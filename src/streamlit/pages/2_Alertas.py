"""Página: Alertas — classificação manual de produtos novos"""
import re
import pandas as pd
import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from _config import get_conn, init_alertas_table, init_produtos_table, aplicar_tema_contili, page_header, MAPA_MOD_BC
from cmed_comparador import consultar_pmc_cmed


def _normalizar_mva(mva):
    """Garante MVA em fração decimal (ex: 0,3824 p/ 38,24%). Se digitado como
    percentual cheio por engano (>5, ou seja >500% em fração), corrige /100."""
    if mva is None:
        return None
    mva = float(mva)
    if mva > 5:
        mva = mva / 100
    return round(mva, 4)


def _reclassificar_alerta(ean, ncm, cest, bc_icms_origem, vlr_icms_origem, competencia, conn):
    """Pré-classificação inline — mesma lógica do nfe_parser._pre_classificar."""
    res = {'pre_mod_bc': None, 'pre_pmc': None, 'pre_mva': None, 'pre_nota': None}

    ncm_norm  = re.sub(r'[.\s]',   '', ncm  or '')
    cest_norm = re.sub(r'[.\s-]',  '', cest or '')

    cur = conn.cursor()

    row_cest = None
    if cest_norm:
        cur.execute(
            "SELECT mva_interno, mva_aliq4, mva_aliq7, mva_aliq12 "
            "FROM ncm_st WHERE cest_norm = ? LIMIT 1",
            (cest_norm,),
        )
        row_cest = cur.fetchone()

    row_ncm = None
    if ncm_norm and row_cest is None:
        cur.execute(
            "SELECT mva_interno, mva_aliq4, mva_aliq7, mva_aliq12 "
            "FROM ncm_st WHERE ? LIKE ncm_norm || '%' LIMIT 1",
            (ncm_norm,),
        )
        row_ncm = cur.fetchone()

    is_st   = (row_cest is not None) or (row_ncm is not None)
    mva_row = row_cest  # MVA só via CEST exato

    pmc_17, tipo_lista = None, None
    if ean and competencia:
        pmc_17, tipo_lista = consultar_pmc_cmed(ean, competencia, conn)

    ean_na_cmed = tipo_lista is not None

    if is_st and ean_na_cmed:
        if pmc_17 and pmc_17 > 0:
            res['pre_mod_bc'] = '0'
            res['pre_pmc']    = pmc_17
        else:
            mod = {'Positiva': '1', 'Negativa': '2', 'Neutra': '3'}.get(tipo_lista or '')
            if mod:
                res['pre_mod_bc'] = mod
            else:
                res['pre_nota'] = (
                    f'EAN na CMED mas PMC 17%=0 e lista não identificada '
                    f'({tipo_lista!r}). Classifique como MOD 1, 2 ou 3.'
                )

    elif is_st and not ean_na_cmed:
        res['pre_mod_bc'] = '4'
        if mva_row is not None:
            bc   = float(bc_icms_origem or 0)
            vlr  = float(vlr_icms_origem or 0)
            aliq = round(vlr / bc * 100) if bc > 0 else None
            if aliq is None:
                pass  # MVA vazio — usuário preenche manualmente
            elif aliq >= 15:
                res['pre_mva'] = round(mva_row[0] / 100, 4) if mva_row[0] is not None else None
            elif aliq >= 10:
                res['pre_mva'] = round(mva_row[3] / 100, 4) if mva_row[3] is not None else None
            elif aliq >= 5:
                res['pre_mva'] = round(mva_row[2] / 100, 4) if mva_row[2] is not None else None
            else:
                res['pre_mva'] = round(mva_row[1] / 100, 4) if mva_row[1] is not None else None

    elif not is_st and not ean_na_cmed:
        res['pre_mod_bc'] = '5'

    else:
        res['pre_mod_bc'] = '5'
        res['pre_nota'] = (
            f'NCM {ncm} fora do Subanexo ST, mas EAN na CMED '
            f'(PMC={pmc_17}, Lista={tipo_lista}). Verificar.'
        )

    return res


# ── Stopwords para busca por descrição ───────────────────────────────────────
_STOP_DESC = {
    'COM', 'PARA', 'UNI', 'UNID', 'MG', 'ML', 'UN', 'CX', 'KG', 'GR', 'PCT',
    'CAIXA', 'DE', 'DA', 'DO', 'E', 'A', 'O', 'EM', 'LT', 'COMP', 'CAP',
    'CPS', 'CPR', 'SOL', 'POM', 'AMP', 'BLI', 'ENV', 'KIT', 'SEM', 'COD',
    'REF', 'ITEM', 'TAB', 'GEL', 'SIR', 'INJ', 'OFT', 'OTO', 'NAL', 'DER',
    'FRAS', 'BISC', 'COMP', 'EMBA', 'LITRO', 'UNID', 'CXAS', 'GRS',
}


def _palavras_busca(desc: str) -> list:
    if not desc:
        return []
    tokens = re.findall(r'[A-Z0-9À-ÿ]{4,}', desc.upper())
    return [t for t in tokens if t not in _STOP_DESC][:6]


def _is_elegivel_lote(row) -> bool:
    """Retorna True se o alerta pode ser aceito em lote (sugestão completa, sem nota)."""
    mod = str(row['pre_mod_bc']) if row['pre_mod_bc'] is not None else None
    if mod is None or row['pre_nota']:
        return False
    if mod == '0':
        return float(row['pre_pmc'] or 0) > 0
    if mod == '4':
        return float(row['pre_mva'] or 0) > 0
    return mod in ('1', '2', '3', '5')


