"""
competencia_importer.py — Núcleo de importação das planilhas RegimeEspecial

Responsabilidade:
  - Reconhecer/validar nomes de arquivo (histórico tolerante + padrão estrito novo)
  - Ler a planilha RegimeEspecial (caminho ou arquivo enviado pelo navegador)
  - Gravar produto_competencia somente quando a classificação realmente mudou
    em relação à última competência conhecida daquele produto+trilha

Critério de mudança: (mod_bc_icms_st, mva) diferente do último estado
conhecido para o produto+tipo_planilha. O valor de PMC não entra nessa
comparação — vem de outra fonte (CMED) e é tratado por cmed_comparador.py.
"""

import re
import pandas as pd

PADRAO_EXCLUSAO = re.compile(r'rotili|envio\s*fiscal', re.IGNORECASE)

# Exigido a partir de agora para uploads novos via Streamlit
PADRAO_ESTRITO = re.compile(r'^RegimeEspecialMS_(\d{4})_(\d{2})_(Original|Ajustada)\.xls[mx]$')

# Reconhece nomes históricos inconsistentes: sem sufixo, hífen/underscore, "Ajustado"/"Ajustada"
PADRAO_LENIENTE = re.compile(
    r'^RegimeEspecialMS_(\d{4})_(\d{2})(?:[-_](Original|Ajustad[ao]))?\.xls[mx]$',
    re.IGNORECASE,
)

# Índices de coluna (0-based) na aba RegimeEspecial
COL_CEST, COL_NCM, COL_EAN = 8, 9, 10
COL_CNPJ, COL_COD_PRODUTO, COL_DESCRICAO, COL_UNIDADE = 6, 12, 14, 15
COL_PMC, COL_MVA, COL_MOD_BC = 24, 25, 26

MOD_BC_VALIDOS = {'0', '1', '2', '3', '4', '5'}


def classificar_arquivo_historico(nome_arquivo):
    """
    Reconhece um nome de arquivo histórico (tolerante a hífen/underscore,
    sufixo ausente, "Ajustado" vs "Ajustada"). Exclui explicitamente
    qualquer variante de "Rotili.../EnvioFiscal...".

    Retorna {'mes_ano': 'YYYY-MM', 'tipo_planilha': 'Original'|'Ajustada'}
    ou None se o arquivo não for reconhecido / deve ser ignorado.
    """
    if PADRAO_EXCLUSAO.search(nome_arquivo):
        return None

    m = PADRAO_LENIENTE.match(nome_arquivo)
    if not m:
        return None

    ano, mes, sufixo = m.group(1), m.group(2), m.group(3)
    if sufixo and sufixo.lower().startswith('ajustad'):
        tipo_planilha = 'Ajustada'
    else:
        tipo_planilha = 'Original'

    return {'mes_ano': f'{ano}-{mes}', 'tipo_planilha': tipo_planilha}


def validar_nome_upload(nome_arquivo, ano, mes, tipo_esperado):
    """
    Valida nome_arquivo contra o padrão estrito exigido para uploads novos,
    e contra a competência/tipo informados na tela.

    Retorna (True, '') se válido, ou (False, mensagem_especifica) se não.
    """
    if PADRAO_EXCLUSAO.search(nome_arquivo):
        return False, (
            f'O arquivo "{nome_arquivo}" parece ser um arquivo de envio ao fiscal '
            f'("Rotili.../EnvioFiscal..."), não a planilha RegimeEspecial. '
            f'Envie o arquivo "RegimeEspecialMS_{ano}_{mes}_{tipo_esperado}.xlsx".'
        )

    m_estrito = PADRAO_ESTRITO.match(nome_arquivo)
    if not m_estrito:
        # Tenta diagnosticar a causa exata usando o padrão leniente
        m_leniente = PADRAO_LENIENTE.match(nome_arquivo)
        if m_leniente:
            ano_arq, mes_arq, sufixo_arq = m_leniente.groups()
            if not sufixo_arq:
                return False, (
                    f'O arquivo "{nome_arquivo}" não informa se é Original ou Ajustada no nome. '
                    f'Renomeie para "RegimeEspecialMS_{ano_arq}_{mes_arq}_{tipo_esperado}.xlsx".'
                )
            if sufixo_arq not in ('Original', 'Ajustada'):
                return False, (
                    f'O arquivo "{nome_arquivo}" usa o sufixo "{sufixo_arq}", mas o padrão exige '
                    f'exatamente "Original" ou "Ajustada". Renomeie para '
                    f'"RegimeEspecialMS_{ano_arq}_{mes_arq}_{tipo_esperado}.xlsx".'
                )
            return False, (
                f'O arquivo "{nome_arquivo}" não usa "_" antes do tipo (formato exigido: '
                f'"RegimeEspecialMS_AAAA_MM_{tipo_esperado}.xlsx"). Renomeie o arquivo.'
            )
        return False, (
            f'O nome "{nome_arquivo}" não segue o padrão exigido '
            f'"RegimeEspecialMS_AAAA_MM_{tipo_esperado}.xlsx" (ou .xlsm).'
        )

    ano_arq, mes_arq, tipo_arq = m_estrito.groups()

    if tipo_arq != tipo_esperado:
        return False, (
            f'Este arquivo é do tipo "{tipo_arq}", mas foi enviado no campo "{tipo_esperado}". '
            f'Verifique se os arquivos não foram trocados de campo.'
        )

    if ano_arq != str(ano) or mes_arq != str(mes):
        return False, (
            f'O arquivo indica competência {ano_arq}-{mes_arq}, mas você informou '
            f'{ano}-{mes}. Corrija a competência ou envie o arquivo certo.'
        )

    return True, ''


