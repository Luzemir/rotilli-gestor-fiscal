"""Página: Consulta de Produtos"""
import streamlit as st
import pandas as pd
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from _config import get_conn, MAPA_MOD_BC, aplicar_tema_contili, page_header, init_produtos_table

from competencia_importer import (
    importar_competencia,
    classificar_arquivo_historico,
)


def _normalizar_mva(mva):
    """Garante MVA em fração decimal (ex: 0,3824 p/ 38,24%). Se digitado como
    percentual cheio por engano (>5, ou seja >500% em fração), corrige /100."""
    if mva is None:
        return None
    mva = float(mva)
    if mva > 5:
        mva = mva / 100
    return round(mva, 4)


def _exibir_relatorio(relatorio: dict) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Produtos novos',       relatorio['produtos_novos'])
    c2.metric('Linhas gravadas',       relatorio['linhas_gravadas'])
    c3.metric('Inalteradas (dedup)',   relatorio['linhas_inalteradas'])
    c4.metric('Total no arquivo',      relatorio['total_linhas'])
    if relatorio['aviso_recalculo']:
        st.warning(relatorio['aviso_recalculo'])


@st.dialog('Arquivo rejeitado')
def _popup_rejeicao(chave: str, motivo: str):
    st.error(motivo)
    if st.button('Fechar', type='primary', use_container_width=True):
        st.session_state[chave] = None
        st.rerun()


def _validar_arquivo(arquivo, ano: str, mes: str, tipo: str):
    import re as _re
    nome = arquivo.name
    if tipo.lower() not in nome.lower():
        return False, (
            f"O arquivo **{nome}** não contém a palavra **'{tipo}'** no nome. "
            f"Selecione o arquivo da planilha **{tipo}**."
        )
    competencia = f'{ano}_{mes}'
    m = _re.search(r'(\d{4})_(\d{2})', nome)
    if not m:
        return False, (
            f"O arquivo **{nome}** não contém a competência no nome. "
            f"Padrão esperado: `RegimeEspecialMS_{competencia}_{tipo}.xlsm`."
        )
    comp_arquivo = f'{m.group(1)}_{m.group(2)}'
    if comp_arquivo != competencia:
        return False, (
            f"A competência do arquivo é **{comp_arquivo}** "
            f"mas a competência selecionada é **{competencia}**. "
            f"Verifique o mês/ano ou escolha o arquivo correto."
        )
    return True, None


# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title='Produtos', page_icon='🔍', layout='wide')
aplicar_tema_contili()
init_produtos_table()

page_header(
    'Produtos',
    'Cadastro de produtos e suas classificações históricas de ICMS-ST. Clique em uma linha para ver o histórico.',
)