def _usar_similar_cb(alerta_id, mod, pmc, mva):
    """Callback: pré-preenche os widgets de classificação com dados de um produto similar."""
    mod_str = str(mod) if mod is not None else None
    pmc_f   = float(pmc or 0.0)
    mva_f   = float(mva or 0.0)
    for sufixo, val in [('mod', mod_str), ('pmc', pmc_f), ('mva', mva_f)]:
        st.session_state[f'_sel_{sufixo}_{alerta_id}'] = val
        st.session_state[f'{sufixo}_{alerta_id}']      = val


_SQL_SIM = '''
    SELECT p.cnpj_remetente, p.cod_produto_origem, p.descricao_produto,
           pc.mod_bc_icms_st, pc.pmc, pc.mva
    FROM produtos p
    LEFT JOIN produto_competencia pc
      ON  pc.cnpj_remetente     = p.cnpj_remetente
      AND pc.cod_produto_origem = p.cod_produto_origem
      AND pc.mes_ano = (
          SELECT MAX(m2.mes_ano) FROM produto_competencia m2
          WHERE m2.cnpj_remetente     = p.cnpj_remetente
            AND m2.cod_produto_origem = p.cod_produto_origem
      )
    WHERE pc.mod_bc_icms_st IS NOT NULL
      AND NOT (p.cnpj_remetente = ? AND p.cod_produto_origem = ?)
'''


def _buscar_produto_similar(ean, ncm, cest, descricao, ex_cnpj, ex_cod, conn):
    """
    Busca produtos cadastrados similares em 4 níveis de confiança.
    Retorna dict: ean_exato | ncm_cest | descricao | ncm_raiz → lista de dicts.
    """
    ncm_norm  = re.sub(r'[.\s]',  '', ncm  or '')
    cest_norm = re.sub(r'[.\s-]', '', cest or '')
    res = {'ean_exato': [], 'ncm_cest': [], 'descricao': [], 'ncm_raiz': []}

    # Nível 1 — EAN exato
    ean_v = str(ean or '').strip()
    if ean_v and ean_v.upper() not in ('', '—', 'SEM GTIN', 'SEMGTIN'):
        rows = conn.execute(
            _SQL_SIM + ' AND p.ean = ? LIMIT 5', (ex_cnpj, ex_cod, ean_v),
        ).fetchall()
        res['ean_exato'] = [dict(r) for r in rows]

    seen = {(r['cnpj_remetente'], r['cod_produto_origem']) for r in res['ean_exato']}

    # Nível 2 — NCM + CEST exatos (só quando o alerta traz CEST)
    if ncm and cest_norm:
        rows = conn.execute(
            _SQL_SIM + ' AND p.ncm = ? AND p.cest = ? LIMIT 5',
            (ex_cnpj, ex_cod, ncm, cest),
        ).fetchall()
        res['ncm_cest'] = [dict(r) for r in rows
                           if (r['cnpj_remetente'], r['cod_produto_origem']) not in seen]
        seen |= {(r['cnpj_remetente'], r['cod_produto_origem']) for r in res['ncm_cest']}

    # Nível 3 — Descrição similar (≥2 palavras significativas em comum)
    palavras = _palavras_busca(descricao)
    if palavras:
        contagem: dict = {}
        for palavra in palavras:
            for r in conn.execute(
                _SQL_SIM + ' AND p.descricao_produto LIKE ? LIMIT 30',
                (ex_cnpj, ex_cod, f'%{palavra}%'),
            ).fetchall():
                k = (r['cnpj_remetente'], r['cod_produto_origem'])
                if k not in contagem:
                    contagem[k] = {'row': dict(r), 'score': 0}
                contagem[k]['score'] += 1
        ranked = sorted(contagem.values(), key=lambda x: -x['score'])
        res['descricao'] = [
            x['row'] for x in ranked
            if x['score'] >= 2
            and (x['row']['cnpj_remetente'], x['row']['cod_produto_origem']) not in seen
        ][:5]
        seen |= {(r['cnpj_remetente'], r['cod_produto_origem']) for r in res['descricao']}

    # Nível 4 — NCM raiz (4 primeiros dígitos), só se não achou nos níveis 1 ou 2
    if ncm_norm and len(ncm_norm) >= 4 and not res['ean_exato'] and not res['ncm_cest']:
        rows = conn.execute(
            _SQL_SIM
            + " AND replace(replace(p.ncm, '.', ''), ' ', '') LIKE ? LIMIT 8",
            (ex_cnpj, ex_cod, ncm_norm[:4] + '%'),
        ).fetchall()
        res['ncm_raiz'] = [
            dict(r) for r in rows
            if (r['cnpj_remetente'], r['cod_produto_origem']) not in seen
        ][:5]

    return res


def _verificar_ncm_sem_cest(ncm, cest, conn) -> list:
    """Retorna entradas da ncm_st para o NCM quando CEST está ausente no alerta."""
    if cest and str(cest).strip():
        return []
    ncm_norm = re.sub(r'[.\s]', '', ncm or '')
    if not ncm_norm:
        return []
    return [dict(r) for r in conn.execute(
        "SELECT cest, descricao FROM ncm_st WHERE ? LIKE ncm_norm || '%' LIMIT 5",
        (ncm_norm,),
    ).fetchall()]