def ler_planilha_regime_especial(fonte):
    """
    Lê a aba 'RegimeEspecial' (fallback: primeira aba) de `fonte`, que pode
    ser um caminho (str) ou um objeto file-like (ex: UploadedFile do
    Streamlit). Pula as 2 primeiras linhas de cabeçalho e retorna um
    DataFrame com colunas nomeadas e já tipadas.
    """
    if hasattr(fonte, 'seek'):
        fonte.seek(0)

    xl = pd.ExcelFile(fonte)
    sheet_name = 'RegimeEspecial' if 'RegimeEspecial' in xl.sheet_names else xl.sheet_names[0]

    df = xl.parse(sheet_name=sheet_name, header=None)
    df = df.iloc[2:]  # pula as 2 primeiras linhas de cabeçalho

    registros = []
    for _, row in df.iterrows():
        cod_produto = str(row[COL_COD_PRODUTO]).strip() if pd.notna(row[COL_COD_PRODUTO]) else None
        if not cod_produto or cod_produto == 'nan':
            continue

        mod_bc = str(row[COL_MOD_BC]).strip() if pd.notna(row[COL_MOD_BC]) else None
        if mod_bc not in MOD_BC_VALIDOS:
            continue

        cnpj = str(row[COL_CNPJ]).strip() if pd.notna(row[COL_CNPJ]) else None
        descricao = str(row[COL_DESCRICAO]).strip() if pd.notna(row[COL_DESCRICAO]) else None
        unidade = str(row[COL_UNIDADE]).strip() if pd.notna(row[COL_UNIDADE]) else None

        ean_raw = str(row[COL_EAN]).strip() if pd.notna(row[COL_EAN]) else None
        # Remove ".0" do Excel e valores sem GTIN real
        if ean_raw and ean_raw.endswith('.0'):
            ean_raw = ean_raw[:-2]
        ean = ean_raw if ean_raw and ean_raw not in ('SEM GTIN', '0', '') else None

        ncm_raw = str(row[COL_NCM]).strip() if pd.notna(row[COL_NCM]) else None
        if ncm_raw and ncm_raw.endswith('.0'):
            ncm_raw = ncm_raw[:-2]
        ncm = ncm_raw if ncm_raw and ncm_raw not in ('0', '') else None

        cest_raw = str(row[COL_CEST]).strip() if pd.notna(row[COL_CEST]) else None
        if cest_raw and cest_raw.endswith('.0'):
            cest_raw = cest_raw[:-2]
        cest = cest_raw if cest_raw and cest_raw not in ('0', '') else None

        pmc = pd.to_numeric(row[COL_PMC], errors='coerce')
        pmc = float(pmc) if pd.notna(pmc) else None

        mva = pd.to_numeric(row[COL_MVA], errors='coerce')
        mva = float(mva) if pd.notna(mva) else None

        registros.append({
            'cnpj_remetente': cnpj,
            'cod_produto_origem': cod_produto,
            'descricao_produto': descricao,
            'unidade': unidade,
            'ean': ean,
            'ncm': ncm,
            'cest': cest,
            'pmc': pmc,
            'mva': mva,
            'mod_bc_icms_st': mod_bc,
        })

    return pd.DataFrame(registros)


def _estado(mod_bc, mva):
    # pd.isna cobre tanto None (vindo do banco) quanto NaN (vindo do DataFrame,
    # já que pandas converte None->NaN ao montar uma coluna float a partir de
    # uma lista de dicts) — comparar NaN == NaN é sempre False em Python, então
    # usar `is not None` aqui faria toda linha com MVA ausente parecer "mudada".
    mva_norm = None if pd.isna(mva) else round(mva, 4)
    return (mod_bc, mva_norm)


