"""
nfe_parser.py — Módulo de Parsing de NF-e (Nota Fiscal Eletrônica)
Responsabilidade:
  - Ler XMLs de uma pasta
  - Extrair os dados de cada item da nota
  - Cruzar com o Banco de Dados de Produtos
  - Alertar sobre produtos novos (não cadastrados)
  - Retornar lista de itens com a classificação ICMS-ST

Uso:
  python src/core/nfe_parser.py --pasta data/nfe/2026-05
"""

import os
import re
import sys
import glob
import sqlite3
import argparse
from xml.etree import ElementTree as ET

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cmed_comparador import comparar_pmc, consultar_pmc_cmed, PMC_OK, PMC_DIVERGENTE, PMC_SEM_CMED, PMC_SEM_EAN

DB_PATH = os.path.join("src", "db", "gestor_fiscal.db")

# Namespace padrão das NF-es brasileiras
NS = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}

# Mapa de descrição dos códigos de tributação
MAPA_MOD_BC = {
    '0': 'PMC (Tabela CMED)',
    '1': 'Lista Negativa',
    '2': 'Lista Positiva',
    '3': 'Lista Neutra',
    '4': 'MVA (Margem Valor Agregado)',
    '5': 'Normal / Sem ST',
}


def _text(element, path, ns=NS, default=None):
    """Extrai texto de um subelemento XML com segurança."""
    node = element.find(path, ns)
    return node.text.strip() if node is not None and node.text else default


def _numero(element, path, ns=NS, default=0.0):
    """Extrai um valor numérico de um subelemento XML, com default seguro."""
    texto = _text(element, path, ns)
    try:
        return float(texto) if texto else default
    except ValueError:
        return default


def _extrair_chave_acesso(root, nfe):
    """
    Extrai a chave de acesso de 44 dígitos: do atributo Id de infNFe
    ("NFe" + 44 dígitos), com fallback em protNFe/infProt/chNFe.
    """
    chave = nfe.get('Id')
    if chave and chave.upper().startswith('NFE'):
        chave = chave[3:]
    if not chave or len(chave) != 44:
        prot = root.find('.//nfe:protNFe/nfe:infProt/nfe:chNFe', NS)
        if prot is not None and prot.text:
            chave = prot.text.strip()
    return chave


def _extrair_icms_origem(det):
    """
    Extrai BC e VLR do ICMS de origem. O nome do sub-elemento de ICMS varia
    por CST/CSOSN (ICMS00, ICMS10, ICMSSN101 etc.) — pega o primeiro (único)
    filho de imposto/ICMS, qualquer que seja o nome, e lê vBC/vICMS dele.

    Notas do Simples Nacional com permissão de crédito (ICMSSN101 = CSOSN 101,
    ICMSSN201 = CSOSN 201) não têm vBC/vICMS; declaram o crédito de ICMS que o
    destinatário pode aproveitar (art. 23 da LC 123/2006) em vCredICMSSN (valor)
    e pCredSN (alíquota do crédito, em %). Nesse caso:
      VLR ICMS (origem) = vCredICMSSN
      BC  ICMS (origem) = vProd + frete + seguro/desp. acess. - desconto

    Retorna (bc, vlr, compor_base). Quando compor_base=True (nota do Simples com
    crédito) a BC ainda não está pronta — o chamador a compõe DEPOIS do rateio e
    da consolidação de seguro+despesas acessórias (ver parsear_xml).
    """
    icms_node = det.find('nfe:imposto/nfe:ICMS', NS)
    if icms_node is None or len(icms_node) == 0:
        return None, None, False
    grupo = icms_node[0]

    bc = _text(grupo, 'nfe:vBC')
    vicms = _text(grupo, 'nfe:vICMS')
    if bc is not None or vicms is not None:
        return (float(bc) if bc else None,
                float(vicms) if vicms else None, False)

    # Simples Nacional com permissão de crédito (CSOSN 101/201)
    vcred = _text(grupo, 'nfe:vCredICMSSN')
    if vcred is None:
        return None, None, False
    return None, float(vcred), True


