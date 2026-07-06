"""Página: Importar NF-e"""
import re
import streamlit as st
import pandas as pd
import glob
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from _config import (
    get_conn, init_alertas_table, init_nfe_item_apuracao_table,
    aplicar_tema_contili, page_header, ROOT,
)
from cmed_comparador import consultar_pmc_cmed

from nfe_parser import parsear_xml, classificar_itens, PMC_DIVERGENTE
from nfe_repository import persistir_itens
from planilha_credito_outorgado import gerar_planilha


def _aplicar_pre_classificacao(item, competencia, conn):
    """
    Pré-classifica um item novo diretamente nesta página.
    Garante que a classificação sempre usa o algoritmo atual,
    independente da versão em cache do nfe_parser.
    """
    item['pre_mod_bc'] = None
    item['pre_pmc']    = None
    item['pre_mva']    = None
    item['pre_nota']   = None

    ncm_norm  = re.sub(r'[.\s]',  '', item.get('ncm')  or '')
    cest_norm = re.sub(r'[.\s-]', '', item.get('cest') or '')
    ean       = item.get('ean')

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
            item['pre_mod_bc'] = '0'
            item['pre_pmc']    = pmc_17
        else:
            mod = {'Positiva': '1', 'Negativa': '2', 'Neutra': '3'}.get(tipo_lista or '')
            if mod:
                item['pre_mod_bc'] = mod
            else:
                item['pre_nota'] = (
                    f'EAN na CMED mas PMC 17%=0 e lista não identificada '
                    f'({tipo_lista!r}). Classifique como MOD 1, 2 ou 3.'
                )

    elif is_st and not ean_na_cmed:
        item['pre_mod_bc'] = '4'
        if mva_row is not None:
            bc   = float(item.get('bc_icms_origem') or 0)
            vlr  = float(item.get('vlr_icms_origem') or 0)
            aliq = round(vlr / bc * 100) if bc > 0 else None
            if aliq is not None:
                if aliq >= 15:
                    item['pre_mva'] = round(mva_row[0] / 100, 4) if mva_row[0] is not None else None
                elif aliq >= 10:
                    item['pre_mva'] = round(mva_row[3] / 100, 4) if mva_row[3] is not None else None
                elif aliq >= 5:
                    item['pre_mva'] = round(mva_row[2] / 100, 4) if mva_row[2] is not None else None
                else:
                    item['pre_mva'] = round(mva_row[1] / 100, 4) if mva_row[1] is not None else None

    elif not is_st and not ean_na_cmed:
        item['pre_mod_bc'] = '5'

    else:
        item['pre_mod_bc'] = '5'
        item['pre_nota'] = (
            f'NCM {item.get("ncm")} fora do Subanexo ST, mas EAN na CMED '
            f'(PMC={pmc_17}, Lista={tipo_lista}). Verificar.'
        )

st.set_page_config(page_title='Importar NF-e', page_icon='📥', layout='wide')
aplicar_tema_contili()
init_alertas_table()
init_nfe_item_apuracao_table()

page_header('Importar NF-e', 'Processa os XMLs de um mês e classifica os itens pelo cadastro de produtos.')

col_ano, col_mes = st.columns(2)
ano_comp   = col_ano.text_input('Ano (AAAA)', max_chars=4, key='nfe_ano')
mes_comp   = col_mes.selectbox('Mês', [f'{m:02d}' for m in range(1, 13)], key='nfe_mes')
ano_valido = bool(ano_comp and len(ano_comp) == 4 and ano_comp.isdigit())

arquivos_xml = st.file_uploader(
    'Arraste a pasta inteira com os XMLs aqui (ou clique para selecionar os arquivos)',
    type='xml', accept_multiple_files=True,
    help='Arraste a pasta do Windows (do Explorador de Arquivos) direto para esta área — '
         'todos os .xml dentro dela, inclusive em subpastas, são pegos automaticamente. '
         'Nenhum arquivo fica de fora.',
)

col_btn, col_info = st.columns([1, 4])
executar = col_btn.button('▶ Processar', type='primary', use_container_width=True)
col_info.caption('Os XMLs serão lidos, classificados e os produtos novos registrados como alertas.')

