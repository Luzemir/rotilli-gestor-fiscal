"""
app.py — Painel Geral do Gestor Fiscal Rotilli
"""
import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import (
    get_conn, init_todas_tabelas,
    aplicar_tema_contili, page_header, badge,
)

st.set_page_config(
    page_title='Gestor Fiscal — Rotilli',
    page_icon='📊',
    layout='wide',
)

aplicar_tema_contili()
init_todas_tabelas()

col_cta = page_header(
    'Painel Geral',
    'Visão consolidada da operação fiscal',
)
with col_cta:
    if st.button('Importar NFs', type='primary', use_container_width=True):
        st.switch_page('pages/1_Importar_NF_e.py')

# ── KPIs ──────────────────────────────────────────────────────────────────────

conn = get_conn()
cur  = conn.cursor()
produtos     = cur.execute('SELECT COUNT(*) FROM produtos').fetchone()[0]
competencias = cur.execute('SELECT COUNT(*) FROM produto_competencia').fetchone()[0]
cmed         = cur.execute('SELECT COUNT(*), MIN(mes_ano), MAX(mes_ano) FROM cmed_historico').fetchone()
alertas      = cur.execute("SELECT COUNT(*) FROM produto_alerta WHERE status='PENDENTE'").fetchone()[0]

ultimas_nf = cur.execute("""
    SELECT DISTINCT chave_acesso, razao_remetente, num_nf, data_emissao,
           SUM(quantidade * valor_unitario) as valor_total,
           COUNT(*) as itens
    FROM nfe_item_apuracao
    GROUP BY chave_acesso
    ORDER BY data_emissao DESC, num_nf DESC
    LIMIT 5
""").fetchall()

alertas_lista = cur.execute("""
    SELECT descricao, ncm, status, criado_em
    FROM produto_alerta
    WHERE status = 'PENDENTE'
    ORDER BY criado_em DESC
    LIMIT 5
""").fetchall()

conn.close()

# ── Métricas ──────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric('Produtos Cadastrados',   f'{produtos:,}')
c2.metric('Alertas Pendentes',      alertas,          delta_color='inverse')
c3.metric('Registros Competência',  f'{competencias:,}')
c4.metric('Registros CMED',
          f'{cmed[0]:,}',
          f'{cmed[1]} → {cmed[2]}' if cmed[0] > 0 else 'sem dados')

st.markdown('<div style="margin-top:20px"></div>', unsafe_allow_html=True)

# ── Dois cards lado a lado ─────────────────────────────────────────────────────
col_nf, col_al = st.columns(2)

with col_nf:
    with st.container(border=True):
        st.markdown(
            '<div class="card-hd-row" style="display:flex;align-items:center;'
            'justify-content:space-between;margin-bottom:14px">'
            '<span style="font-size:13px;font-weight:700;color:var(--c-fg,#142158)">'
            'Últimas NF-e Importadas</span></div>',
            unsafe_allow_html=True,
        )
        if ultimas_nf:
            rows_html = ''
            for r in ultimas_nf:
                chave, emitente, num_nf, data, valor, itens = r
                chave_fmt = str(chave)[-12:] if chave else '—'
                emitente  = (emitente or '—')[:28]
                valor_fmt = f'R$ {(valor or 0):,.2f}'
                rows_html += (
                    f'<tr>'
                    f'<td class="ctili-mono">{chave_fmt}…</td>'
                    f'<td style="font-weight:600;color:var(--c-primary,#1B3A78)">{emitente}</td>'
                    f'<td class="ctili-mono">{valor_fmt}</td>'
                    f'<td>{itens} itens</td>'
                    f'</tr>'
                )
            st.markdown(f"""
            <style>
            .ctili-tbl {{width:100%;border-collapse:collapse;font-size:12.5px}}
            .ctili-tbl thead th {{text-align:left;font-size:10.5px;font-weight:700;
              color:var(--c-muted,#5A6480);text-transform:uppercase;letter-spacing:.08em;
              padding:0 10px 9px;border-bottom:1px solid var(--c-border,#E3E6EF);white-space:nowrap}}
            .ctili-tbl tbody tr {{border-bottom:1px solid var(--c-border,#E3E6EF)}}
            .ctili-tbl tbody tr:last-child {{border-bottom:none}}
            .ctili-tbl tbody td {{padding:9px 10px;color:var(--c-fg,#142158);vertical-align:middle}}
            </style>
            <table class="ctili-tbl">
              <thead><tr><th>Chave</th><th>Emitente</th><th>Valor</th><th>Itens</th></tr></thead>
              <tbody>{rows_html}</tbody>
            </table>
            """, unsafe_allow_html=True)
        else:
            st.caption('Nenhuma NF-e importada ainda.')

with col_al:
    with st.container(border=True):
        st.markdown(
            f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">'
            f'<span style="font-size:13px;font-weight:700;color:var(--c-fg,#142158)">Alertas Pendentes</span>'
            f'{badge(f"{alertas} pendentes", "warn") if alertas else badge("Nenhum", "ok")}'
            f'</div>',
            unsafe_allow_html=True,
        )
        if alertas_lista:
            items_html = ''
            for desc, ncm, status, criado in alertas_lista:
                desc_fmt = (desc or '—')[:45]
                ncm_fmt  = ncm or '—'
                items_html += (
                    f'<div style="display:flex;align-items:flex-start;gap:10px;'
                    f'padding:10px 0;border-bottom:1px solid var(--c-border,#E3E6EF)">'
                    f'<div style="width:7px;height:7px;border-radius:50%;background:#F7901E;'
                    f'flex-shrink:0;margin-top:5px"></div>'
                    f'<div>'
                    f'<div style="font-size:13px;font-weight:600;color:var(--c-fg,#142158)">{desc_fmt}</div>'
                    f'<div style="font-size:11.5px;color:var(--c-muted,#5A6480);margin-top:2px">'
                    f'NCM {ncm_fmt}</div>'
                    f'</div></div>'
                )
            st.markdown(items_html, unsafe_allow_html=True)
        else:
            st.success('Nenhum alerta pendente.')

# ── Navegação rápida ───────────────────────────────────────────────────────────
st.markdown('<div style="margin-top:8px"></div>', unsafe_allow_html=True)
st.markdown("""
<table class="ctili-tbl">
  <thead><tr><th>Módulo</th><th>O que faz</th></tr></thead>
  <tbody>
    <tr><td style="font-weight:700">📥 Importar NF-e</td><td>Processa XMLs e classifica itens por competência</td></tr>
    <tr><td style="font-weight:700">🔔 Alertas</td><td>Produtos novos detectados aguardando classificação manual</td></tr>
    <tr><td style="font-weight:700">🔍 Produtos</td><td>Consulta e edição do cadastro de produtos</td></tr>
    <tr><td style="font-weight:700">💊 CMED</td><td>Status e importação da tabela de preços da Anvisa</td></tr>
    <tr><td style="font-weight:700">📋 NCM ST</td><td>Pré-classificação e consulta de NCMs com ST</td></tr>
    <tr><td style="font-weight:700">📊 Comparar Planilhas</td><td>Identifica divergências entre planilha Original e Ajustada</td></tr>
  </tbody>
</table>
""", unsafe_allow_html=True)