def _extrair_icms_st_nfe(det):
    """
    Extrai vBCST e vICMSST declarados pelo remetente na NF-e.
    Presentes em grupos como ICMS10, ICMS30, ICMS70, ICMS90.
    Esses valores representam o ICMS-ST retido/cobrado na operação.
    """
    icms_node = det.find('nfe:imposto/nfe:ICMS', NS)
    if icms_node is None or len(icms_node) == 0:
        return None, None
    grupo = icms_node[0]
    vbcst   = _text(grupo, 'nfe:vBCST')
    vicmsst = _text(grupo, 'nfe:vICMSST')
    return (float(vbcst) if vbcst else None,
            float(vicmsst) if vicmsst else None)


def _extrair_ipi(det):
    """Extrai o valor de IPI da NF-e (tag vIPI dentro de IPITrib ou IPINT)."""
    ipi_node = det.find('nfe:imposto/nfe:IPI', NS)
    if ipi_node is None:
        return None
    vipi = _text(ipi_node, './/nfe:vIPI')
    return float(vipi) if vipi else None


def _aplicar_rateio(itens, campo, total):
    """
    Distribui um valor total proporcionalmente entre os itens quando o campo
    está zerado em todos os itens mas o total da nota é positivo.
    Proporção: vProd do item / soma dos vProd da nota.
    O último item absorve as diferenças de arredondamento.
    """
    if total < 0.01:
        return
    if sum(float(i.get(campo) or 0) for i in itens) > 0.01:
        return  # já distribuído por item pelo emitente
    vProd_sum = sum(float(i.get('valor_total') or 0) for i in itens)
    if vProd_sum < 0.01:
        return
    acumulado = 0.0
    for idx, item in enumerate(itens):
        vProd_item = float(item.get('valor_total') or 0)
        if idx == len(itens) - 1:
            item[campo] = round(total - acumulado, 2)
        else:
            valor = round(total * vProd_item / vProd_sum, 2)
            acumulado += valor
            item[campo] = valor


