"""Página: CMED — Status e importação da tabela CMED (Anvisa)"""
import tempfile
import streamlit as st
import pandas as pd
import sys, os
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from _config import get_conn, aplicar_tema_contili, page_header

from cmed_downloader import (
    processar_arquivo_cmed, init_cmed_db,
    extrair_mes_ano_do_nome, extrair_mes_ano_da_planilha,
)


def _normalizar_ean_busca(valor: str) -> str:
    """Remove espaços e o '.0' que o Excel adiciona ao colar EANs como número."""
    v = valor.strip()
    if v.endswith('.0'):
        v = v[:-2]
    return v


def _meses_ausentes(competencias: list) -> list[str]:
    """Retorna lista de 'YYYY-MM' ausentes entre a competência mais antiga e a mais recente."""
    if len(competencias) < 2:
        return []
    carregados = {r[0] for r in competencias}
    datas = sorted(datetime.strptime(c, '%Y-%m') for c in carregados)
    dt_min, dt_max = datas[0], datas[-1]
    ausentes = []
    cur = dt_min
    while cur <= dt_max:
        chave = cur.strftime('%Y-%m')
        if chave not in carregados:
            ausentes.append(chave)
        cur = cur.replace(month=cur.month % 12 + 1, year=cur.year + (1 if cur.month == 12 else 0))
    return ausentes


st.set_page_config(page_title='CMED', page_icon='💊', layout='wide')
aplicar_tema_contili()

# Garante que a tabela CMED existe antes de qualquer consulta
conn = get_conn()
init_cmed_db(conn)
conn.close()

page_header('CMED — Anvisa', 'Preços Máximos ao Consumidor (PMC 17%) — alíquota do Mato Grosso do Sul.')

# ── 1. Consulta por EAN ───────────────────────────────────────────────────────
st.subheader('🔍 Consulta de PMC por EAN')
st.caption('Histórico completo do medicamento em todas as competências carregadas.')

ean_busca = st.text_input('EAN do medicamento', placeholder='ex: 7896523208024')

if ean_busca:
    ean_norm = _normalizar_ean_busca(ean_busca)
    try:
        conn = get_conn()
        rows = conn.execute(
            'SELECT mes_ano, produto, apresentacao, pmc_17, tipo_lista '
            'FROM cmed_historico WHERE ean = ? ORDER BY mes_ano',
            (ean_norm,),
        ).fetchall()
        conn.close()
    except Exception as e:
        rows = []
        st.error(f'Erro ao consultar o banco: {e}')

    if rows:
        st.success(f'**{rows[-1]["produto"]}** — {rows[-1]["apresentacao"] or "—"}')
        df_hist = pd.DataFrame([
            {
                'Competência':  r['mes_ano'],
                'PMC 17% (R$)': f'{r["pmc_17"]:.2f}' if r['pmc_17'] is not None else '—',
                'Lista':        r['tipo_lista'] or '—',
            }
            for r in rows
        ])
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
    else:
        st.warning(f'EAN `{ean_busca}` não encontrado em nenhuma competência carregada.')

st.divider()

# ── 2. Importar nova tabela CMED ──────────────────────────────────────────────
st.subheader('📥 Importar nova tabela CMED')
st.markdown(
    '**Como baixar:** acesse '
    '[gov.br/anvisa/pt-br/assuntos/medicamentos/cmed/precos]'
    '(https://www.gov.br/anvisa/pt-br/assuntos/medicamentos/cmed/precos), '
    'clique em "Consulta de Preços" e salve o arquivo `.xlsx`.'
)

arquivo_up = st.file_uploader(
    'Selecione o arquivo CMED (.xls / .xlsx)',
    type=['xls', 'xlsx'],
    help='Selecione o arquivo mensal baixado da Anvisa.',
)

