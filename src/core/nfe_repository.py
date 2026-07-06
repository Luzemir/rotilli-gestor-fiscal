"""
nfe_repository.py — Persistência dos itens de NF-e importados

Responsabilidade:
  - Gravar cada item de NF-e classificado (ou pendente de classificação) em
    nfe_item_apuracao, de forma idempotente (reimportar o mesmo XML apenas
    sobrescreve a mesma linha, nunca duplica).
  - Servir de fonte de dados para a geração da planilha de apuração mensal
    (src/core/planilha_credito_outorgado.py), que relê TODOS os itens de uma
    competência já persistidos, não só o lote importado agora.
"""

COLUNAS = [
    'chave_acesso', 'num_item', 'mes_ano', 'tipo_planilha',
    'num_nf', 'data_emissao', 'cnpj_remetente', 'razao_remetente', 'uf_remetente',
    'cest', 'ncm', 'ean', 'cfop', 'cod_produto_origem', 'descricao_produto', 'unidade',
    'quantidade', 'valor_unitario', 'frete', 'seguro', 'ipi_despesas', 'desconto',
    'bc_icms_origem', 'vlr_icms_origem', 'pmc', 'pmc_cmed', 'mva', 'mod_bc_icms_st',
    'bc_icms_st_nfe', 'vlr_icms_st_nfe',
]


def _float_seguro(valor):
    try:
        return float(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None


def persistir_itens(conn, itens, mes_ano, tipo_planilha='Original', commit=True):
    """
    Grava cada item (classificado ou novo/sem cadastro) em nfe_item_apuracao
    via INSERT OR REPLACE, usando a chave (chave_acesso, num_item, tipo_planilha).
    Itens sem chave_acesso ou sem num_item são ignorados (não é possível
    persistir de forma idempotente sem essa chave).

    Retorna {'gravados': int, 'ignorados': int}.
    """
    cursor = conn.cursor()
    gravados = 0
    ignorados = 0

    placeholders = ', '.join(['?'] * len(COLUNAS))
    sql = f'INSERT OR REPLACE INTO nfe_item_apuracao ({", ".join(COLUNAS)}) VALUES ({placeholders})'

    for item in itens:
        if not item.get('chave_acesso') or not item.get('num_item'):
            ignorados += 1
            continue

        valores = (
            item.get('chave_acesso'),
            int(item.get('num_item')),
            mes_ano,
            tipo_planilha,
            item.get('num_nf'),
            item.get('data_emissao'),
            item.get('cnpj_emitente'),
            item.get('razao_remetente'),
            item.get('uf_remetente'),
            item.get('cest'),
            item.get('ncm'),
            item.get('ean'),
            item.get('cfop'),
            item.get('cod_produto'),
            item.get('descricao'),
            item.get('unidade'),
            _float_seguro(item.get('quantidade')),
            _float_seguro(item.get('valor_unitario')),
            _float_seguro(item.get('frete')),
            _float_seguro(item.get('seguro')),
            _float_seguro(item.get('ipi_despesas')),
            _float_seguro(item.get('desconto')),
            _float_seguro(item.get('bc_icms_origem')),
            _float_seguro(item.get('vlr_icms_origem')),
            _float_seguro(item.get('pmc')),
            _float_seguro(item.get('pmc_cmed')),
            _float_seguro(item.get('mva')),
            item.get('mod_bc_icms_st'),
            _float_seguro(item.get('bc_icms_st_nfe')),
            _float_seguro(item.get('vlr_icms_st_nfe')),
        )
        cursor.execute(sql, valores)
        gravados += 1

    if commit:
        conn.commit()

    return {'gravados': gravados, 'ignorados': ignorados}