_AJUDA_MD = """
## Como funciona a página de Alertas

### O que são alertas?
Quando uma NF-e é importada, o sistema compara cada produto com o cadastro.
Produtos ainda **não cadastrados** geram um alerta para que o operador defina
a classificação tributária antes de a apuração de ICMS-ST poder ocorrer.

---

### Status dos alertas
| Status | Significado |
|---|---|
| **PENDENTE** | Aguarda classificação do operador |
| **CLASSIFICADO** | Produto incluído no cadastro com MOD definido |
| **IGNORADO** | Descartado manualmente (pode ser reaberto) |

---

### Critérios de classificação — MOD BC ICMS-ST
| MOD | Nome | Quando usar |
|---|---|---|
| **0** | PMC — Tabela CMED | Medicamento com PMC 17% cadastrado na CMED/Anvisa |
| **1** | Lista Positiva | Consta na CMED, sem PMC 17%, lista Positiva |
| **2** | Lista Negativa | Consta na CMED, sem PMC 17%, lista Negativa |
| **3** | Lista Neutra | Consta na CMED, sem PMC 17%, lista Neutra |
| **4** | MVA | Sujeito à ST via Subanexo, não está na CMED |
| **5** | Normal / Sem ST | Não está no Subanexo de Substituição Tributária |

> **MOD 0** exige o valor do PMC 17% (R$).
> **MOD 4** exige o valor do MVA (ex: 0,3512 = 35,12%).

---

### Sugestão automática 🤖
O motor consulta a CMED e a tabela NCM-ST automaticamente ao importar a NF-e
e sugere o MOD mais provável. A sugestão aparece em cada alerta com o ícone 🤖.

Alertas com **nota de atenção** (⚠️) têm conflito ou ambiguidade e precisam
de revisão manual — não entram no lote automático.

Use o botão **🔄 Reclassificar automaticamente** para refazer a sugestão
sem precisar reimportar a NF-e (útil após atualizar a tabela CMED ou NCM-ST).

---

### Classificação em lote ✅
O banner verde exibe quantos alertas têm **sugestão automática completa**
(MOD definido + PMC/MVA preenchidos quando necessário).

- **📋 Revisar lista** — veja os produtos antes de confirmar
- **Aceitar todos** — classifica todos de uma vez com as sugestões do motor

---

### Busca de produtos similares 🔍
Clique em **🔍 Buscar produtos similares no cadastro** dentro de cada alerta
para localizar produtos já classificados com características parecidas:

| Ícone | Critério | Confiança |
|---|---|---|
| 🟢 | EAN idêntico | Alta — mesmo produto |
| 🟡 | Mesmo NCM + CEST | Boa — mesma categoria tributária |
| 🟠 | Descrição similar | Contextual — verifique |
| 🔴 | NCM raiz | Baixa — NCM pode abranger categorias diferentes |

Clique **← Usar** para pré-preencher o formulário com a classificação do
produto similar encontrado.

---

### Aviso NCM sem CEST ⚠️
Quando o NCM consta na tabela ST mas a NF-e **não traz CEST**, o sistema
exibe um aviso laranja. Isso pode indicar que o produto **não pertence ao
regime ST** (exemplo: vitaminas com NCM compartilhado com bebidas preparadas).
Verifique sempre pela descrição e pela busca de similares antes de aceitar MOD 4.

---

### Filtros 🔍
Use o painel **Filtros** para restringir os alertas por NCM, CEST, EAN,
código do produto, CNPJ, descrição ou número de NF. Os filtros combinam
critério **E** (AND) e respeitam a paginação.
"""


st.set_page_config(page_title='Alertas', page_icon='🔔', layout='wide')
aplicar_tema_contili()
st.markdown(
    '<style>.stMarkdown code { font-size: 1em; }</style>',
    unsafe_allow_html=True,
)
init_alertas_table()
init_produtos_table()

col_cta = page_header(
    'Alertas — Produtos Novos',
    'Produtos detectados em NF-es que ainda não estão no cadastro. Classifique cada um para liberar a apuração.',
)
with col_cta:
    st.markdown('<div style="margin-top:8px"></div>', unsafe_allow_html=True)
    with st.popover('❓ Como usar', use_container_width=True):
        st.markdown(_AJUDA_MD)

# ── Filtro de status ─────────────────────────────────────────────────────────
status_filtro = st.radio(
    'Exibir alertas com status:',
    ['PENDENTE', 'CLASSIFICADO', 'IGNORADO'],
    horizontal=True,
)

# Reseta a página ao trocar o filtro de status
if st.session_state.get('_alertas_filtro') != status_filtro:
    st.session_state['alertas_page'] = 0
    st.session_state['_alertas_filtro'] = status_filtro

# ── Filtros de texto ──────────────────────────────────────────────────────────
_FK = ['f_ncm', 'f_cest', 'f_ean', 'f_cod', 'f_cnpj', 'f_desc', 'f_nf']
_FK_MAP = {
    'f_ncm':  'ncm',
    'f_cest': 'cest',
    'f_ean':  'ean',
    'f_cod':  'cod_produto',
    'f_cnpj': 'cnpj_emitente',
    'f_desc': 'descricao',
    'f_nf':   'num_nf',
}

def _limpar_filtros():
    for k in _FK:
        st.session_state[k] = ''
    st.session_state['alertas_page'] = 0

n_ativos = sum(1 for k in _FK if st.session_state.get(k, '').strip())
_label_exp = f'🔍 Filtros — {n_ativos} ativo(s)' if n_ativos else '🔍 Filtros'