def parsear_xml(filepath):
    """
    Parseia um único arquivo XML de NF-e e retorna um dicionário com os dados
    da nota e a lista de itens (produtos).
    """
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()

        # Suporta tanto a raiz <nfeProc> quanto <NFe> diretamente
        nfe = root.find('.//nfe:NFe/nfe:infNFe', NS) or root.find('.//nfe:infNFe', NS)
        if nfe is None:
            print(f"  [AVISO] Estrutura XML não reconhecida em: {filepath}")
            return None

        chave_acesso = _extrair_chave_acesso(root, nfe)
        cnpj_emitente = _text(nfe, 'nfe:emit/nfe:CNPJ')
        razao_remetente = _text(nfe, 'nfe:emit/nfe:xNome')
        uf_remetente = _text(nfe, 'nfe:emit/nfe:enderEmit/nfe:UF')
        num_nf = _text(nfe, 'nfe:ide/nfe:nNF')
        data_emissao = _text(nfe, 'nfe:ide/nfe:dhEmi') or _text(nfe, 'nfe:ide/nfe:dEmi')

        # Totais da nota — base para rateio quando campos não estão distribuídos por item
        _tot = nfe.find('nfe:total/nfe:ICMSTot', NS)
        _vFrete_tot = float(_text(_tot, 'nfe:vFrete') or 0) if _tot is not None else 0.0
        _vSeg_tot   = float(_text(_tot, 'nfe:vSeg')   or 0) if _tot is not None else 0.0
        _vOutro_tot = float(_text(_tot, 'nfe:vOutro') or 0) if _tot is not None else 0.0

        itens = []
        for det in nfe.findall('nfe:det', NS):
            prod = det.find('nfe:prod', NS)
            if prod is None:
                continue

            bc_icms_origem, vlr_icms_origem, compor_base_origem = _extrair_icms_origem(det)
            bc_icms_st_nfe, vlr_icms_st_nfe = _extrair_icms_st_nfe(det)
            vOutro = _numero(prod, 'nfe:vOutro')

            item = {
                'chave_acesso': chave_acesso,
                'num_item': det.get('nItem'),
                'cnpj_emitente': cnpj_emitente,
                'razao_remetente': razao_remetente,
                'uf_remetente': uf_remetente,
                'num_nf': num_nf,
                'data_emissao': data_emissao,
                'ean': _text(prod, 'nfe:cEAN'),
                'cod_produto': _text(prod, 'nfe:cProd'),
                'descricao': _text(prod, 'nfe:xProd'),
                'ncm': _text(prod, 'nfe:NCM'),
                'cest': _text(prod, 'nfe:CEST'),
                'cfop': _text(prod, 'nfe:CFOP'),
                'unidade': _text(prod, 'nfe:uCom'),
                'quantidade': _text(prod, 'nfe:qCom'),
                'valor_unitario': _text(prod, 'nfe:vUnCom'),
                'valor_total': _text(prod, 'nfe:vProd'),
                'frete': _numero(prod, 'nfe:vFrete'),
                'seguro': _numero(prod, 'nfe:vSeg'),
                # _vOutro temporário — somado ao seguro após rateio (col T "Seguro/Desp. Acess.")
                '_vOutro': vOutro,
                'ipi_despesas': _extrair_ipi(det) or 0.0,  # IPI do produto (col U "IPI")
                'desconto': _numero(prod, 'nfe:vDesc'),
                'bc_icms_origem': bc_icms_origem,
                'vlr_icms_origem': vlr_icms_origem,
                # Nota do Simples com crédito: BC composta após rateio (abaixo)
                '_compor_base_origem': compor_base_origem,
                'bc_icms_st_nfe': bc_icms_st_nfe,
                'vlr_icms_st_nfe': vlr_icms_st_nfe,
                # Será preenchido depois pelo cruzamento com o BD
                'mod_bc_icms_st': None,
                'pmc': None,
                'mva': None,
                'status': 'PENDENTE',
            }
            itens.append(item)

        # Rateio proporcional: distribui valores que estão apenas no total da nota
        _aplicar_rateio(itens, 'frete',   _vFrete_tot)
        _aplicar_rateio(itens, 'seguro',  _vSeg_tot)
        _aplicar_rateio(itens, '_vOutro', _vOutro_tot)

        # Consolida seguro = seguro + vOutro (possivelmente rateados) — col T "Seguro/Desp. Acess."
        for item in itens:
            item['seguro'] = round((item.get('seguro') or 0.0) + (item.pop('_vOutro') or 0.0), 2)
            # BC ICMS origem do Simples: composta agora que frete/seguro/desp.
            # acessórias já foram rateados e consolidados.
            # BC = vProd + frete + seguro/desp. acess. - desconto
            if item.pop('_compor_base_origem', False):
                item['bc_icms_origem'] = round(
                    float(item.get('valor_total') or 0)
                    + (item.get('frete') or 0.0)
                    + (item.get('seguro') or 0.0)
                    - (item.get('desconto') or 0.0), 2)

        return {'cnpj_emitente': cnpj_emitente, 'num_nf': num_nf, 'data_emissao': data_emissao, 'itens': itens}

    except ET.ParseError as e:
        print(f"  [ERRO] XML malformado em {filepath}: {e}")
        return None


def _extrair_mes_ano(data_emissao):
    """Extrai YYYY-MM de data_emissao da NF-e (ex: '2026-05-15T10:30:00-03:00')."""
    if not data_emissao:
        return None
    m = re.match(r'(\d{4}-\d{2})', data_emissao)
    return m.group(1) if m else None


def extrair_competencia_pasta(pasta):
    """
    Extrai a competência pretendida (YYYY-MM) do nome da pasta importada.
    Todos os XMLs de uma pasta pertencem à competência da pasta — uma NF-e
    emitida no fim do mês anterior mas importada no lote do mês corrente
    entra na apuração do mês corrente, não no mês da própria emissão.
    """
    nome = os.path.basename(os.path.normpath(pasta))
    m = re.match(r'^(\d{4}-\d{2})$', nome)
    return m.group(1) if m else None


