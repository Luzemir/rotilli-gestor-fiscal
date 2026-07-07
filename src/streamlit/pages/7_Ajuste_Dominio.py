"""Página: Ajuste de CFOP para o Domínio"""
import io
import os
import glob
import zipfile
import streamlit as st
import pandas as pd
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from _config import (
    get_conn, init_produto_competencia_table,
    aplicar_tema_contili, page_header, ROOT,
)
import dominio_xml_ajuste as dx


st.set_page_config(page_title='Ajuste Domínio', page_icon='🔀', layout='wide')
aplicar_tema_contili()
init_produto_competencia_table()

page_header(
    'Ajuste de CFOP para o Domínio',
    'Reescreve o CFOP dos XMLs conforme a trilha Ajustada, para o lançamento cair '
    'no acumulador certo (23 = Normal · 25 = ST) ao importar no Domínio.',
)

# ── Entrada: competência + XMLs ────────────────────────────────────────────────
col_ano, col_mes = st.columns(2)
ano_comp = col_ano.text_input('Ano (AAAA)', max_chars=4, key='dom_ano')
mes_comp = col_mes.selectbox('Mês', [f'{m:02d}' for m in range(1, 13)], key='dom_mes')
ano_valido = bool(ano_comp and len(ano_comp) == 4 and ano_comp.isdigit())
competencia = f'{ano_comp}-{mes_comp}' if ano_valido else None

arquivos_xml = st.file_uploader(
    'Arraste a pasta com os XMLs da competência (ou clique para selecionar)',
    type='xml', accept_multiple_files=True,
    help='Os XMLs originais NÃO são alterados. A página gera cópias ajustadas '
         'para você baixar e importar no Domínio.',
)

apenas_troca = st.toggle(
    'Somente trocas de acumulador (não normalizar CFOP de mesma direção)',
    value=False,
    help='Desligado (padrão): aplica a regra completa — todo item de revenda vira x102 (Normal) '
         'ou x403 (ST), inclusive normalizações como 6101→6102 que não mudam o acumulador. '
         'Ligado: só mexe onde o acumulador muda de fato.',
)

# ── Pasta de destino ───────────────────────────────────────────────────────────
PASTA_BASE_PADRAO = os.path.join(ROOT, 'Documentos')
pasta_base = st.text_input(
    'Pasta onde salvar os XMLs ajustados',
    value=PASTA_BASE_PADRAO,
    help='Uma subpasta nova por competência é criada dentro dela (não sobrescreve os originais). '
         'Você também pode simplesmente baixar o .zip depois e salvar onde quiser.',
).strip() or PASTA_BASE_PADRAO


def _resolver_saida(base, comp):
    return os.path.join(base, comp, 'xml_dominio')


if competencia:
    _prev = _resolver_saida(pasta_base, competencia)
    _existe = os.path.isdir(_prev)
    st.caption(
        f'📁 Destino: `{_prev}` — '
        + ('⚠️ a pasta já existe e será **sobrescrita**.' if _existe
           else 'a pasta será **criada** ao gerar.')
    )

# ── Pré-check da trilha Ajustada ───────────────────────────────────────────────
if competencia:
    _conn = get_conn()
    stt = dx.status_ajustada(_conn, competencia)
    _conn.close()
    if stt['ultima_mes_ano'] is None:
        st.error(
            'Nenhuma classificação **Ajustada** encontrada até esta competência. '
            'Importe a planilha Ajustada em **Produtos** antes de gerar o ajuste — '
            'sem ela todos os itens ficam sem classificação e nada é reescrito.'
        )
    elif stt['competencia_exata'] == 0:
        st.warning(
            f'Não há carga Ajustada da própria competência {competencia}. '
            f'Será usada a mais recente disponível (**{stt["ultima_mes_ano"]}**), '
            f'com {stt["universo_produtos"]} produto(s). Para máxima precisão, '
            f'importe a Ajustada de {competencia} primeiro.'
        )
    else:
        st.success(
            f'Trilha Ajustada de {competencia} carregada · '
            f'{stt["universo_produtos"]} produto(s) classificável(is).'
        )