with st.expander(_label_exp, expanded=(n_ativos > 0)):
    fa, fb, fc, fd = st.columns(4)
    fa.text_input('NCM',               key='f_ncm',  placeholder='ex: 3004')
    fb.text_input('CEST',              key='f_cest', placeholder='ex: 1300100')
    fc.text_input('EAN',               key='f_ean',  placeholder='ex: 7891...')
    fd.text_input('Código do produto', key='f_cod',  placeholder='ex: 001234')
    fe, ff, fg, fh = st.columns(4)
    fe.text_input('CNPJ Emitente',     key='f_cnpj', placeholder='ex: 12.345...')
    ff.text_input('Descrição',         key='f_desc', placeholder='busca parcial')
    fg.text_input('Nota Fiscal',       key='f_nf',   placeholder='ex: 000123')
    fh.markdown('<div style="margin-top:28px"></div>', unsafe_allow_html=True)
    fh.button('🗑️ Limpar filtros', on_click=_limpar_filtros, use_container_width=True)

# Reseta a página quando algum filtro muda
_filtros_hash = '|'.join(st.session_state.get(k, '') for k in _FK)
if st.session_state.get('_filtros_hash') != _filtros_hash:
    st.session_state['alertas_page'] = 0
    st.session_state['_filtros_hash'] = _filtros_hash

conn = get_conn()
rows = conn.execute(
    '''SELECT id, cnpj_emitente, cod_produto, ean, descricao, ncm, cest,
              num_nf, data_emissao, criado_em,
              pre_mod_bc, pre_pmc, pre_mva, pre_nota
       FROM produto_alerta WHERE status = ? ORDER BY criado_em DESC''',
    (status_filtro,),
).fetchall()
conn.close()

# Filtro Python-side — matching parcial case-insensitive por coluna
for _fk, _col in _FK_MAP.items():
    _val = st.session_state.get(_fk, '').strip().upper()
    if _val:
        rows = [r for r in rows if _val in str(r[_col] or '').upper()]

if not rows:
    st.info(
        f'Nenhum alerta com status **{status_filtro}**'
        + (' para os filtros aplicados.' if n_ativos else '.')
    )
    st.stop()

# ── Paginação ─────────────────────────────────────────────────────────────────
PAGE_SIZE = 20
total = len(rows)
n_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

if 'alertas_page' not in st.session_state:
    st.session_state['alertas_page'] = 0
page = min(st.session_state['alertas_page'], n_pages - 1)

rows_pagina = rows[page * PAGE_SIZE: (page + 1) * PAGE_SIZE]

col_info, col_prev, col_next = st.columns([4, 1, 1])
_legenda_total = f'{total} alerta(s)' + (' (filtrado)' if n_ativos else '')
col_info.caption(f'{_legenda_total} — página {page + 1} de {n_pages}')
if col_prev.button('◀ Anterior', disabled=(page == 0), use_container_width=True):
    st.session_state['alertas_page'] -= 1
    st.rerun()
if col_next.button('Próxima ▶', disabled=(page >= n_pages - 1), use_container_width=True):
    st.session_state['alertas_page'] += 1
    st.rerun()