def _pre_classificar(item, competencia, conn):
    """
    Pré-classifica produto novo com base na tabela ncm_st (Subanexo MS) e CMED.

    Regras aplicadas em ordem:
      NCM em ncm_st + EAN na CMED + PMC 17% > 0              → 0  PMC
      NCM em ncm_st + EAN na CMED + PMC = 0 + lista Positiva → 1  Lista Positiva
      NCM em ncm_st + EAN na CMED + PMC = 0 + lista Negativa → 2  Lista Negativa
      NCM em ncm_st + EAN na CMED + PMC = 0 + lista Neutra   → 3  Lista Neutra
      NCM em ncm_st + EAN não na CMED                        → 4  MVA (por alíq.)
      NCM não em ncm_st + EAN não na CMED                    → 5  Normal
      NCM não em ncm_st + EAN na CMED                        → 5  Normal + pre_nota anomalia
    """
    item['pre_mod_bc'] = None
    item['pre_pmc']    = None
    item['pre_mva']    = None
    item['pre_nota']   = None

    ncm  = item.get('ncm')  or ''
    cest = item.get('cest') or ''
    ean  = item.get('ean')

    ncm_norm  = re.sub(r'[.\s]', '', ncm)
    cest_norm = re.sub(r'[.\s-]', '', cest)

    cur = conn.cursor()

    # ── 1. Verifica se produto é ICMS-ST (NCM raiz ou CEST exato na ncm_st) ──
    row_cest = None
    if cest_norm:
        cur.execute(
            "SELECT mva_interno, mva_aliq4, mva_aliq7, mva_aliq12 "
            "FROM ncm_st WHERE cest_norm = ? LIMIT 1",
            (cest_norm,),
        )
        row_cest = cur.fetchone()

    row_ncm = None
    if ncm_norm and row_cest is None:   # só consulta NCM se CEST não achou
        cur.execute(
            "SELECT mva_interno, mva_aliq4, mva_aliq7, mva_aliq12 "
            "FROM ncm_st WHERE ? LIKE ncm_norm || '%' LIMIT 1",
            (ncm_norm,),
        )
        row_ncm = cur.fetchone()

    is_st   = (row_cest is not None) or (row_ncm is not None)
    # MVA só é preenchido automaticamente quando o CEST é localizado (match exato)
    mva_row = row_cest   # None → usuário deve preencher manualmente

    # ── 2. EAN presente na CMED? ──────────────────────────────────────────────
    pmc_17, tipo_lista = None, None
    if ean and competencia:
        pmc_17, tipo_lista = consultar_pmc_cmed(ean, competencia, conn)

    # Usa tipo_lista (não pmc_17) para detectar presença na CMED:
    # pmc_17 pode ser NULL no banco mesmo com o EAN cadastrado.
    ean_na_cmed = tipo_lista is not None

    # ── 3. Aplica regras ──────────────────────────────────────────────────────
    if is_st and ean_na_cmed:
        if pmc_17 and pmc_17 > 0:
            # MOD 0 — PMC conhecido e positivo
            item['pre_mod_bc'] = '0'
            item['pre_pmc']    = pmc_17
        else:
            # PMC = 0 ou ausente → roteia pela lista
            _lista_mod = {'Positiva': '1', 'Negativa': '2', 'Neutra': '3'}
            mod = _lista_mod.get(tipo_lista or '')
            if mod:
                item['pre_mod_bc'] = mod
            else:
                # tipo_lista não reconhecido → não classifica automaticamente
                item['pre_mod_bc'] = None
                item['pre_nota'] = (
                    f'EAN localizado na CMED mas PMC 17% = 0 e lista não identificada '
                    f'(lista retornada: {tipo_lista!r}). Classifique manualmente como MOD 1, 2 ou 3.'
                )

    elif is_st and not ean_na_cmed:
        # MOD 4 — ST sem correspondência na CMED
        item['pre_mod_bc'] = '4'
        if mva_row is not None:
            bc   = float(item.get('bc_icms_origem') or 0)
            vlr  = float(item.get('vlr_icms_origem') or 0)
            aliq = round(vlr / bc * 100) if bc > 0 else None

            if aliq is None:
                # Alíquota não calculável (NF sem ICMS declarado) → MVA fica vazio
                item['pre_mva'] = None
            elif aliq >= 15:
                item['pre_mva'] = round(mva_row[0] / 100, 4) if mva_row[0] is not None else None
            elif aliq >= 10:
                item['pre_mva'] = round(mva_row[3] / 100, 4) if mva_row[3] is not None else None
            elif aliq >= 5:
                item['pre_mva'] = round(mva_row[2] / 100, 4) if mva_row[2] is not None else None
            else:
                item['pre_mva'] = round(mva_row[1] / 100, 4) if mva_row[1] is not None else None
        # mva_row is None (CEST não localizado) → pre_mva permanece None

    elif not is_st and not ean_na_cmed:
        # MOD 5 — produto normal, fora do subanexo ST
        item['pre_mod_bc'] = '5'

    else:
        # NCM fora do subanexo ST, mas EAN localizado na CMED — anomalia
        item['pre_mod_bc'] = '5'
        item['pre_nota'] = (
            f'NCM {ncm} não consta no Subanexo ST, mas EAN localizado na CMED '
            f'(PMC 17% = {pmc_17}, Lista = {tipo_lista}). Verificar situação do produto.'
        )