if executar:
    if not ano_valido:
        st.error('Informe um ano válido com 4 dígitos.')
        st.stop()
    if not arquivos_xml:
        st.warning('Arraste a pasta (ou selecione os arquivos) com os XMLs.')
        st.stop()

    competencia = f'{ano_comp}-{mes_comp}'
    pasta_abs = os.path.join(ROOT, 'data', 'nfe', competencia)
    os.makedirs(pasta_abs, exist_ok=True)
    for _up in arquivos_xml:
        with open(os.path.join(pasta_abs, os.path.basename(_up.name)), 'wb') as _f:
            _f.write(_up.getbuffer())

    arquivos = sorted(glob.glob(os.path.join(pasta_abs, '*.xml')))

    st.caption(f'Competência: **{competencia}** ({len(arquivos_xml)} XML(s) recebido(s), todos entram na apuração deste mês, independente da data de emissão de cada nota).')

    todos_classificados = []
    todos_novos = []
    erros = []

    conn = get_conn()

    # Limpa todos os alertas antes de reprocessar — garante slate limpo a cada import.
    n_alertas_limpos = conn.execute("DELETE FROM produto_alerta").rowcount
    conn.commit()

    barra = st.progress(0, text='Lendo arquivos...')

    for i, arq in enumerate(arquivos, 1):
        barra.progress(i / len(arquivos), text=f'Lendo {os.path.basename(arq)} ({i}/{len(arquivos)})')
        nota = parsear_xml(arq)
        if not nota:
            erros.append(os.path.basename(arq))
            continue
        classificados, novos = classificar_itens(nota['itens'], conn, competencia)
        todos_classificados.extend(classificados)
        todos_novos.extend(novos)

        persistir_itens(conn, classificados + novos, competencia, tipo_planilha='Original', commit=False)

        for item in novos:
            _aplicar_pre_classificacao(item, competencia, conn)
            try:
                # INSERT OR IGNORE: evita duplicatas quando o mesmo produto aparece
                # em múltiplos XMLs dentro do mesmo lote de importação.
                conn.execute(
                    '''INSERT OR IGNORE INTO produto_alerta
                           (cnpj_emitente, cod_produto, ean, descricao, ncm, cest,
                            num_nf, data_emissao, pre_mod_bc, pre_pmc, pre_mva, pre_nota)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (item.get('cnpj_emitente'), item.get('cod_produto'), item.get('ean'),
                     item.get('descricao'), item.get('ncm'), item.get('cest'),
                     item.get('num_nf'), item.get('data_emissao'),
                     item.get('pre_mod_bc'), item.get('pre_pmc'), item.get('pre_mva'),
                     item.get('pre_nota')),
                )
            except Exception:
                pass

    conn.commit()
    barra.empty()

    # ── Geração da planilha de apuração (acumulado de toda a competência) ────
    planilhas_geradas = []
    with st.spinner(f'Gerando planilha de apuração de {competencia}...'):
        try:
            caminho = gerar_planilha(conn, competencia, tipo_planilha='Original')
            planilhas_geradas.append((competencia, caminho))
        except Exception as e:
            st.error(f'Erro ao gerar planilha de {competencia}: {e}')

    conn.close()

    # ── Resumo ──────────────────────────────────────────────────────────────
    st.divider()
    st.subheader('Resultado')

    pmc_div = [i for i in todos_classificados if i.get('status') == PMC_DIVERGENTE]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric('Arquivos lidos', len(arquivos))
    c2.metric('Itens classificados', len(todos_classificados))
    c3.metric('PMC atualizados pela CMED', len(pmc_div))
    c4.metric('Novos produtos (alertas)', len(todos_novos))
    c5.metric('Alertas limpos', n_alertas_limpos)

    if erros:
        st.error(f'Erros de leitura em {len(erros)} arquivo(s): {", ".join(erros)}')

    # ── Divergências de PMC ──────────────────────────────────────────────────
    if pmc_div:
        st.divider()
        st.subheader('💰 PMC com divergência da tabela CMED')
        st.caption(
            'Esses produtos têm PMC diferente do pesquisado na CMED. O PMC histórico (coluna Y '
            'da planilha) NÃO é alterado — o valor da CMED fica registrado separadamente '
            '(coluna AN) para conferência.'
        )
        df_div = pd.DataFrame([
            {
                'Código': i.get('cod_produto'),
                'EAN': i.get('ean'),
                'Descrição': i.get('descricao'),
                'PMC Histórico (R$)': i.get('pmc'),
                'PMC CMED (R$)': i.get('pmc_cmed'),
                'Diferença (R$)': i.get('pmc_divergencia'),
            }
            for i in pmc_div
        ])
        st.dataframe(df_div, use_container_width=True, hide_index=True)

    # ── Novos Produtos ───────────────────────────────────────────────────────
    if todos_novos:
        st.divider()
        st.warning(
            f'⚠️ **{len(todos_novos)} produto(s) novo(s)** detectado(s). '
            'Acesse a página **Alertas** para classificar antes de fechar a apuração.'
        )
        df_novos = pd.DataFrame([
            {
                'CNPJ Emitente': i.get('cnpj_emitente'),
                'Código': i.get('cod_produto'),
                'EAN': i.get('ean'),
                'NCM': i.get('ncm'),
                'Descrição': i.get('descricao'),
                'Pré-class.': (
                    {'0': '0-PMC', '4': '4-MVA', '5': '5-Normal'}.get(i.get('pre_mod_bc', ''), i.get('pre_mod_bc') or '—')
                ),
                'NF': i.get('num_nf'),
            }
            for i in todos_novos
        ])
        st.dataframe(df_novos, use_container_width=True, hide_index=True)

    elif not erros:
        st.success('Todos os itens foram classificados automaticamente. Nenhum produto novo detectado.')

    # ── Planilha de apuração gerada ───────────────────────────────────────────
    if planilhas_geradas:
        st.divider()
        st.subheader('📄 Planilha de apuração (Crédito Outorgado)')
        st.caption(
            'Gerada com o acumulado de toda a competência (todas as NF-e já importadas '
            'naquele mês, não só o lote de agora). Trilha Original.'
        )
        for mes, caminho in planilhas_geradas:
            with open(caminho, 'rb') as f:
                st.download_button(
                    f'⬇️ Baixar {os.path.basename(caminho)}',
                    data=f.read(),
                    file_name=os.path.basename(caminho),
                    mime='application/vnd.ms-excel.sheet.macroEnabled.12',
                    key=f'download_{mes}',
                )