# ── Módulo 1 — Aceitar sugestões em lote ─────────────────────────────────────
if status_filtro == 'PENDENTE':
    if 'confirmar_lote' not in st.session_state:
        st.session_state['confirmar_lote'] = False

    # Exibe resultado da última operação em lote
    if st.session_state.get('_lote_resultado'):
        _r_lt = st.session_state.pop('_lote_resultado')
        _msg_lt = f'✅ **{_r_lt["ok"]} produto(s) classificado(s)** com as sugestões automáticas.'
        if _r_lt['err']:
            _msg_lt += f' {_r_lt["err"]} com erro.'
        st.success(_msg_lt)

    # Exibe resultado da última classificação individual
    if st.session_state.get('_classif_resultado'):
        _r_ci = st.session_state.pop('_classif_resultado')
        st.success(
            f'✅ **{_r_ci["descricao"]}** classificado como '
            f'`MOD {_r_ci["mod"]} — {MAPA_MOD_BC.get(_r_ci["mod"], "?")}` e cadastrado.'
        )

    _elegiveis = [r for r in rows if _is_elegivel_lote(r)]
    if _elegiveis:
        _cnt_mod: dict = {}
        for _r in _elegiveis:
            _m = str(_r['pre_mod_bc'])
            _cnt_mod[_m] = _cnt_mod.get(_m, 0) + 1
        _resumo_mods = ' · '.join(f'MOD {k}: {v}' for k, v in sorted(_cnt_mod.items()))

        for _sfx in ('revisar_lote', 'confirmar_lote'):
            if _sfx not in st.session_state:
                st.session_state[_sfx] = False

        def _preparar_lote_todos():
            st.session_state['_lote_sel_indices'] = list(range(len(_elegiveis)))
            st.session_state['confirmar_lote'] = True

        def _preparar_lote_sel():
            editor   = st.session_state.get('revisar_lote_editor') or {}
            editados = editor.get('edited_rows', {})
            indices  = set(range(len(_elegiveis)))
            for _k, _ch in editados.items():
                if _ch.get('Classificar') is False:
                    indices.discard(int(_k))
            st.session_state['_lote_sel_indices'] = sorted(indices)
            st.session_state['confirmar_lote'] = True

        with st.container(border=True):
            _bc, _br, _bb = st.columns([4, 1, 1])
            _bc.markdown(
                f'**✅ {len(_elegiveis)} alerta(s) prontos para classificação em lote** '
                f'— sugestão automática completa  \n'
                f'<small>{_resumo_mods}</small>',
                unsafe_allow_html=True,
            )
            if _br.button('📋 Revisar lista', key='btn_revisar_lote', use_container_width=True):
                st.session_state['revisar_lote'] = not st.session_state['revisar_lote']
            _bb.button(
                'Aceitar todos', type='primary', key='btn_aceitar_lote',
                use_container_width=True,
                on_click=_preparar_lote_todos,
            )

        if st.session_state['revisar_lote']:
            _df_rev = pd.DataFrame([{
                'Classificar': True,
                'Descrição':   r['descricao'] or '—',
                'EAN':         r['ean'] or '—',
                'NCM':         r['ncm'] or '—',
                'CEST':        r['cest'] or '—',
                'MOD':         str(r['pre_mod_bc']),
                'PMC (R$)':    f"{float(r['pre_pmc']):.2f}" if r['pre_pmc'] else '—',
                'MVA':         f"{float(r['pre_mva']) * 100:.2f}%" if r['pre_mva'] else '—',
            } for r in _elegiveis])
            _df_edit = st.data_editor(
                _df_rev,
                use_container_width=True,
                hide_index=True,
                key='revisar_lote_editor',
                column_config={
                    'Classificar': st.column_config.CheckboxColumn(
                        '✓',
                        help='Desmarque para excluir da classificação em lote',
                        default=True,
                    ),
                },
                disabled=['Descrição', 'EAN', 'NCM', 'CEST', 'MOD', 'PMC (R$)', 'MVA'],
            )
            _n_sel = int(_df_edit['Classificar'].sum())
            _crev_txt, _crev_btn = st.columns([3, 1])
            _crev_txt.caption(
                f'{_n_sel} de {len(_elegiveis)} produto(s) selecionado(s).'
                + (' Desmarque os que não deseja classificar agora.' if _n_sel == len(_elegiveis) else '')
            )
            _crev_btn.button(
                f'Aceitar {_n_sel} selecionado(s)',
                type='primary',
                key='btn_aceitar_sel',
                use_container_width=True,
                disabled=(_n_sel == 0),
                on_click=_preparar_lote_sel,
            )

        _indices_lote    = st.session_state.get('_lote_sel_indices') or list(range(len(_elegiveis)))
        _elegiveis_proc  = [_elegiveis[i] for i in _indices_lote if i < len(_elegiveis)]

        if st.session_state['confirmar_lote']:
            _n_proc = len(_elegiveis_proc)
            st.warning(
                f'⚠️ Classificar **{_n_proc} produto(s)** com as sugestões automáticas. '
                'Esta ação não pode ser desfeita.'
            )
            _csim, _cnao = st.columns(2)
            if _csim.button('✅ Confirmar', type='primary', key='lote_sim',
                            use_container_width=True):
                _conn_lt = get_conn()
                _ok = _err_lt = 0
                try:
                    for _r in _elegiveis_proc:
                        _mod_lt  = str(_r['pre_mod_bc'])
                        _pmc_lt  = float(_r['pre_pmc']) if _mod_lt == '0' and _r['pre_pmc'] else None
                        _mva_lt  = _normalizar_mva(_r['pre_mva']) if _mod_lt == '4' and _r['pre_mva'] else None
                        try:
                            _nfe_lt = _conn_lt.execute(
                                'SELECT unidade FROM nfe_item_apuracao '
                                'WHERE cnpj_remetente = ? AND cod_produto_origem = ? LIMIT 1',
                                (_r['cnpj_emitente'], _r['cod_produto']),
                            ).fetchone()
                            _conn_lt.execute(
                                '''INSERT INTO produtos
                                       (cnpj_remetente, cod_produto_origem, descricao_produto,
                                        unidade, ean, ncm, cest)
                                   VALUES (?, ?, ?, ?, ?, ?, ?)
                                   ON CONFLICT(cnpj_remetente, cod_produto_origem) DO UPDATE SET
                                       unidade = COALESCE(excluded.unidade, produtos.unidade),
                                       ean     = COALESCE(excluded.ean,     produtos.ean),
                                       ncm     = COALESCE(excluded.ncm,     produtos.ncm),
                                       cest    = COALESCE(excluded.cest,    produtos.cest)''',
                                (_r['cnpj_emitente'], _r['cod_produto'], _r['descricao'],
                                 _nfe_lt['unidade'] if _nfe_lt else None,
                                 _r['ean'], _r['ncm'], _r['cest']),
                            )
                            _conn_lt.execute(
                                '''INSERT OR REPLACE INTO produto_competencia
                                       (cnpj_remetente, cod_produto_origem, mes_ano,
                                        mod_bc_icms_st, pmc, mva, tipo_planilha)
                                   VALUES (?, ?, strftime('%Y-%m', 'now'), ?, ?, ?, 'Original')''',
                                (_r['cnpj_emitente'], _r['cod_produto'],
                                 _mod_lt, _pmc_lt, _mva_lt),
                            )
                            _conn_lt.execute(
                                "UPDATE produto_alerta SET status='CLASSIFICADO' WHERE id=?",
                                (_r['id'],),
                            )
                            _ok += 1
                        except Exception:
                            _err_lt += 1
                    _conn_lt.commit()
                    for _k_lt in ('confirmar_lote', 'revisar_lote', '_lote_sel_indices', 'revisar_lote_editor'):
                        st.session_state.pop(_k_lt, None)
                    st.session_state['_lote_resultado'] = {'ok': _ok, 'err': _err_lt}
                    st.rerun()
                except Exception as _e_lt:
                    st.error(f'Erro no processamento em lote: {_e_lt}')
                finally:
                    _conn_lt.close()

            if _cnao.button('❌ Cancelar', key='lote_nao', use_container_width=True):
                for _k_lt in ('confirmar_lote', '_lote_sel_indices'):
                    st.session_state.pop(_k_lt, None)
                st.rerun()

