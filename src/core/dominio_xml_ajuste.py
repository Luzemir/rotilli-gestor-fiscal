"""
dominio_xml_ajuste.py — Modelo A: alinhamento do CFOP no XML ao Domínio Sistema

Gera cópias dos XMLs de NF-e com o CFOP de entrada reescrito para que, ao
importar no Domínio, o lançamento caia no acumulador coerente com a trilha
AJUSTADA (o Domínio deriva o acumulador do CFOP: x.4xx→ST, x.1xx→Normal).

Regra de negócio (confirmada pelo fiscal):
  Todos os produtos são destinados a REVENDA. Logo o CFOP-alvo depende só da
  direção da Ajustada, preservando o 1º dígito (5 interno / 6 interestadual):
      Ajustada = Normal → alvo  <1ºdígito>102   (ex: 6102)
      Ajustada = ST     → alvo  <1ºdígito>403   (ex: 6403)
  A direção vem de produto_competencia (mod_bc 0-4 = ST, 5 = Normal), NÃO do
  CFOP do XML nem do PMC.

Acumulador no Domínio (derivado por ELE, não escrito aqui): 23 = Normal, 25 = ST.

Segurança:
  - O XML original NUNCA é alterado; grava cópias em pasta separada.
  - A troca é cirurgia de texto: só as tags <CFOP> mudam; todo o resto do
    arquivo (inclusive <Signature>) fica byte a byte igual. O Domínio aceita o
    XML mesmo com a assinatura invalidada (validado em piloto 2026-07-07).
  - CFOP de origem fora da lista prevista NÃO é alterado e vira ALERTA para o
    operador decidir se adiciona à lista.
"""

import os
import re
import sys
import sqlite3
import argparse
from xml.etree import ElementTree as ET

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(ROOT, 'src', 'db', 'gestor_fiscal.db')

NS = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}

# Sufixo do CFOP de revenda por direção (1º dígito 5/6 é preservado do XML)
SUFIXO_ST = '403'
SUFIXO_NORMAL = '102'

# Lista branca de CFOPs de origem esperados (da planilha de-para do fiscal).
# Qualquer CFOP fora daqui gera alerta em vez de ser alterado.
CFOPS_PREVISTOS = {'6101', '6102', '6105', '6106', '6401', '6403', '6910'}

# Rótulos de resultado por item
R_AJUSTADO = 'ajustado'
R_COERENTE = 'coerente'
R_SEM_AJUSTADA = 'sem_ajustada'
R_CFOP_NAO_PREVISTO = 'cfop_nao_previsto'


def direcao_por_mod(mod_bc):
    """mod_bc 0-4 = ST; 5 = Normal; outro = None."""
    if mod_bc in ('0', '1', '2', '3', '4'):
        return 'ST'
    if mod_bc == '5':
        return 'NORMAL'
    return None


def cfop_alvo(cfop_origem, direcao):
    """CFOP de revenda para a direção, preservando o 1º dígito (5 interno / 6 interestadual)."""
    primeiro = cfop_origem[0]
    return primeiro + (SUFIXO_ST if direcao == 'ST' else SUFIXO_NORMAL)


def lookup_ajustada(cur, cnpj, cod, competencia):
    """Última classificação Ajustada conhecida para o produto em mes_ano <= competência."""
    cur.execute(
        '''SELECT mod_bc_icms_st, mes_ano FROM produto_competencia
           WHERE tipo_planilha = 'Ajustada'
             AND cnpj_remetente = ? AND cod_produto_origem = ? AND mes_ano <= ?
           ORDER BY mes_ano DESC LIMIT 1''',
        (cnpj, cod, competencia),
    )
    return cur.fetchone()  # (mod_bc, mes_ano) ou None


def _direcao_por_cfop(cfop):
    """Direção declarada pela centena do CFOP: 4xx=ST, 1xx=Normal, senão None."""
    if not cfop or len(cfop) < 4:
        return None
    return {'4': 'ST', '1': 'NORMAL'}.get(cfop[1])