def importar_competencia(conn, fonte, mes_ano, tipo_planilha, commit=True):
    """
    Lê `fonte` e grava produto_competencia somente para produtos cuja
    classificação (mod_bc_icms_st, mva) mudou em relação à última
    competência conhecida (mes_ano < mes_ano atual) naquela trilha.

    Retorna um relatório:
        {
            'mes_ano', 'tipo_planilha',
            'produtos_novos': int,
            'linhas_gravadas': int,
            'linhas_inalteradas': int,
            'total_linhas': int,
            'aviso_recalculo': str | None,
        }
    """
    df = ler_planilha_regime_especial(fonte)
    cursor = conn.cursor()

    # 1. Upsert da parte fixa (produtos)
    produtos_unicos = (
        df[['cnpj_remetente', 'cod_produto_origem', 'descricao_produto', 'unidade', 'ean', 'ncm', 'cest']]
        .drop_duplicates(subset=['cnpj_remetente', 'cod_produto_origem'])
    )

    produtos_novos = 0
    for _, p in produtos_unicos.iterrows():
        cursor.execute(
            'SELECT 1 FROM produtos WHERE cnpj_remetente = ? AND cod_produto_origem = ?',
            (p['cnpj_remetente'], p['cod_produto_origem']),
        )
        if cursor.fetchone() is None:
            produtos_novos += 1
        cursor.execute(
            '''INSERT INTO produtos
                   (cnpj_remetente, cod_produto_origem, descricao_produto, unidade, ean, ncm, cest)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(cnpj_remetente, cod_produto_origem) DO UPDATE SET
                   unidade = COALESCE(excluded.unidade, produtos.unidade),
                   ean     = COALESCE(excluded.ean,     produtos.ean),
                   ncm     = COALESCE(excluded.ncm,     produtos.ncm),
                   cest    = COALESCE(excluded.cest,    produtos.cest)''',
            (p['cnpj_remetente'], p['cod_produto_origem'], p['descricao_produto'], p['unidade'],
             p['ean'] if pd.notna(p['ean']) else None,
             p['ncm'] if pd.notna(p['ncm']) else None,
             p['cest'] if pd.notna(p['cest']) else None),
        )

    # 2. Estado anterior (última competência conhecida ANTES de mes_ano, nessa trilha)
    cursor.execute(
        '''SELECT cnpj_remetente, cod_produto_origem, mes_ano, mod_bc_icms_st, mva
           FROM produto_competencia
           WHERE tipo_planilha = ? AND mes_ano < ?
           ORDER BY mes_ano ASC''',
        (tipo_planilha, mes_ano),
    )
    estado_anterior = {}
    for cnpj, cod, _mes, mod_bc, mva in cursor.fetchall():
        estado_anterior[(cnpj, cod)] = _estado(mod_bc, mva)

    # 3. Verifica se já existia uma carga para esta exata competência (reimportação/correção)
    cursor.execute(
        'SELECT COUNT(*) FROM produto_competencia WHERE tipo_planilha = ? AND mes_ano = ?',
        (tipo_planilha, mes_ano),
    )
    ja_existia = cursor.fetchone()[0] > 0

    # 4. Limpa a competência atual antes de regravar (garante idempotência)
    cursor.execute(
        'DELETE FROM produto_competencia WHERE tipo_planilha = ? AND mes_ano = ?',
        (tipo_planilha, mes_ano),
    )

    # 5. Decide o que gravar
    linhas_gravadas = 0
    linhas_inalteradas = 0
    for _, row in df.iterrows():
        chave = (row['cnpj_remetente'], row['cod_produto_origem'])
        novo_estado = _estado(row['mod_bc_icms_st'], row['mva'])

        if estado_anterior.get(chave) == novo_estado:
            linhas_inalteradas += 1
            continue

        cursor.execute(
            '''INSERT OR REPLACE INTO produto_competencia
                   (cnpj_remetente, cod_produto_origem, mes_ano, mod_bc_icms_st, pmc, mva, tipo_planilha)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (chave[0], chave[1], mes_ano, row['mod_bc_icms_st'], row['pmc'], row['mva'], tipo_planilha),
        )
        linhas_gravadas += 1

    if commit:
        conn.commit()

    aviso_recalculo = None
    if ja_existia:
        aviso_recalculo = (
            f'A competência {mes_ano} ({tipo_planilha}) já existia e foi recalculada. '
            f'Se a classificação de algum produto mudou aqui, competências POSTERIORES já '
            f'gravadas podem precisar ser reimportadas em ordem cronológica para refletir a mudança.'
        )

    return {
        'mes_ano': mes_ano,
        'tipo_planilha': tipo_planilha,
        'produtos_novos': produtos_novos,
        'linhas_gravadas': linhas_gravadas,
        'linhas_inalteradas': linhas_inalteradas,
        'total_linhas': len(df),
        'aviso_recalculo': aviso_recalculo,
    }