_LABEL_PRE = {
    '0': 'PMC — Tabela CMED',
    '1': 'Lista Positiva',
    '2': 'Lista Negativa',
    '3': 'Lista Neutra',
    '4': 'MVA — Margem de Valor Agregado',
    '5': 'Normal / Sem ST',
}
opcoes_mod  = list(MAPA_MOD_BC.items())
opcoes_keys = [None] + [k for k, _ in opcoes_mod]   # None = "não classificado"

# ── Pré-carga de UF e alíquota para os alertas da página ─────────────────────
_conn_uf = get_conn()
_uf_aliq: dict = {}
for _r in rows_pagina:
    _nfe = _conn_uf.execute(
        'SELECT uf_remetente, bc_icms_origem, vlr_icms_origem '
        'FROM nfe_item_apuracao '
        'WHERE cnpj_remetente = ? AND cod_produto_origem = ? AND bc_icms_origem > 0 '
        'ORDER BY data_emissao DESC LIMIT 1',
        (_r['cnpj_emitente'], _r['cod_produto']),
    ).fetchone()
    if _nfe and _nfe['bc_icms_origem']:
        _aliq = round(_nfe['vlr_icms_origem'] / _nfe['bc_icms_origem'] * 100, 2) \
                if _nfe['vlr_icms_origem'] else 0.0
        _uf_aliq[(_r['cnpj_emitente'], _r['cod_produto'])] = (
            _nfe['uf_remetente'] or '—', f'{_aliq:.2f}%'
        )
    else:
        _uf_aliq[(_r['cnpj_emitente'], _r['cod_produto'])] = ('—', '—')
_conn_uf.close()