def status_ajustada(conn, competencia):
    """
    Pré-check da trilha Ajustada para a competência: quantos produtos há para
    classificar. `competencia_exata` = houve carga na própria competência;
    `ultima_mes_ano` = competência Ajustada mais recente aproveitável (<=);
    `universo_produtos` = produtos distintos classificáveis até a competência.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM produto_competencia WHERE tipo_planilha='Ajustada' AND mes_ano=?",
        (competencia,),
    )
    exata = cur.fetchone()[0]
    cur.execute(
        "SELECT MAX(mes_ano) FROM produto_competencia WHERE tipo_planilha='Ajustada' AND mes_ano<=?",
        (competencia,),
    )
    ultima = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(DISTINCT cnpj_remetente || '|' || cod_produto_origem) "
        "FROM produto_competencia WHERE tipo_planilha='Ajustada' AND mes_ano<=?",
        (competencia,),
    )
    universo = cur.fetchone()[0]
    return {'competencia_exata': exata, 'ultima_mes_ano': ultima, 'universo_produtos': universo}


def decidir_itens(xml_path, competencia, conn, apenas_troca_direcao=False):
    """
    Analisa um XML e devolve (emit_cnpj, [decisão por item em ordem de documento]).
    Cada decisão: {num_item, cprod, cfop_old, cfop_new|None, resultado, motivo}.

    apenas_troca_direcao=True: só ajusta itens onde a DIREÇÃO (acumulador) muda;
    suprime as normalizações de mesma direção (ex: 6101→6102, ambos Normal).
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    cur = conn.cursor()

    emit_node = root.find('.//nfe:emit/nfe:CNPJ', NS)
    emit_cnpj = emit_node.text.strip() if emit_node is not None and emit_node.text else None

    decisoes = []
    for det in root.findall('.//nfe:det', NS):
        prod = det.find('nfe:prod', NS)
        if prod is None:
            continue
        cfop_node = prod.find('nfe:CFOP', NS)
        cfop = cfop_node.text.strip() if cfop_node is not None and cfop_node.text else None
        cprod_node = prod.find('nfe:cProd', NS)
        cprod = cprod_node.text.strip() if cprod_node is not None and cprod_node.text else None

        d = {'num_item': det.get('nItem'), 'cprod': cprod, 'cfop_old': cfop,
             'cfop_new': None, 'resultado': None, 'motivo': ''}

        aj = lookup_ajustada(cur, emit_cnpj, cprod, competencia)
        if aj is None:
            d['resultado'] = R_SEM_AJUSTADA
            d['motivo'] = 'produto sem classificação na trilha Ajustada — não alterado'
        elif cfop not in CFOPS_PREVISTOS:
            d['resultado'] = R_CFOP_NAO_PREVISTO
            d['motivo'] = f'CFOP {cfop} não previsto na lista de-para — não alterado (adicionar à lista)'
        else:
            mod_bc, mes_aj = aj
            direcao = direcao_por_mod(mod_bc)
            if direcao is None:
                d['resultado'] = R_SEM_AJUSTADA
                d['motivo'] = f'mod_bc={mod_bc!r} inesperado (Ajustada {mes_aj}) — não alterado'
            else:
                alvo = cfop_alvo(cfop, direcao)
                if cfop == alvo:
                    d['resultado'] = R_COERENTE
                    d['motivo'] = f'já coerente ({direcao}, mod {mod_bc})'
                elif apenas_troca_direcao and _direcao_por_cfop(cfop) == direcao:
                    # mesma direção (acumulador não muda) — normalização suprimida neste modo
                    d['resultado'] = R_COERENTE
                    d['motivo'] = f'normalização suprimida ({cfop} mantém direção {direcao})'
                else:
                    d['cfop_new'] = alvo
                    d['resultado'] = R_AJUSTADO
                    d['motivo'] = f'{cfop}→{alvo} ({direcao}, mod {mod_bc}, Ajustada {mes_aj})'
        decisoes.append(d)

    return emit_cnpj, decisoes


def escrever_xml_ajustado(xml_path, decisoes, saida_path):
    """
    Grava uma cópia do XML aplicando apenas as tags <CFOP> marcadas (por índice
    de ordem no documento). Sempre grava a cópia (mesmo sem mudanças), para que
    a pasta de saída contenha o lote completo pronto para importar no Domínio.
    Retorna a quantidade de CFOP efetivamente trocados.
    """
    with open(xml_path, 'r', encoding='utf-8') as f:
        raw = f.read()

    matches = list(re.finditer(r'<CFOP>(\d+)</CFOP>', raw))
    if len(matches) != len(decisoes):
        raise RuntimeError(
            f'{os.path.basename(xml_path)}: contagem de <CFOP> ({len(matches)}) '
            f'difere de itens ({len(decisoes)}) — abortado por segurança.'
        )

    mudancas = {i: d['cfop_new'] for i, d in enumerate(decisoes) if d['cfop_new']}

    if mudancas:
        partes, last = [], 0
        for i, m in enumerate(matches):
            if i in mudancas:
                partes.append(raw[last:m.start()])
                partes.append(f'<CFOP>{mudancas[i]}</CFOP>')
                last = m.end()
        partes.append(raw[last:])
        raw = ''.join(partes)

    os.makedirs(os.path.dirname(saida_path), exist_ok=True)
    with open(saida_path, 'w', encoding='utf-8') as f:
        f.write(raw)
    return len(mudancas)