def classificar_itens(itens, conn, mes_ano=None):
    """
    Recebe uma lista de itens extraídos da NF-e e cruza com o BD de Produtos.
    Para produtos PMC (mod_bc=0), compara o preço com a tabela CMED.
    Retorna dois grupos: itens classificados e itens novos (sem cadastro).
    """
    cursor = conn.cursor()
    classificados = []
    novos_produtos = []

    for item in itens:
        cnpj = item.get('cnpj_emitente')
        cod = item.get('cod_produto')

        # Usa mes_ano do argumento; fallback para a data de emissão do item
        competencia = mes_ano or _extrair_mes_ano(item.get('data_emissao'))

        cursor.execute('''
            SELECT p.descricao_produto, p.unidade,
                   pc.mod_bc_icms_st, pc.pmc, pc.mva, pc.mes_ano, pc.tipo_planilha
            FROM produtos p
            LEFT JOIN produto_competencia pc
                ON p.cnpj_remetente = pc.cnpj_remetente
                AND p.cod_produto_origem = pc.cod_produto_origem
            WHERE p.cnpj_remetente = ? AND p.cod_produto_origem = ?
            ORDER BY pc.mes_ano DESC, pc.tipo_planilha
            LIMIT 2
        ''', (cnpj, cod))

        rows = cursor.fetchall()

        if rows:
            row_original = next((r for r in rows if r[6] == 'Original'), rows[0])

            item['mod_bc_icms_st'] = row_original[2]
            item['pmc'] = row_original[3]
            item['mva'] = row_original[4]
            item['mes_referencia'] = row_original[5]
            item['descricao_bd'] = row_original[0]
            item['nome_tipo'] = MAPA_MOD_BC.get(str(row_original[2]), 'Desconhecido')

            if str(row_original[2]) == '0' and competencia:
                # Produto PMC: consulta e compara com a CMED
                comparar_pmc(item, competencia, conn)
            else:
                item['status'] = 'CLASSIFICADO'

            classificados.append(item)
        else:
            item['status'] = 'NOVO_PRODUTO'
            _pre_classificar(item, competencia, conn)
            novos_produtos.append(item)

    return classificados, novos_produtos