# ── Loop de alertas ──────────────────────────────────────────────────────────
for row in rows_pagina:
    alerta_id = row['id']
    ncm_exib  = row['ncm']  or '—'
    cest_exib = row['cest'] or '—'
    pre_mod_db = str(row['pre_mod_bc']) if row['pre_mod_bc'] is not None else None
    pre_pmc_db = float(row['pre_pmc'] or 0.0)
    pre_mva_db = float(row['pre_mva'] or 0.0)  # decimal no BD (ex: 0.3417)

    # Chaves customizadas (non-widget) persistem mesmo quando o Streamlit limpa
    # widget-keys num run interrompido por st.rerun() de outro item do loop.
    _sk_mod = f'_sel_mod_{alerta_id}'
    _sk_pmc = f'_sel_pmc_{alerta_id}'
    _sk_mva = f'_sel_mva_{alerta_id}'
    if _sk_mod not in st.session_state:
        st.session_state[_sk_mod] = pre_mod_db
        st.session_state[_sk_pmc] = pre_pmc_db
        st.session_state[_sk_mva] = pre_mva_db
    # Restaura widget-keys se foram limpas (itens abaixo do item classificado)
    if f'mod_{alerta_id}' not in st.session_state:
        st.session_state[f'mod_{alerta_id}'] = st.session_state[_sk_mod]
    if f'pmc_{alerta_id}' not in st.session_state:
        st.session_state[f'pmc_{alerta_id}'] = st.session_state[_sk_pmc]
    if f'mva_{alerta_id}' not in st.session_state:
        st.session_state[f'mva_{alerta_id}'] = st.session_state[_sk_mva]

    with st.expander(
        f"📦 {row['descricao'] or '(sem descrição)'} "
        f"— Cód: {row['cod_produto']} | EAN: {row['ean'] or '—'} "
        f"| NCM: {ncm_exib} | CEST: {cest_exib} | NF: {row['num_nf']}",
        expanded=(status_filtro == 'PENDENTE'),
    ):
        _uf_val, _aliq_val = _uf_aliq.get((row['cnpj_emitente'], row['cod_produto']), ('—', '—'))
        c1, c2 = st.columns([2, 1])
        c1.markdown(f"""
**CNPJ Emitente:** `{row['cnpj_emitente']}`
**Código do produto:** `{row['cod_produto']}`
**EAN:** `{row['ean'] or '—'}`
**NCM:** `{ncm_exib}` &nbsp;&nbsp; **CEST:** `{cest_exib}`
**UF Emitente:** `{_uf_val}` &nbsp;&nbsp; **Alíquota ICMS:** `{_aliq_val}`
**Descrição:** {row['descricao'] or '—'}
**Nota Fiscal:** {row['num_nf']} &nbsp;&nbsp; **Emissão:** {(row['data_emissao'] or '')[:10]}
**Detectado em:** {(row['criado_em'] or '')[:16]}
""")
        if pre_mod_db is not None and (pre_mod_db != '5' or pre_pmc_db or pre_mva_db):
            pre_label = _LABEL_PRE.get(pre_mod_db, MAPA_MOD_BC.get(pre_mod_db, '?'))
            pre_info  = f'🤖 **Sugestão automática:** `{pre_mod_db} — {pre_label}`'
            if pre_mod_db == '0' and pre_pmc_db:
                pre_info += f' | PMC CMED: **R$ {pre_pmc_db:.2f}**'
            elif pre_mod_db == '4' and pre_mva_db:
                pre_info += f' | MVA: **{pre_mva_db * 100:.2f}%**'
            c1.caption(pre_info)
        if row['pre_nota']:
            c1.warning(f"⚠️ {row['pre_nota']}")

        with c2:
            if status_filtro == 'PENDENTE':
                mod_sel = st.selectbox(
                    'Mod. BC ICMS-ST',
                    options=opcoes_keys,
                    format_func=lambda k: '— não classificado —' if k is None
                                          else f'{k} — {MAPA_MOD_BC[k]}',
                    key=f'mod_{alerta_id}',
                )
                st.session_state[_sk_mod] = mod_sel  # atualiza chave customizada

                pmc_val, mva_val = None, None
                if mod_sel == '0':
                    pmc_val = st.number_input(
                        'PMC 17% (R$)', min_value=0.0, step=0.01,
                        format='%.2f',
                        key=f'pmc_{alerta_id}',
                    )
                    st.session_state[_sk_pmc] = pmc_val
                elif mod_sel == '4':
                    mva_val = st.number_input(
                        'MVA', min_value=0.0, step=0.0001,
                        format='%.4f',
                        help='Informe em decimal — ex: 0,3824 para 38,24%',
                        key=f'mva_{alerta_id}',
                    )
                    st.session_state[_sk_mva] = mva_val

                col_salvar, col_ignorar = st.columns(2)

                _mod_invalido = mod_sel is None
                _pmc_invalido = mod_sel == '0' and (not pmc_val or pmc_val <= 0)
                _mva_invalido = mod_sel == '4' and (not mva_val or mva_val <= 0)
                if _mod_invalido:
                    st.error('Selecione um MOD para classificar o produto.')
                elif _pmc_invalido:
                    st.error('PMC 17% obrigatório para MOD 0 — Tabela CMED. Informe o valor antes de classificar.')
                elif _mva_invalido:
                    st.error('MVA obrigatório para MOD 4. Informe o valor antes de classificar.')

                if col_salvar.button('✅ Classificar', key=f'salvar_{alerta_id}', type='primary',
                                     disabled=(_mod_invalido or _pmc_invalido or _mva_invalido)):
                    # Guard server-side: protege contra race-condition de re-render
                    if mod_sel is None:
                        st.error('MOD BC é obrigatório. Selecione antes de classificar.')
                        st.stop()
                    if mod_sel == '0' and (not pmc_val or pmc_val <= 0):
                        st.error('PMC 17% obrigatório para MOD 0.')
                        st.stop()
                    if mod_sel == '4' and (not mva_val or mva_val <= 0):
                        st.error('MVA obrigatório para MOD 4.')
                        st.stop()
                    conn = get_conn()
                    try:
                        row_nfe = conn.execute(
                            'SELECT unidade FROM nfe_item_apuracao '
                            'WHERE cnpj_remetente = ? AND cod_produto_origem = ? LIMIT 1',
                            (row['cnpj_emitente'], row['cod_produto']),
                        ).fetchone()
                        unidade_val = row_nfe['unidade'] if row_nfe else None
                        conn.execute(
                            '''INSERT INTO produtos
                                   (cnpj_remetente, cod_produto_origem, descricao_produto,
                                    unidade, ean, ncm, cest)
                               VALUES (?, ?, ?, ?, ?, ?, ?)
                               ON CONFLICT(cnpj_remetente, cod_produto_origem) DO UPDATE SET
                                   unidade = COALESCE(excluded.unidade, produtos.unidade),
                                   ean     = COALESCE(excluded.ean,     produtos.ean),
                                   ncm     = COALESCE(excluded.ncm,     produtos.ncm),
                                   cest    = COALESCE(excluded.cest,    produtos.cest)''',
                            (row['cnpj_emitente'], row['cod_produto'],
                             row['descricao'], unidade_val,
                             row['ean'], row['ncm'], row['cest']),
                        )
                        conn.execute(
                            '''INSERT OR REPLACE INTO produto_competencia
                                   (cnpj_remetente, cod_produto_origem, mes_ano,
                                    mod_bc_icms_st, pmc, mva, tipo_planilha)
                               VALUES (?, ?, strftime('%Y-%m', 'now'), ?, ?, ?, 'Original')''',
                            (row['cnpj_emitente'], row['cod_produto'],
                             mod_sel,
                             pmc_val,
                             _normalizar_mva(mva_val)),
                        )
                        conn.execute(
                            "UPDATE produto_alerta SET status='CLASSIFICADO' WHERE id=?",
                            (alerta_id,),
                        )
                        conn.commit()
                        st.session_state['_classif_resultado'] = {
                            'descricao': row['descricao'] or row['cod_produto'],
                            'mod': mod_sel,
                        }
                        st.rerun()
                    except Exception as e:
                        st.error(f'Erro ao salvar: {e}')
                    finally:
                        conn.close()

                if col_ignorar.button('🚫 Ignorar', key=f'ignorar_{alerta_id}'):
                    conn = get_conn()
                    conn.execute(
                        "UPDATE produto_alerta SET status='IGNORADO' WHERE id=?", (alerta_id,)
                    )
                    conn.commit()
                    conn.close()
                    st.rerun()

                if st.button(
                    '🔄 Reclassificar automaticamente',
                    key=f'reclassificar_{alerta_id}',
                    help='Re-executa a pré-classificação sem precisar reimportar a NF-e',
                ):
                    _conn_rc = get_conn()
                    try:
                        _nfe_rc = _conn_rc.execute(
                            'SELECT bc_icms_origem, vlr_icms_origem, mes_ano '
                            'FROM nfe_item_apuracao '
                            'WHERE cnpj_remetente = ? AND cod_produto_origem = ? '
                            'AND bc_icms_origem > 0 '
                            'ORDER BY data_emissao DESC LIMIT 1',
                            (row['cnpj_emitente'], row['cod_produto']),
                        ).fetchone()

                        _competencia_rc = (
                            _nfe_rc['mes_ano'] if _nfe_rc
                            else (row['data_emissao'] or '')[:7] or None
                        )

                        _res = _reclassificar_alerta(
                            ean=row['ean'], ncm=row['ncm'], cest=row['cest'],
                            bc_icms_origem=_nfe_rc['bc_icms_origem']  if _nfe_rc else None,
                            vlr_icms_origem=_nfe_rc['vlr_icms_origem'] if _nfe_rc else None,
                            competencia=_competencia_rc,
                            conn=_conn_rc,
                        )

                        _conn_rc.execute(
                            '''UPDATE produto_alerta
                               SET pre_mod_bc = ?, pre_pmc = ?, pre_mva = ?, pre_nota = ?
                               WHERE id = ? AND status = 'PENDENTE' ''',
                            (_res['pre_mod_bc'], _res['pre_pmc'],
                             _res['pre_mva'], _res['pre_nota'],
                             alerta_id),
                        )
                        _conn_rc.commit()
                        st.session_state.pop(f'_sel_mod_{alerta_id}', None)
                        st.session_state.pop(f'_sel_pmc_{alerta_id}', None)
                        st.session_state.pop(f'_sel_mva_{alerta_id}', None)
                        st.rerun()
                    except Exception as _e:
                        st.error(f'Erro ao reclassificar: {_e}')
                    finally:
                        _conn_rc.close()

            else:
                st.caption('Alerta já resolvido.')
                if st.button('↩ Reabrir como Pendente', key=f'reabrir_{alerta_id}'):
                    conn = get_conn()
                    conn.execute(
                        "UPDATE produto_alerta SET status='PENDENTE' WHERE id=?", (alerta_id,)
                    )
                    conn.commit()
                    conn.close()
                    st.rerun()

        # ── Módulos 2 + 3: Aviso NCM ambíguo e busca de similares ────────────
        if status_filtro == 'PENDENTE':
            _conn_aux = get_conn()
            try:
                _ambiguos = _verificar_ncm_sem_cest(row['ncm'], row['cest'], _conn_aux)
            finally:
                _conn_aux.close()

            if _ambiguos:
                _cests_txt = ', '.join(
                    f"`{a['cest']}`" for a in _ambiguos if a.get('cest')
                )
                st.warning(
                    f'⚠️ **NCM `{ncm_exib}` está mapeado na tabela ST**, mas este produto '
                    f'não traz CEST na NF-e. Verifique se realmente pertence ao regime de '
                    f'Substituição Tributária antes de classificar como MOD 4.'
                    + (f'  \nCESTs ST mapeados para este NCM: {_cests_txt}.' if _cests_txt else '')
                )

            _sim_key = f'_sim_{alerta_id}'
            if _sim_key not in st.session_state:
                st.session_state[_sim_key] = False

            if st.button(
                '🔍 Buscar produtos similares no cadastro',
                key=f'btn_sim_{alerta_id}',
                help='Localiza produtos já classificados com EAN, NCM/CEST ou descrição similares',
            ):
                st.session_state[_sim_key] = not st.session_state[_sim_key]

            if st.session_state[_sim_key]:
                _conn_s = get_conn()
                try:
                    _sims = _buscar_produto_similar(
                        ean=row['ean'], ncm=row['ncm'], cest=row['cest'],
                        descricao=row['descricao'],
                        ex_cnpj=row['cnpj_emitente'], ex_cod=row['cod_produto'],
                        conn=_conn_s,
                    )
                finally:
                    _conn_s.close()

                if not any(_sims[k] for k in _sims):
                    st.info('Nenhum produto similar encontrado no cadastro.')
                else:
                    st.divider()
                    st.caption('**Produtos similares encontrados no cadastro**')
                    for _nivel, _icone, _titulo, _aviso_nivel in [
                        ('ean_exato', '🟢', 'EAN idêntico', None),
                        ('ncm_cest',  '🟡', 'Mesmo NCM + CEST', None),
                        ('descricao', '🟠', 'Descrição similar', None),
                        ('ncm_raiz',  '🔴', 'NCM raiz',
                         'O mesmo NCM pode abranger produtos de categorias diferentes. '
                         'Confirme pela descrição antes de usar.'),
                    ]:
                        _lista_sim = _sims[_nivel]
                        if not _lista_sim:
                            continue
                        st.caption(f'{_icone} **{_titulo}**')
                        if _aviso_nivel:
                            st.caption(f'⚠️ {_aviso_nivel}')
                        for _idx, _sim in enumerate(_lista_sim):
                            _mod_s  = _sim.get('mod_bc_icms_st')
                            _pmc_s  = _sim.get('pmc')
                            _mva_s  = _sim.get('mva')
                            _desc_s = _sim.get('descricao_produto') or '—'
                            _mod_label = (
                                f'MOD {_mod_s} — {MAPA_MOD_BC.get(str(_mod_s), "?")}'
                                if _mod_s else '—'
                            )
                            _val_extra = ''
                            if _mod_s == '0' and _pmc_s:
                                _val_extra = f' · PMC R$ {float(_pmc_s):.2f}'
                            elif _mod_s == '4' and _mva_s:
                                _val_extra = f' · MVA {float(_mva_s) * 100:.2f}%'
                            _ca, _cb = st.columns([5, 1])
                            _ca.markdown(f'{_desc_s}  \n`{_mod_label}{_val_extra}`')
                            if _mod_s:
                                _cb.button(
                                    '← Usar',
                                    key=f'usar_{alerta_id}_{_nivel}_{_idx}',
                                    on_click=_usar_similar_cb,
                                    kwargs={
                                        'alerta_id': alerta_id,
                                        'mod': _mod_s,
                                        'pmc': _pmc_s,
                                        'mva': _mva_s,
                                    },
                                    use_container_width=True,
                                )