if arquivo_up is not None:
    # Detecta a competência pelo nome do arquivo primeiro
    mes_ano_det = extrair_mes_ano_do_nome(arquivo_up.name)

    # Se não encontrou no nome, lê o conteúdo via tempfile
    ext = os.path.splitext(arquivo_up.name)[1] or '.xlsx'
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(arquivo_up.getvalue())
        tmp_path = tmp.name

    if not mes_ano_det:
        try:
            df_raw = pd.read_excel(tmp_path, header=None, nrows=25)
            mes_ano_det = extrair_mes_ano_da_planilha(df_raw)
        except Exception:
            pass

    if mes_ano_det:
        st.info(f'Competência detectada no arquivo: **{mes_ano_det}**')
    else:
        st.warning(
            'Não foi possível identificar a competência pelo nome ou conteúdo do arquivo. '
            'A data de modificação do arquivo será usada como fallback.'
        )

    if st.button('📥 Importar arquivo selecionado', type='primary'):
        with st.spinner('Importando…'):
            conn = get_conn()
            init_cmed_db(conn)
            total = processar_arquivo_cmed(tmp_path, conn)
            conn.commit()
            conn.close()
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        st.success(
            f'✅ {total} medicamento(s) importado(s)'
            + (f' para a competência **{mes_ano_det}**.' if mes_ano_det else '.')
        )
        st.rerun()

st.divider()

# ── 3. Competências carregadas ────────────────────────────────────────────────
st.subheader('📅 Competências carregadas')

conn = get_conn()
competencias = conn.execute(
    'SELECT mes_ano, COUNT(*) as total FROM cmed_historico GROUP BY mes_ano ORDER BY mes_ano'
).fetchall()
conn.close()

_MESES_PT = {
    '01': 'Jan', '02': 'Fev', '03': 'Mar', '04': 'Abr',
    '05': 'Mai', '06': 'Jun', '07': 'Jul', '08': 'Ago',
    '09': 'Set', '10': 'Out', '11': 'Nov', '12': 'Dez',
}

def _fmt_mes(mes_ano: str) -> str:
    """'2026-06' → 'Jun/2026'"""
    try:
        ano, mes = mes_ano.split('-')
        return f"{_MESES_PT.get(mes, mes)}/{ano}"
    except Exception:
        return mes_ano

if not competencias:
    st.warning('Nenhum dado CMED carregado ainda. Importe um arquivo acima.')
else:
    _mais_antiga  = competencias[0][0]
    _mais_recente = competencias[-1][0]
    _total_reg    = sum(r[1] for r in competencias)
    _n_meses      = len(competencias)
    _ausentes     = _meses_ausentes(competencias)

    # Métricas em linha horizontal
    _mc1, _mc2, _mc3, _mc4 = st.columns(4)
    _mc1.metric('Competência mais recente', _fmt_mes(_mais_recente))
    _mc2.metric('Competência mais antiga',  _fmt_mes(_mais_antiga))
    _mc3.metric('Meses carregados',         _n_meses)
    _mc4.metric('Total de registros',       f'{_total_reg:,}')

    # Status de gaps — bloco cheio abaixo das métricas
    if _ausentes:
        _lista = ' · '.join(_fmt_mes(m) for m in _ausentes)
        st.info(
            f'**{len(_ausentes)} competência(s) ausente(s)** no intervalo '
            f'{_fmt_mes(_mais_antiga)} → {_fmt_mes(_mais_recente)}:  \n{_lista}'
        )
    else:
        st.info(
            f'Série completa — todos os **{_n_meses}** meses do intervalo '
            f'{_fmt_mes(_mais_antiga)} → {_fmt_mes(_mais_recente)} estão presentes.'
        )

    with st.expander('Ver todas as competências', expanded=False):
        df_comp = pd.DataFrame(
            [{'Competência': _fmt_mes(r[0]), 'Ano-Mês': r[0], 'Registros': r[1]}
             for r in competencias],
        )
        st.dataframe(df_comp, use_container_width=True, hide_index=True)