def processar_pasta(pasta_xmls):
    """
    Ponto de entrada principal: processa todos os XMLs de uma pasta.
    """
    if not os.path.exists(pasta_xmls):
        print(f"[ERRO] Pasta não encontrada: {pasta_xmls}")
        return

    arquivos = glob.glob(os.path.join(pasta_xmls, "*.xml"))
    if not arquivos:
        print(f"[AVISO] Nenhum arquivo XML encontrado em: {pasta_xmls}")
        return

    competencia = extrair_competencia_pasta(pasta_xmls)
    if not competencia:
        print(f"[ERRO] A pasta deve terminar em uma competência AAAA-MM (ex: data/nfe/2026-05). Recebido: {pasta_xmls}")
        return

    print(f"\n{'='*60}")
    print(f" GESTOR FISCAL — Processamento de NF-e")
    print(f" Pasta: {pasta_xmls}")
    print(f" Competência: {competencia}")
    print(f" Arquivos encontrados: {len(arquivos)}")
    print(f"{'='*60}\n")

    conn = sqlite3.connect(DB_PATH)

    todos_classificados = []
    todos_novos = []

    for arquivo in arquivos:
        print(f"Lendo: {os.path.basename(arquivo)}")
        nota = parsear_xml(arquivo)
        if not nota:
            continue

        classificados, novos = classificar_itens(nota['itens'], conn, competencia)
        todos_classificados.extend(classificados)
        todos_novos.extend(novos)

    conn.close()

    # ---- Contadores por status PMC ----
    pmc_ok         = [i for i in todos_classificados if i.get('status') == PMC_OK]
    pmc_divergente = [i for i in todos_classificados if i.get('status') == PMC_DIVERGENTE]
    pmc_sem_cmed   = [i for i in todos_classificados if i.get('status') == PMC_SEM_CMED]
    pmc_sem_ean    = [i for i in todos_classificados if i.get('status') == PMC_SEM_EAN]

    # ---- RELATÓRIO FINAL ----
    print(f"\n{'='*60}")
    print(f" RESULTADO DO PROCESSAMENTO")
    print(f"{'='*60}")
    print(f"  Itens classificados automaticamente : {len(todos_classificados)}")
    print(f"  NOVOS PRODUTOS (classificar manual) : {len(todos_novos)}")
    print(f"")
    print(f"  --- Produtos PMC (mod_bc=0) ---")
    print(f"  PMC em dia (CMED confirma)          : {len(pmc_ok)}")
    print(f"  PMC DIVERGENTE (atualizado p/ CMED) : {len(pmc_divergente)}")
    print(f"  Nao encontrado na CMED              : {len(pmc_sem_cmed)}")
    print(f"  Sem EAN (nao consultavel)           : {len(pmc_sem_ean)}")

    if pmc_divergente:
        print(f"\n{'─'*60}")
        print(f" PMC ATUALIZADOS PELA CMED ({len(pmc_divergente)} item(ns)):")
        print(f"{'─'*60}")
        print(f"  {'Codigo':<15} {'EAN':<15} {'PMC BD':>10} {'PMC CMED':>10} {'Diferenca':>10}")
        print(f"  {'-'*14} {'-'*14} {'-'*10} {'-'*10} {'-'*10}")
        for item in pmc_divergente:
            pmc_bd_orig = item['pmc'] - item.get('pmc_divergencia', 0)
            print(f"  {str(item['cod_produto']):<15} {str(item['ean']):<15} "
                  f"  R${pmc_bd_orig:>7.2f}   R${item['pmc']:>7.2f}   R${item.get('pmc_divergencia', 0):>+7.2f}")

    if todos_novos:
        print(f"\n{'─'*60}")
        print(f" ATENCAO: {len(todos_novos)} PRODUTO(S) NOVO(S) — classifique antes de fechar a apuracao:")
        print(f"{'─'*60}")
        for i, item in enumerate(todos_novos, 1):
            print(f"  [{i:03d}] NF: {item['num_nf']} | "
                  f"Cod: {item['cod_produto']} | "
                  f"EAN: {item['ean']} | "
                  f"Desc: {item['descricao']}")

    return todos_classificados, todos_novos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Gestor Fiscal — Parser de NF-e')
    parser.add_argument('--pasta', required=True, help='Caminho da pasta com os arquivos XML das NF-es')
    args = parser.parse_args()
    processar_pasta(args.pasta)