def processar_pasta(pasta, competencia, conn, saida_dir=None, apenas_troca_direcao=False):
    """
    Processa todos os XMLs de `pasta`, grava as cópias ajustadas e devolve um
    relatório agregado com contadores e a lista de pendências/alertas.
    """
    import glob
    if saida_dir is None:
        saida_dir = os.path.join(ROOT, 'Documentos', competencia, 'xml_dominio')

    arquivos = sorted(glob.glob(os.path.join(pasta, '*.xml')))
    rel = {
        'competencia': competencia, 'saida_dir': saida_dir,
        'arquivos': 0, 'itens': 0,
        'itens_ajustados': 0, 'itens_coerentes': 0,
        'itens_sem_ajustada': 0, 'itens_cfop_nao_previsto': 0,
        'arquivos_ajustados': 0,
        'cfops_nao_previstos': {},        # cfop -> qtd (para o alerta "adicionar à lista")
        'pendencias': [],                 # itens sem_ajustada ou cfop_nao_previsto
    }

    for arq in arquivos:
        emit_cnpj, decisoes = decidir_itens(arq, competencia, conn, apenas_troca_direcao)
        nome = os.path.basename(arq)
        n = escrever_xml_ajustado(arq, decisoes, os.path.join(saida_dir, nome))

        rel['arquivos'] += 1
        rel['itens'] += len(decisoes)
        if n:
            rel['arquivos_ajustados'] += 1
        for d in decisoes:
            res = d['resultado']
            if res == R_AJUSTADO:
                rel['itens_ajustados'] += 1
            elif res == R_COERENTE:
                rel['itens_coerentes'] += 1
            elif res == R_SEM_AJUSTADA:
                rel['itens_sem_ajustada'] += 1
                rel['pendencias'].append((nome, d['num_item'], d['cprod'], d['cfop_old'], d['motivo']))
            elif res == R_CFOP_NAO_PREVISTO:
                rel['itens_cfop_nao_previsto'] += 1
                rel['cfops_nao_previstos'][d['cfop_old']] = rel['cfops_nao_previstos'].get(d['cfop_old'], 0) + 1
                rel['pendencias'].append((nome, d['num_item'], d['cprod'], d['cfop_old'], d['motivo']))

    return rel


def _imprimir_relatorio(rel):
    print('=' * 72)
    print(f' Ajuste de CFOP para o Domínio — competência {rel["competencia"]}')
    print(f' Saída: {rel["saida_dir"]}')
    print('=' * 72)
    print(f'  Arquivos processados      : {rel["arquivos"]} ({rel["arquivos_ajustados"]} com ajuste)')
    print(f'  Itens                     : {rel["itens"]}')
    print(f'  ├─ CFOP ajustado          : {rel["itens_ajustados"]}')
    print(f'  ├─ já coerente            : {rel["itens_coerentes"]}')
    print(f'  ├─ sem classif. Ajustada  : {rel["itens_sem_ajustada"]}  (pendência)')
    print(f'  └─ CFOP não previsto      : {rel["itens_cfop_nao_previsto"]}  (alerta)')
    if rel['cfops_nao_previstos']:
        print('\n  ALERTA — CFOPs não previstos na lista de-para (adicionar se necessário):')
        for cfop, q in sorted(rel['cfops_nao_previstos'].items()):
            print(f'    {cfop}: {q} item(ns)')


def main():
    ap = argparse.ArgumentParser(description='Ajuste de CFOP dos XMLs para o Domínio (trilha Ajustada)')
    ap.add_argument('--pasta', required=True, help='Pasta com os XMLs (ex: data/nfe/2026-05)')
    ap.add_argument('--competencia', required=True, help='Competência AAAA-MM')
    ap.add_argument('--saida', default=None, help='Pasta de saída (default: Documentos/<comp>/xml_dominio)')
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    rel = processar_pasta(args.pasta, args.competencia, conn, args.saida)
    conn.close()
    _imprimir_relatorio(rel)


if __name__ == '__main__':
    main()