# ── Session state ─────────────────────────────────────────────────────────────
for _k, _v in [
    ('prod_chave', ''), ('modo_edicao', False), ('aguardando_excluir', False),
    ('_orig_key', 0), ('_ajus_key', 0),
    ('_rejeicao_orig', None), ('_rejeicao_ajus', None),
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── 1. Busca + Tabela ─────────────────────────────────────────────────────────
cb, co = st.columns([4, 1])
busca = cb.text_input('Buscar por nome, código, CNPJ, EAN, NCM ou CEST',
                      placeholder='Digite qualquer termo...')
ordem = co.radio('Ordenar por', ['Alfabético', '🕒 Mais recentes'], horizontal=False,
                 label_visibility='collapsed',
                 help='Mais recentes = ordem de inserção no sistema',
                 key='radio_ordem')

# Resetar página para 1 quando a ordenação mudar
if st.session_state.get('_ultima_ordem') != ordem:
    st.session_state['_ultima_ordem'] = ordem
    st.session_state['numero_pagina'] = 1

ORDER_BY = 'rowid DESC' if ordem == '🕒 Mais recentes' else 'descricao_produto'

CAMPOS_BUSCA = (
    'descricao_produto LIKE ? OR cod_produto_origem LIKE ? '
    'OR cnpj_remetente LIKE ? OR ean LIKE ? OR ncm LIKE ? OR cest LIKE ?'
)

conn = get_conn()
cur  = conn.cursor()

if busca:
    like         = f'%{busca}%'
    params_busca = (like, like, like, like, like, like)
    total = cur.execute(
        f'SELECT COUNT(*) FROM produtos WHERE {CAMPOS_BUSCA}', params_busca,
    ).fetchone()[0]
else:
    total = cur.execute('SELECT COUNT(*) FROM produtos').fetchone()[0]

POR_PAGINA = 50
n_paginas  = max(1, -(-total // POR_PAGINA))

_c_info, _c_pag = st.columns([3, 1])
_c_info.caption(f'{total:,} produto(s) encontrado(s). Ordem: **{"A→Z" if ordem == "Alfabético" else "mais recente primeiro"}**')
pagina = _c_pag.number_input('Página', min_value=1, max_value=n_paginas, value=1, step=1,
                             label_visibility='collapsed', key='numero_pagina')
offset = (pagina - 1) * POR_PAGINA

_COLS_SEL = 'cnpj_remetente, cod_produto_origem, descricao_produto, unidade, ean, ncm, cest, criado_em'

if busca:
    rows = cur.execute(
        f'SELECT {_COLS_SEL} FROM produtos WHERE {CAMPOS_BUSCA} '
        f'ORDER BY {ORDER_BY} LIMIT ? OFFSET ?',
        (like, like, like, like, like, like, POR_PAGINA, offset),
    ).fetchall()
else:
    rows = cur.execute(
        f'SELECT {_COLS_SEL} FROM produtos ORDER BY {ORDER_BY} LIMIT ? OFFSET ?',
        (POR_PAGINA, offset),
    ).fetchall()

conn.close()

_colunas_df = ['CNPJ Emitente', 'Código', 'Descrição', 'Unidade', 'EAN', 'NCM', 'CEST', 'Cadastrado em']
df = pd.DataFrame(rows, columns=_colunas_df)
df['Cadastrado em'] = (
    pd.to_datetime(df['Cadastrado em'], errors='coerce')
    .dt.strftime('%d/%m/%Y')
    .fillna('—')
)

evento = st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    on_select='rerun',
    selection_mode='single-row',
    key='tabela_produtos',
)
st.caption(f'Página {pagina} de {n_paginas}')

# ── 2. Detalhe do produto selecionado ─────────────────────────────────────────
st.divider()

linhas_selecionadas = evento.selection.rows if evento and evento.selection else []

if linhas_selecionadas and linhas_selecionadas[0] < len(df):
    sel = df.iloc[linhas_selecionadas[0]]
    cnpj_sel, cod_sel = sel['CNPJ Emitente'], sel['Código']

    # Reseta modos ao trocar de produto
    chave_atual = f'{cnpj_sel}|{cod_sel}'
    if st.session_state.prod_chave != chave_atual:
        st.session_state.prod_chave         = chave_atual
        st.session_state.modo_edicao        = False
        st.session_state.aguardando_excluir = False

    st.subheader('📄 Histórico de Classificação')
    st.markdown(
        f"**{sel['Descrição']}** — Código `{cod_sel}` · CNPJ `{cnpj_sel}`"
    )

    # ── Histórico pivotado ────────────────────────────────────────────────────
    conn = get_conn()
    hist = conn.execute(
        '''SELECT mes_ano, mod_bc_icms_st, pmc, mva, tipo_planilha
           FROM produto_competencia
           WHERE cnpj_remetente = ? AND cod_produto_origem = ?
           ORDER BY mes_ano DESC, tipo_planilha''',
        (cnpj_sel, cod_sel),
    ).fetchall()
    conn.close()

    if hist:
        df_all = pd.DataFrame(hist, columns=['mes_ano', 'mod_bc', 'pmc', 'mva', 'tipo'])
        df_all['clasf'] = df_all['mod_bc'].astype(str).apply(
            lambda m: f"{m} — {MAPA_MOD_BC[m]}" if m in MAPA_MOD_BC else f"{m} — ?"
        )
        df_all['pmc_s'] = df_all['pmc'].apply(
            lambda v: f'{v:.2f}' if pd.notna(v) and v is not None else '—'
        )
        df_all['mva_s'] = df_all['mva'].apply(
            lambda v: f'{v:.2f}' if pd.notna(v) and v is not None else '—'
        )

        df_orig = (
            df_all[df_all['tipo'] == 'Original'][['mes_ano', 'clasf', 'pmc_s', 'mva_s']]
            .drop_duplicates('mes_ano').set_index('mes_ano')
            .rename(columns={'clasf': 'Classificação Original',
                             'pmc_s': 'PMC (R$)', 'mva_s': 'MVA Original (%)'})
        )
        df_ajus = (
            df_all[df_all['tipo'] == 'Ajustada'][['mes_ano', 'clasf', 'pmc_s', 'mva_s']]
            .drop_duplicates('mes_ano').set_index('mes_ano')
            .rename(columns={'clasf': 'Classificação Ajustada',
                             'pmc_s': 'PMC Ajustada (R$)', 'mva_s': 'MVA Ajustada (%)'})
        )

        todas = sorted(set(df_all['mes_ano']), reverse=True)
        df_pivot = pd.DataFrame(index=todas)
        df_pivot.index.name = 'Competência'
        df_pivot = df_pivot.join(df_orig, how='left').join(df_ajus, how='left')
        df_pivot[['Classificação Ajustada', 'PMC Ajustada (R$)', 'MVA Ajustada (%)']] = (
            df_pivot[['Classificação Ajustada', 'PMC Ajustada (R$)', 'MVA Ajustada (%)']].fillna('# Sem Valor')
        )
        df_pivot = df_pivot.fillna('—').reset_index()

        st.caption(
            '**Original** = RegimeEspecial Original · '
            '**Ajustada** = RegimeEspecial Ajustada · '
            '`# Sem Valor` = ainda não importada'
        )
        st.dataframe(df_pivot, use_container_width=True, hide_index=True)
    else:
        st.info('Nenhuma competência registrada para esse produto.')

    # ── Editar competência do histórico ──────────────────────────────────────
    with st.expander('✏️ Editar competência do histórico'):
        if not hist:
            st.info('Nenhuma competência registrada para editar.')
        else:
            periodos_he = sorted({r[0] for r in hist}, reverse=True)
            col_pe, col_te = st.columns(2)
            mes_he  = col_pe.selectbox('Competência', periodos_he,
                                       key=f'he_mes_{cnpj_sel}_{cod_sel}')
            tipo_he = col_te.radio('Tipo', ['Original', 'Ajustada'], horizontal=True,
                                   key=f'he_tipo_{cnpj_sel}_{cod_sel}')

            conn_he = get_conn()
            row_he = conn_he.execute(
                'SELECT mod_bc_icms_st, pmc, mva FROM produto_competencia '
                'WHERE cnpj_remetente = ? AND cod_produto_origem = ? '
                'AND mes_ano = ? AND tipo_planilha = ?',
                (cnpj_sel, cod_sel, mes_he, tipo_he),
            ).fetchone()
            conn_he.close()

            if row_he:
                _keys_he = list(MAPA_MOD_BC.keys())
                _mod_raw = row_he['mod_bc_icms_st']
                if _mod_raw is None:
                    st.warning(
                        'Competência salva sem MOD definido. '
                        'Selecione a classificação correta abaixo.'
                    )
                    _mod_atual = _keys_he[0]
                else:
                    _mod_atual = str(_mod_raw)
                _idx_he = _keys_he.index(_mod_atual) if _mod_atual in _keys_he else 0

                mod_he = st.selectbox(
                    'Classificação (Mod. BC)',
                    options=_keys_he,
                    format_func=lambda k: f'{k} — {MAPA_MOD_BC[k]}',
                    index=_idx_he,
                    key=f'he_mod_{cnpj_sel}_{cod_sel}',
                )

                pmc_he = mva_he = None
                with st.form(f'form_hist_{cnpj_sel}_{cod_sel}'):
                    if mod_he in ('0', '1', '2', '3'):
                        pmc_he = st.number_input('PMC (R$)',
                                                  value=float(row_he['pmc'] or 0.0),
                                                  min_value=0.0, step=0.01, format='%.2f')
                    elif mod_he == '4':
                        mva_he = st.number_input('MVA',
                                                  value=float(row_he['mva'] or 0.0),
                                                  min_value=0.0, step=0.0001, format='%.4f',
                                                  help='Informe em decimal — ex: 0,3824 para 38,24%')
                    else:
                        st.info('Mod. BC 5 — Normal/Sem ST. Nenhum valor adicional necessário.')
                    salvar_he = st.form_submit_button('💾 Salvar competência',
                                                       type='primary', use_container_width=True)

                if salvar_he:
                    conn_he = get_conn()
                    conn_he.execute(
                        'UPDATE produto_competencia SET mod_bc_icms_st = ?, pmc = ?, mva = ? '
                        'WHERE cnpj_remetente = ? AND cod_produto_origem = ? '
                        'AND mes_ano = ? AND tipo_planilha = ?',
                        (mod_he, pmc_he, _normalizar_mva(mva_he), cnpj_sel, cod_sel, mes_he, tipo_he),
                    )
                    conn_he.commit()
                    conn_he.close()
                    st.success(f'Competência {mes_he} ({tipo_he}) atualizada.')
                    st.rerun()
            else:
                st.info(f'Nenhum registro {tipo_he} para {mes_he}.')

    # ── Botões de ação ────────────────────────────────────────────────────────
    st.divider()
    if not st.session_state.modo_edicao and not st.session_state.aguardando_excluir:
        col_ed, col_del, _ = st.columns([1, 1, 4])
        if col_ed.button('✏️ Editar produto', use_container_width=True):
            st.session_state.modo_edicao = True
            st.rerun()
        if col_del.button('🗑️ Excluir produto', use_container_width=True):
            st.session_state.aguardando_excluir = True
            st.rerun()

    # ── Formulário de edição ──────────────────────────────────────────────────
    if st.session_state.modo_edicao:
        st.markdown('**Editar produto** — CNPJ Emitente e Código são somente leitura.')
        conn_ed = get_conn()
        prod_db = conn_ed.execute(
            'SELECT descricao_produto, unidade, ean, ncm, cest FROM produtos '
            'WHERE cnpj_remetente = ? AND cod_produto_origem = ?',
            (cnpj_sel, cod_sel),
        ).fetchone()
        conn_ed.close()

        with st.form('form_editar_produto'):
            st.text_input('CNPJ Emitente', value=cnpj_sel, disabled=True)
            st.text_input('Código',        value=cod_sel,  disabled=True)
            nova_desc = st.text_input('Descrição', value=prod_db['descricao_produto'] or '')
            col_u, col_e = st.columns(2)
            nova_unid = col_u.text_input('Unidade', value=prod_db['unidade'] or '', max_chars=10)
            novo_ean  = col_e.text_input('EAN',     value=prod_db['ean']     or '', max_chars=30)
            col_n, col_c2 = st.columns(2)
            novo_ncm  = col_n.text_input('NCM',  value=prod_db['ncm']  or '', max_chars=20)
            novo_cest = col_c2.text_input('CEST', value=prod_db['cest'] or '', max_chars=20)
            col_s, col_c = st.columns(2)
            salvar   = col_s.form_submit_button('💾 Salvar',    type='primary', use_container_width=True)
            cancelar = col_c.form_submit_button('❌ Cancelar',  use_container_width=True)

        if salvar:
            conn_ed = get_conn()
            conn_ed.execute(
                'UPDATE produtos SET descricao_produto = ?, unidade = ?, ean = ?, ncm = ?, cest = ? '
                'WHERE cnpj_remetente = ? AND cod_produto_origem = ?',
                (nova_desc.strip(), nova_unid.strip() or None,
                 novo_ean.strip() or None, novo_ncm.strip() or None, novo_cest.strip() or None,
                 cnpj_sel, cod_sel),
            )
            conn_ed.commit()
            conn_ed.close()
            st.success('Produto atualizado com sucesso.')
            st.session_state.modo_edicao = False
            st.rerun()

        if cancelar:
            st.session_state.modo_edicao = False
            st.rerun()

    # ── Confirmação de exclusão ───────────────────────────────────────────────
    if st.session_state.aguardando_excluir:
        conn_del = get_conn()
        n_comp  = conn_del.execute(
            'SELECT COUNT(*) FROM produto_competencia '
            'WHERE cnpj_remetente = ? AND cod_produto_origem = ?',
            (cnpj_sel, cod_sel),
        ).fetchone()[0]
        n_apur  = conn_del.execute(
            'SELECT COUNT(*) FROM nfe_item_apuracao '
            'WHERE cnpj_remetente = ? AND cod_produto_origem = ?',
            (cnpj_sel, cod_sel),
        ).fetchone()[0]
        n_alert = conn_del.execute(
            'SELECT COUNT(*) FROM produto_alerta '
            'WHERE cnpj_emitente = ? AND cod_produto = ?',
            (cnpj_sel, cod_sel),
        ).fetchone()[0]
        conn_del.close()

        _partes = [f'**{n_comp}** competência(s)', f'**{n_apur}** item(ns) de apuração']
        if n_alert:
            _partes.append(f'**{n_alert}** alerta(s) pendente(s)')
        st.warning(
            f'⚠️ Deseja excluir permanentemente o produto **{sel["Descrição"]}** '
            f'(Código `{cod_sel}`) da base de dados?\n\n'
            f'Serão removidos também: {", ".join(_partes)}.'
        )
        col_sim, col_nao, _ = st.columns([1, 1, 4])
        if col_sim.button('✅ Sim, excluir', type='primary', use_container_width=True):
            conn_del = get_conn()
            conn_del.execute(
                'DELETE FROM produto_alerta WHERE cnpj_emitente = ? AND cod_produto = ?',
                (cnpj_sel, cod_sel),
            )
            conn_del.execute(
                'DELETE FROM produto_competencia '
                'WHERE cnpj_remetente = ? AND cod_produto_origem = ?',
                (cnpj_sel, cod_sel),
            )
            conn_del.execute(
                'DELETE FROM nfe_item_apuracao '
                'WHERE cnpj_remetente = ? AND cod_produto_origem = ?',
                (cnpj_sel, cod_sel),
            )
            conn_del.execute(
                'DELETE FROM produtos WHERE cnpj_remetente = ? AND cod_produto_origem = ?',
                (cnpj_sel, cod_sel),
            )
            conn_del.commit()
            conn_del.close()
            st.session_state.aguardando_excluir = False
            st.session_state.prod_chave = ''
            st.success('Produto excluído com sucesso.')
            st.rerun()
        if col_nao.button('❌ Cancelar', use_container_width=True):
            st.session_state.aguardando_excluir = False
            st.rerun()

else:
    st.info('Clique em uma linha da tabela acima para ver o histórico de competências.')

# ── 3. Importar nova competência ──────────────────────────────────────────────
st.divider()
with st.expander('📤 Importar nova competência (RegimeEspecial)', expanded=False):

    # Exibir popups de rejeição pendentes (antes dos widgets para sobrepor corretamente)
    if st.session_state.get('_rejeicao_orig'):
        _popup_rejeicao('_rejeicao_orig', st.session_state['_rejeicao_orig'])
    if st.session_state.get('_rejeicao_ajus'):
        _popup_rejeicao('_rejeicao_ajus', st.session_state['_rejeicao_ajus'])

    st.caption(
        'Selecione os dois arquivos da competência. '
        'Nomes obrigatórios: `RegimeEspecialMS_AAAA_MM_Original.xlsx` e '
        '`RegimeEspecialMS_AAAA_MM_Ajustada.xlsx`. '
        'A importação inicia automaticamente quando ambos forem validados.'
    )

    col_ano, col_mes = st.columns(2)
    ano_comp          = col_ano.text_input('Ano (AAAA)', max_chars=4, key='comp_ano')
    mes_comp          = col_mes.selectbox('Mês', [f'{m:02d}' for m in range(1, 13)], key='comp_mes')
    ano_valido        = bool(ano_comp and len(ano_comp) == 4 and ano_comp.isdigit())
    mes_ano_informado = f'{ano_comp}-{mes_comp}' if ano_valido else None

    col_orig, col_ajust = st.columns(2)
    arquivo_original = col_orig.file_uploader(
        'Planilha Original', type=['xlsx', 'xlsm'],
        key=f'upload_original_{st.session_state["_orig_key"]}',
    )
    arquivo_ajustada = col_ajust.file_uploader(
        'Planilha Ajustada', type=['xlsx', 'xlsm'],
        key=f'upload_ajustada_{st.session_state["_ajus_key"]}',
    )

    orig_ok = ajus_ok = False

    if ano_valido:
        if arquivo_original:
            ok, msg = _validar_arquivo(arquivo_original, ano_comp, mes_comp, 'Original')
            if ok:
                col_orig.success('✅ Arquivo válido')
                orig_ok = True
            else:
                st.session_state['_rejeicao_orig'] = msg
                st.session_state['_orig_key'] += 1
                st.rerun()

        if arquivo_ajustada:
            ok, msg = _validar_arquivo(arquivo_ajustada, ano_comp, mes_comp, 'Ajustada')
            if ok:
                col_ajust.success('✅ Arquivo válido')
                ajus_ok = True
            else:
                st.session_state['_rejeicao_ajus'] = msg
                st.session_state['_ajus_key'] += 1
                st.rerun()

        if orig_ok and not ajus_ok and not arquivo_ajustada:
            st.info('✅ Original validada — aguardando planilha Ajustada.')
        elif ajus_ok and not orig_ok and not arquivo_original:
            st.info('✅ Ajustada validada — aguardando planilha Original.')

    elif ano_comp:
        st.error('Informe um ano válido de 4 dígitos.')

    # Auto-import quando ambos válidos
    if orig_ok and ajus_ok and mes_ano_informado:
        chave_importado = f'_importado_{mes_ano_informado}'
        chave_rel_orig  = f'relatorio_original_{mes_ano_informado}'
        chave_rel_ajus  = f'relatorio_ajustada_{mes_ano_informado}'

        if not st.session_state.get(chave_importado):
            with st.spinner(f'Importando competência {mes_ano_informado}...'):
                _conn = get_conn()
                _rel_orig = importar_competencia(_conn, arquivo_original, mes_ano_informado, 'Original')
                _conn.close()
                _conn = get_conn()
                _rel_ajus = importar_competencia(_conn, arquivo_ajustada, mes_ano_informado, 'Ajustada')
                _conn.close()
            st.session_state[chave_importado] = True
            st.session_state[chave_rel_orig]  = _rel_orig
            st.session_state[chave_rel_ajus]  = _rel_ajus
            st.rerun()

    # Resultados da última importação
    if mes_ano_informado:
        chave_rel_orig = f'relatorio_original_{mes_ano_informado}'
        chave_rel_ajus = f'relatorio_ajustada_{mes_ano_informado}'
        if st.session_state.get(chave_rel_orig):
            st.success(f'✅ Planilha Original de {mes_ano_informado} importada.')
            _exibir_relatorio(st.session_state[chave_rel_orig])
        if st.session_state.get(chave_rel_ajus):
            st.success(f'✅ Planilha Ajustada de {mes_ano_informado} importada.')
            _exibir_relatorio(st.session_state[chave_rel_ajus])

# ── 4. Backfill EAN / NCM / CEST ─────────────────────────────────────────────
with st.expander('🔄 Preencher EAN / NCM / CEST em lote (arquivos históricos)', expanded=False):
    st.caption(
        'Selecione todos os seus arquivos RegimeEspecial de uma vez. '
        'Apenas os campos EAN, NCM e CEST serão atualizados — '
        'classificações, PMC e MVA existentes não são alterados.'
    )

    _sem_ean = get_conn().execute(
        "SELECT COUNT(*) FROM produtos WHERE ean IS NULL OR ean = ''"
    ).fetchone()[0]
    st.info(f'Produtos sem EAN/NCM no cadastro: **{_sem_ean}** de {total}')

    # Exibe resultado da última execução (session_state persiste entre reruns)
    if st.session_state.get('_bf_resultado'):
        _r = st.session_state['_bf_resultado']
        st.success(
            f'Concluído: **{_r["atualizados"]}** produto(s) atualizados. '
            f'Sem EAN/NCM: {_r["antes"]} antes → {_r["depois"]} agora.'
        )
        if _r['ignorados']:
            st.caption(f'{_r["ignorados"]} arquivo(s) ignorados (nome fora do padrão).')
        for _e in _r['erros']:
            st.error(_e)

    arquivos_lote = st.file_uploader(
        'Selecione os arquivos RegimeEspecialMS (qualquer mês, Original ou Ajustada)',
        type=['xlsx', 'xlsm'],
        accept_multiple_files=True,
        key='backfill_lote',
    )

    if arquivos_lote and st.button('🔄 Preencher agora', type='primary'):
        st.session_state['_bf_resultado'] = None
        _conn = get_conn()
        _cur  = _conn.cursor()
        _atualizados = 0
        _ignorados   = 0
        _erros_bf    = []

        # Índices de coluna fixos da aba RegimeEspecial (independente do módulo em cache)
        _COL_CNPJ, _COL_COD, _COL_EAN, _COL_NCM, _COL_CEST = 6, 12, 10, 9, 8

        def _limpa(v, extras=('SEM GTIN', '0', '')):
            if not pd.notna(v):
                return None
            s = str(v).strip()
            if s.endswith('.0'):
                s = s[:-2]
            return s if s not in extras else None

        for _up in arquivos_lote:
            _info = classificar_arquivo_historico(_up.name)
            if _info is None:
                _ignorados += 1
                continue
            try:
                _xl  = pd.ExcelFile(_up)
                _sht = 'RegimeEspecial' if 'RegimeEspecial' in _xl.sheet_names else _xl.sheet_names[0]
                _raw = _xl.parse(sheet_name=_sht, header=None).iloc[2:]
            except Exception as _e:
                _erros_bf.append(f'{_up.name}: {_e}')
                continue

            _registros = []
            for _, _row in _raw.iterrows():
                _cnpj = str(_row[_COL_CNPJ]).strip() if pd.notna(_row[_COL_CNPJ]) else None
                _cod  = str(_row[_COL_COD]).strip()  if pd.notna(_row[_COL_COD])  else None
                if not _cnpj or not _cod or _cod == 'nan':
                    continue
                _registros.append({
                    'cnpj_remetente':     _cnpj,
                    'cod_produto_origem': _cod,
                    'ean':  _limpa(_row[_COL_EAN], ('SEM GTIN', '0', '')),
                    'ncm':  _limpa(_row[_COL_NCM]),
                    'cest': _limpa(_row[_COL_CEST]),
                })

            if not _registros:
                continue
            _unicos = pd.DataFrame(_registros).drop_duplicates(
                subset=['cnpj_remetente', 'cod_produto_origem']
            )
            for _, _p in _unicos.iterrows():
                _ean  = _p['ean']  if pd.notna(_p['ean'])  else None
                _ncm  = _p['ncm']  if pd.notna(_p['ncm'])  else None
                _cest = _p['cest'] if pd.notna(_p['cest']) else None
                if not any([_ean, _ncm, _cest]):
                    continue
                _cur.execute(
                    'UPDATE produtos SET ean=COALESCE(ean,?), ncm=COALESCE(ncm,?), cest=COALESCE(cest,?) '
                    'WHERE cnpj_remetente=? AND cod_produto_origem=?',
                    (_ean, _ncm, _cest, _p['cnpj_remetente'], _p['cod_produto_origem']),
                )
                _atualizados += _cur.rowcount

        _conn.commit()
        _depois = _conn.execute(
            "SELECT COUNT(*) FROM produtos WHERE ean IS NULL OR ean = ''"
        ).fetchone()[0]
        _conn.close()

        st.session_state['_bf_resultado'] = {
            'atualizados': _atualizados,
            'antes':       _sem_ean,
            'depois':      _depois,
            'ignorados':   _ignorados,
            'erros':       _erros_bf,
        }
        st.rerun()