col_btn, col_info = st.columns([1, 4])
executar = col_btn.button('▶ Gerar XMLs ajustados', type='primary', use_container_width=True)
col_info.caption('Gera as cópias ajustadas e um .zip pronto para importar no Domínio.')

# ── Processamento ──────────────────────────────────────────────────────────────
if executar:
    if not ano_valido:
        st.error('Informe um ano válido com 4 dígitos.')
        st.stop()
    if not arquivos_xml:
        st.warning('Arraste a pasta (ou selecione os arquivos) com os XMLs.')
        st.stop()

    competencia = f'{ano_comp}-{mes_comp}'  # garantido não-nulo após validação acima

    # Salva os uploads numa pasta de entrada da competência
    pasta_in = os.path.join(ROOT, 'data', 'nfe', competencia)
    os.makedirs(pasta_in, exist_ok=True)
    for _up in arquivos_xml:
        with open(os.path.join(pasta_in, os.path.basename(_up.name)), 'wb') as _f:
            _f.write(_up.getbuffer())

    saida_dir = _resolver_saida(pasta_base, competencia)
    with st.spinner(f'Ajustando CFOPs de {competencia}...'):
        conn = get_conn()
        rel = dx.processar_pasta(pasta_in, competencia, conn, saida_dir, apenas_troca)
        conn.close()

    st.session_state['dom_rel'] = rel
    st.session_state['dom_saida'] = saida_dir

# ── Relatório ──────────────────────────────────────────────────────────────────
rel = st.session_state.get('dom_rel')
if rel:
    st.divider()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric('Arquivos', rel['arquivos'], f'{rel["arquivos_ajustados"]} c/ ajuste')
    c2.metric('CFOP ajustado', rel['itens_ajustados'])
    c3.metric('Já coerente', rel['itens_coerentes'])
    c4.metric('Sem Ajustada', rel['itens_sem_ajustada'])
    c5.metric('CFOP não previsto', rel['itens_cfop_nao_previsto'])

    # Alerta de CFOPs não previstos (adicionar à lista de-para)
    if rel['cfops_nao_previstos']:
        linhas = ' · '.join(f'{c} ({q})' for c, q in sorted(rel['cfops_nao_previstos'].items()))
        st.warning(
            f'**CFOP(s) não previsto(s) na lista de-para:** {linhas}. '
            f'Esses itens ficaram inalterados. Se forem de revenda, adicione o CFOP à '
            f'lista `CFOPS_PREVISTOS` em `dominio_xml_ajuste.py`.'
        )

    # ZIP para download
    saida_dir = st.session_state.get('dom_saida')
    if saida_dir and os.path.isdir(saida_dir):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for arq in sorted(glob.glob(os.path.join(saida_dir, '*.xml'))):
                zf.write(arq, os.path.basename(arq))
        buf.seek(0)
        st.download_button(
            f'⬇ Baixar lote ajustado ({rel["arquivos"]} XMLs) — {rel["competencia"]}',
            data=buf, file_name=f'xml_dominio_{rel["competencia"]}.zip',
            mime='application/zip', type='primary', use_container_width=True,
        )
        st.caption(f'Também gravado em disco: `{saida_dir}`')

    # Tabela de pendências (sem classificação Ajustada + CFOP não previsto)
    if rel['pendencias']:
        st.markdown('#### Pendências (não alteradas — revisar manualmente)')
        df = pd.DataFrame(rel['pendencias'], columns=['Arquivo', 'Item', 'cProd', 'CFOP', 'Motivo'])
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(
            f'{rel["itens_sem_ajustada"]} sem classificação Ajustada · '
            f'{rel["itens_cfop_nao_previsto"]} com CFOP fora da lista. '
            f'A maioria dos "sem Ajustada" some quando a planilha Ajustada da competência é importada.'
        )
