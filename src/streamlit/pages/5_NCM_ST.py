"""Página: NCM ST — Cadastro de NCMs sujeitos ao ICMS-ST no MS"""
import glob
import json
import re
import subprocess
import tempfile
import streamlit as st
import pandas as pd
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from _config import get_conn, aplicar_tema_contili, page_header, ROOT

ARQUIVO_SEGS = os.path.join(ROOT, 'data', 'Mercadorias_ST.xlsx')

# Seguimentos ICMS-ST MS — dados estáticos da legislação (Decreto 15.990/2022 e atualizações)
_SEGUIMENTOS_HARDCODED: dict[int, str] = {
    1:  'Autopeças',
    2:  'Bebidas alcoólicas, exceto cerveja e chope',
    3:  'Cervejas, chopes, refrigerantes, águas e outras bebidas',
    4:  'Cigarros e outros produtos derivados do fumo',
    5:  'Cimentos',
    6:  'Combustíveis e lubrificantes',
    7:  'Energia elétrica',
    8:  'Ferramentas',
    9:  'Lâmpadas, reatores e "starter"',
    10: 'Materiais de construção e congêneres',
    11: 'Materiais de limpeza',
    12: 'Materiais elétricos',
    13: 'Medicamentos de uso humano e outros produtos farmacêuticos para uso humano ou veterinário',
    14: 'Papéis, plásticos, produtos cerâmicos e vidros',
    15: 'Revogado',
    16: 'Pneumáticos, câmaras de ar e protetores de borracha',
    17: 'Produtos alimentícios',
    18: 'Revogado',
    19: 'Revogado',
    20: 'Produtos de perfumaria e de higiene pessoal e cosméticos',
    21: 'Produtos Eletrônicos, Eletroeletrônicos e Eletrodomésticos',
    22: 'Rações para animais domésticos',
    23: 'Sorvetes e preparados para fabricação de sorvetes em máquinas',
    24: 'Tintas e vernizes',
    25: 'Veículos automotores',
    26: 'Veículos de duas e três rodas motorizados',
    27: 'Revogado',
    28: 'Venda de mercadorias pelo sistema porta a porta',
}

COLUNAS_ESPERADAS = frozenset({
    'NCM', 'CEST', 'Remover', 'Seg.', 'Descrição',
    'MVA Oper. Interna (%)', 'MVA Alíq. 4%', 'MVA Alíq. 7%', 'MVA Alíq. 12%',
})


def _init_ncm_st_table():
    conn = get_conn()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS ncm_st (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            seguimento        INTEGER,
            item              TEXT,
            cest              TEXT,
            cest_norm         TEXT,
            ncm               TEXT,
            ncm_norm          TEXT,
            mva_interno       REAL,
            mva_aliq4         REAL,
            mva_aliq7         REAL,
            mva_aliq12        REAL,
            descricao         TEXT,
            dispositivo_legal TEXT
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_ncm_st_ncm  ON ncm_st (ncm_norm)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_ncm_st_cest ON ncm_st (cest_norm)')
    conn.commit()
    conn.close()


@st.cache_data
def _carregar_segmentos() -> dict[int, str]:
    try:
        df = pd.read_excel(ARQUIVO_SEGS, sheet_name='Seguimentos', header=0)
        df = df.iloc[:, :2].dropna(subset=[df.columns[0]])
        df.columns = ['id', 'nome']
        df['id'] = df['id'].astype(int)
        return dict(zip(df['id'], df['nome']))
    except Exception:
        return _SEGUIMENTOS_HARDCODED


def _norm(v) -> str:
    return re.sub(r'[\s./\\-]', '', str(v)).strip()


def _safe_num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ('', 'nan'):
        return None
    try:
        return float(str(v).replace(',', '.'))
    except ValueError:
        return None


def _safe_int(v):
    if v is None or str(v).strip() in ('', 'nan'):
        return None
    try:
        return int(float(str(v)))
    except (ValueError, TypeError):
        return None


def _executar_importacao(df_csv: pd.DataFrame) -> None:
    conn = get_conn()
    try:
        removidos = inseridos = 0
        for _, row in df_csv.iterrows():
            ncm  = str(row.get('ncm',  '') or '').strip()
            cest = str(row.get('cest', '') or '').strip()
            if not ncm or ncm == 'nan' or not cest or cest == 'nan':
                continue

            remover_flag = str(row.get('remover', '') or '').strip()
            deve_remover = bool(remover_flag) and remover_flag.lower() not in ('nan', '0', 'false', 'n', 'não', 'nao')

            if deve_remover:
                conn.execute(
                    'DELETE FROM ncm_st WHERE ncm_norm = ? AND cest_norm = ?',
                    (_norm(ncm), _norm(cest)),
                )
                removidos += 1
            else:
                conn.execute(
                    'DELETE FROM ncm_st WHERE ncm_norm = ? AND cest_norm = ?',
                    (_norm(ncm), _norm(cest)),
                )
                conn.execute(
                    '''INSERT INTO ncm_st
                           (seguimento, cest, cest_norm, ncm, ncm_norm,
                            mva_interno, mva_aliq4, mva_aliq7, mva_aliq12, descricao)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (_safe_int(row.get('seguimento')),
                     cest, _norm(cest), ncm, _norm(ncm),
                     _safe_num(row.get('mva_interno')),
                     _safe_num(row.get('mva_aliq4')),
                     _safe_num(row.get('mva_aliq7')),
                     _safe_num(row.get('mva_aliq12')),
                     str(row.get('descricao', '') or '').strip()),
                )
                inseridos += 1
        conn.commit()
        partes = []
        if inseridos: partes.append(f'{inseridos} inserido(s)/atualizado(s)')
        if removidos: partes.append(f'{removidos} removido(s)')
        st.success(' · '.join(partes) + '.')
        st.session_state.aguardando_confirmacao_delete = False
        st.rerun()
    except Exception as e:
        st.error(f'Erro ao importar: {e}')
    finally:
        conn.close()


def _campos_ncm_st(ncm='', cest='', seg=None, desc='', mva_int=None, mva_a4=None, mva_a7=None, mva_a12=None):
    """Renderiza os campos do formulário de NCM/CEST e retorna os valores digitados."""
    segs = _carregar_segmentos()
    ids_seg = sorted(segs.keys())

    # Normaliza valores vindos de linhas do pandas (podem chegar como NaN, não None)
    seg     = _safe_int(seg)
    mva_int = _safe_num(mva_int)
    mva_a4  = _safe_num(mva_a4)
    mva_a7  = _safe_num(mva_a7)
    mva_a12 = _safe_num(mva_a12)
    ncm_str  = '' if ncm  is None or (isinstance(ncm, float)  and pd.isna(ncm))  else str(ncm)
    cest_str = '' if cest is None or (isinstance(cest, float) and pd.isna(cest)) else str(cest)
    desc_str = '' if desc is None or (isinstance(desc, float) and pd.isna(desc)) else str(desc)

    ncm_v  = st.text_input('NCM *', value=ncm_str, placeholder='ex: 30049099')
    cest_v = st.text_input('CEST *', value=cest_str, placeholder='ex: 13.001.00')

    if ids_seg:
        idx_seg = ids_seg.index(seg) if seg is not None and seg in ids_seg else 0
        seg_v = st.selectbox(
            'Seguimento', options=ids_seg, index=idx_seg,
            format_func=lambda k: f'{k} — {segs.get(k, "?")}',
        )
    else:
        seg_v = st.number_input('Seguimento (nº)', min_value=1, step=1, value=seg or 1)

    desc_v = st.text_input('Descrição', value=desc_str)

    c1, c2 = st.columns(2)
    mva_int_v = c1.number_input('MVA Oper. Interna (%)', min_value=0.0, step=0.01, format='%.2f',
                                 value=mva_int or 0.0)
    mva_a4_v  = c2.number_input('MVA Alíq. 4%', min_value=0.0, step=0.01, format='%.2f',
                                 value=mva_a4 or 0.0)
    c3, c4 = st.columns(2)
    mva_a7_v  = c3.number_input('MVA Alíq. 7%', min_value=0.0, step=0.01, format='%.2f',
                                 value=mva_a7 or 0.0)
    mva_a12_v = c4.number_input('MVA Alíq. 12%', min_value=0.0, step=0.01, format='%.2f',
                                 value=mva_a12 or 0.0)

    return ncm_v, cest_v, seg_v, desc_v, mva_int_v, mva_a4_v, mva_a7_v, mva_a12_v


@st.dialog('➕ Novo NCM/CEST')
def _dialog_novo():
    ncm_v, cest_v, seg_v, desc_v, mva_int_v, mva_a4_v, mva_a7_v, mva_a12_v = _campos_ncm_st()

    ncm_v, cest_v, desc_v = (ncm_v or '').strip(), (cest_v or '').strip(), (desc_v or '').strip()

    if st.button('💾 Salvar', type='primary', use_container_width=True):
        if not ncm_v or not cest_v:
            st.error('NCM e CEST são obrigatórios.')
        else:
            conn = get_conn()
            conn.execute(
                '''INSERT INTO ncm_st
                       (seguimento, cest, cest_norm, ncm, ncm_norm,
                        mva_interno, mva_aliq4, mva_aliq7, mva_aliq12, descricao)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (seg_v, cest_v, _norm(cest_v), ncm_v, _norm(ncm_v),
                 mva_int_v or None, mva_a4_v or None, mva_a7_v or None, mva_a12_v or None,
                 desc_v),
            )
            conn.commit()
            conn.close()
            st.success('NCM/CEST criado com sucesso.')
            st.rerun()


@st.dialog('✏️ Editar NCM/CEST')
def _dialog_editar(registro: dict):
    ncm_v, cest_v, seg_v, desc_v, mva_int_v, mva_a4_v, mva_a7_v, mva_a12_v = _campos_ncm_st(
        ncm=registro['ncm'], cest=registro['cest'], seg=registro['seguimento'],
        desc=registro['descricao'], mva_int=registro['mva_interno'], mva_a4=registro['mva_aliq4'],
        mva_a7=registro['mva_aliq7'], mva_a12=registro['mva_aliq12'],
    )

    ncm_v, cest_v, desc_v = (ncm_v or '').strip(), (cest_v or '').strip(), (desc_v or '').strip()

    col_salvar, col_cancelar = st.columns(2)
    if col_salvar.button('💾 Salvar alterações', type='primary', use_container_width=True):
        if not ncm_v or not cest_v:
            st.error('NCM e CEST são obrigatórios.')
        else:
            conn = get_conn()
            conn.execute(
                '''UPDATE ncm_st SET seguimento=?, cest=?, cest_norm=?, ncm=?, ncm_norm=?,
                       mva_interno=?, mva_aliq4=?, mva_aliq7=?, mva_aliq12=?, descricao=?
                   WHERE id=?''',
                (seg_v, cest_v, _norm(cest_v), ncm_v, _norm(ncm_v),
                 mva_int_v or None, mva_a4_v or None, mva_a7_v or None, mva_a12_v or None,
                 desc_v, int(registro['id'])),
            )
            conn.commit()
            conn.close()
            st.success('Registro atualizado.')
            st.rerun()
    if col_cancelar.button('Cancelar', use_container_width=True):
        st.rerun()


@st.dialog('🗑️ Excluir NCM/CEST')
def _dialog_excluir(registro: dict):
    st.warning(
        f"Deseja excluir permanentemente o NCM **{registro['ncm']}** "
        f"/ CEST **{registro['cest']}** da base de dados?"
    )
    col_sim, col_nao = st.columns(2)
    if col_sim.button('🗑️ Sim, excluir', type='primary', use_container_width=True):
        conn = get_conn()
        conn.execute('DELETE FROM ncm_st WHERE id = ?', (int(registro['id']),))
        conn.commit()
        conn.close()
        st.success('Registro excluído.')
        st.rerun()
    if col_nao.button('Cancelar', use_container_width=True):
        st.rerun()


def _verificar_estado_chrome() -> dict:
    """Executa check_econet_state.py e retorna o dict de estado."""
    import urllib.request

    # Teste rápido de porta — se 9222 não responder, Playwright nem precisa rodar
    try:
        urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=2)
    except Exception as porta_err:
        return {
            'conectado': False, 'logado': False, 'pagina_correta': False,
            'url': '',
            'erro': (
                f'Porta 9222 não responde ({porta_err}). '
                'Use o botão "🌐 Abrir Econet" para lançar o Chrome com depuração ativa.'
            ),
        }

    # Porta responde — chama o verificador Playwright
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(ROOT, 'scripts', 'check_econet_state.py')],
            capture_output=True, text=True, timeout=12, cwd=ROOT,
        )
        stdout = (result.stdout or '').strip()
        if stdout:
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                pass
        # Script não produziu JSON válido — mostra o traceback
        stderr = (result.stderr or '').strip()[:500]
        return {
            'conectado': False, 'logado': False, 'pagina_correta': False,
            'url': '',
            'erro': f'Script falhou (rc={result.returncode}): {stderr or "sem saída"}',
        }
    except subprocess.TimeoutExpired:
        return {
            'conectado': False, 'logado': False, 'pagina_correta': False,
            'url': '', 'erro': 'Timeout (>12 s). Playwright pode estar travado.',
        }
    except Exception as e:
        return {'conectado': False, 'logado': False, 'pagina_correta': False,
                'url': '', 'erro': str(e)}


def _abrir_chrome_econet() -> tuple[bool, str]:
    """
    Abre o Chrome com porta de debug apontando para o Econet.
    Se já estiver respondendo na porta 9222, informa sem abrir nova instância.
    """
    import urllib.request

    # Verifica se a porta já está ativa
    try:
        urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=1)
        return True, 'ja_conectado'
    except Exception:
        pass

    # Localiza o executável do Chrome
    chrome_paths = [
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Google\Chrome\Application\chrome.exe'),
    ]
    chrome = next((p for p in chrome_paths if os.path.exists(p)), None)
    if not chrome:
        return False, 'Chrome não encontrado. Instale o Google Chrome ou ajuste o caminho.'

    perfil = os.path.join(tempfile.gettempdir(), 'ChromeDebugEconet')
    try:
        subprocess.Popen([
            chrome,
            '--remote-debugging-port=9222',
            f'--user-data-dir={perfil}',
            '--no-first-run',
            '--no-default-browser-check',
            'https://www.econeteditora.com.br/',
        ])
        return True, ''
    except Exception as e:
        return False, str(e)


def _garantir_colunas_scraper():
    """Adiciona scraped_em e aliquota_interna à ncm_st se ainda não existem."""
    conn = get_conn()
    for col, tipo in [('aliquota_interna', 'REAL'), ('scraped_em', 'TEXT')]:
        try:
            conn.execute(f'ALTER TABLE ncm_st ADD COLUMN {col} {tipo}')
            conn.commit()
        except Exception:
            pass
    conn.close()


def _get_stats_scraper() -> tuple[int, int, int, int]:
    """Retorna (total, atualizados, sem_resultado, pendentes) da raspagem Econet."""
    try:
        conn = get_conn()
        total   = conn.execute('SELECT COUNT(*) FROM ncm_st').fetchone()[0]
        atuali  = conn.execute(
            "SELECT COUNT(*) FROM ncm_st WHERE scraped_em IS NOT NULL "
            "AND scraped_em NOT LIKE '%SEM_RESULTADO%'"
        ).fetchone()[0]
        sem_res = conn.execute(
            "SELECT COUNT(*) FROM ncm_st WHERE scraped_em LIKE '%SEM_RESULTADO%'"
        ).fetchone()[0]
        pend    = conn.execute(
            'SELECT COUNT(*) FROM ncm_st WHERE scraped_em IS NULL'
        ).fetchone()[0]
        conn.close()
        return total, atuali, sem_res, pend
    except Exception:
        return 0, 0, 0, 0


def _ultimo_log_scraper() -> str | None:
    """Retorna o caminho do log mais recente do scraper Econet, ou None."""
    arquivos = sorted(
        glob.glob(os.path.join(ROOT, 'logs', 'scraper_econet_*.log')),
        reverse=True,
    )
    return arquivos[0] if arquivos else None


st.set_page_config(page_title='NCM ST', page_icon='📋', layout='wide')
aplicar_tema_contili()
_init_ncm_st_table()

conn = get_conn()
total_db = conn.execute('SELECT COUNT(*) FROM ncm_st').fetchone()[0]
conn.close()

page_header(
    'NCM ST',
    'Cadastro de NCMs e CESTs sujeitos ao ICMS-ST no MS com MVA por alíquota interestadual.',
)

# ── 1. Pesquisa ───────────────────────────────────────────────────────────────
col_titulo, col_novo = st.columns([5, 1])
col_titulo.subheader('🔍 Pesquisar')
col_novo.markdown('<div style="margin-top:8px"></div>', unsafe_allow_html=True)
if col_novo.button('➕ Novo NCM/CEST', use_container_width=True):
    _dialog_novo()

st.caption(
    'Pesquise por NCM parcial (`3004`) para ver todos os NCMs com essa raiz, '
    'ou por NCM completo (`30049099`) para encontrar também as raízes que o abrangem. '
    'Campos usados em conjunto aplicam filtro **E** (AND).'
)

if total_db == 0:
    st.warning('Cadastro vazio. Importe um CSV abaixo para carregar os dados, ou clique em ➕ Novo NCM/CEST acima.')
else:
    c1, c2, c3 = st.columns([2, 2, 1])
    ncm_input  = c1.text_input('NCM', placeholder='ex: 3004 ou 30049099')
    cest_input = c2.text_input('CEST', placeholder='ex: 1300100 ou 13.001.00')
    c3.markdown('<div style="margin-top:28px"></div>', unsafe_allow_html=True)
    pesquisar  = c3.button('🔍 Pesquisar', use_container_width=True, type='primary')

    if pesquisar or ncm_input.strip() or cest_input.strip():
        ncm_q  = _norm(ncm_input)  if ncm_input.strip()  else ''
        cest_q = _norm(cest_input) if cest_input.strip() else ''

        conditions: list[str] = []
        params: list = []

        if ncm_q:
            conditions.append("(ncm_norm LIKE ? OR ? LIKE ncm_norm || '%')")
            params += [ncm_q + '%', ncm_q]

        if cest_q:
            conditions.append("cest_norm LIKE ?")
            params.append('%' + cest_q + '%')

        where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
        sql = f'''
            SELECT id, seguimento, cest, ncm, ncm_norm,
                   mva_interno, mva_aliq4, mva_aliq7, mva_aliq12, descricao
            FROM ncm_st {where}
            ORDER BY seguimento, cest_norm, ncm_norm
            LIMIT 500
        '''

        conn = get_conn()
        rows = conn.execute(sql, params).fetchall()
        conn.close()

        if not rows:
            st.info('Nenhum resultado encontrado.')
        else:
            SEGS = _carregar_segmentos()
            df_res = pd.DataFrame([dict(r) for r in rows])
            df_res['Seg.'] = df_res['seguimento'].apply(lambda s: int(s) if pd.notna(s) else None)

            compacto = df_res[['ncm', 'cest', 'Seg.', 'descricao']].rename(columns={
                'ncm': 'NCM', 'cest': 'CEST', 'descricao': 'Descrição',
            })

            limite = ' (limitado a 500)' if len(rows) == 500 else ''
            st.caption(f'{len(rows)} resultado(s){limite} — clique em uma linha para ver os MVAs')

            evento = st.dataframe(
                compacto,
                use_container_width=True,
                hide_index=True,
                on_select='rerun',
                selection_mode='single-row',
            )

            sel = evento.selection.rows
            if sel:
                r = df_res.iloc[sel[0]]
                seg_raw = r['seguimento']
                seg_nome = f"{int(seg_raw)} — {SEGS.get(int(seg_raw), '?')}" if pd.notna(seg_raw) else '—'

                st.divider()
                st.markdown(
                    f"**NCM:** `{r['ncm']}` &nbsp;&nbsp; **CEST:** `{r['cest']}` "
                    f"&nbsp;&nbsp; **Seguimento:** {seg_nome}"
                )
                st.caption(r['descricao'] or '')

                def _fmt(v):
                    return f"{v:.2f} %" if pd.notna(v) and v is not None else '—'

                ca, cb, cc, cd = st.columns(4)
                ca.metric('MVA Oper. Interna', _fmt(r['mva_interno']))
                cb.metric('MVA Alíq. 4%',      _fmt(r['mva_aliq4']))
                cc.metric('MVA Alíq. 7%',      _fmt(r['mva_aliq7']))
                cd.metric('MVA Alíq. 12%',     _fmt(r['mva_aliq12']))

                col_edit, col_del = st.columns(2)
                if col_edit.button('✏️ Editar', use_container_width=True, key='btn_editar_ncm'):
                    _dialog_editar(r.to_dict())
                if col_del.button('🗑️ Excluir', use_container_width=True, key='btn_excluir_ncm'):
                    _dialog_excluir(r.to_dict())

            csv_df = df_res[['ncm', 'cest', 'Seg.', 'descricao',
                              'mva_interno', 'mva_aliq4', 'mva_aliq7', 'mva_aliq12']].rename(columns={
                'ncm': 'NCM', 'cest': 'CEST', 'descricao': 'Descrição',
                'mva_interno': 'MVA Oper. Interna (%)',
                'mva_aliq4': 'MVA Alíq. 4%', 'mva_aliq7': 'MVA Alíq. 7%', 'mva_aliq12': 'MVA Alíq. 12%',
            })
            csv_df.insert(2, 'Remover', '')
            csv_bytes = csv_df.to_csv(index=False, decimal=',', sep=';').encode('utf-8-sig')
            st.download_button(
                '⬇️ Exportar CSV', data=csv_bytes,
                file_name='ncm_st_resultado.csv', mime='text/csv',
            )

    else:
        SEGS = _carregar_segmentos()
        conn = get_conn()
        resumo = conn.execute(
            'SELECT seguimento, COUNT(*) as total FROM ncm_st GROUP BY seguimento ORDER BY seguimento'
        ).fetchall()
        conn.close()

        st.caption('Totais por seguimento — use os campos acima para pesquisar.')
        df_resumo = pd.DataFrame([dict(r) for r in resumo])
        df_resumo['Seguimento'] = df_resumo['seguimento'].apply(
            lambda s: f"{int(s)} — {SEGS.get(int(s), '?')}" if pd.notna(s) else '—'
        )
        df_resumo = df_resumo.rename(columns={'total': 'Registros'})[['Seguimento', 'Registros']]
        st.dataframe(df_resumo, use_container_width=True, hide_index=True)

st.divider()

# ── 2. Atualizar cadastro via CSV ─────────────────────────────────────────────
col_m, col_info = st.columns([3, 1])
col_m.metric('Registros no cadastro', total_db)

with col_info:
    with st.popover('ℹ️ Como atualizar', use_container_width=True):
        st.markdown("""
**O arquivo CSV é um patch — somente os NCMs presentes no arquivo são afetados.
Os demais registros do banco não são alterados.**

**Formato das colunas:**

| Coluna | Exemplo | Obrigatório |
|---|---|---|
| `NCM` | `3004` ou `30049099` | ✔ |
| `CEST` | `13.001.00` | ✔ |
| `Remover` | `S` | — |
| `Seg.` | `13` | — |
| `Descrição` | Medicamentos de referência | — |
| `MVA Oper. Interna (%)` | `35,12` | — |
| `MVA Alíq. 4%` | `41,83` | — |
| `MVA Alíq. 7%` | `38,57` | — |
| `MVA Alíq. 12%` | `32,22` | — |

**Separador:** `;` · **Decimal:** `,` · **Encoding:** UTF-8

**Para atualizar valores:** deixe `Remover` vazio — o registro é inserido ou atualizado.

**Para excluir um NCM:** coloque qualquer valor na coluna `Remover` (ex: `S`) — o registro é removido do banco.

Use **⬇️ Exportar CSV** na pesquisa para gerar o arquivo base já com a coluna `Remover`.
        """)

if 'aguardando_confirmacao_delete' not in st.session_state:
    st.session_state.aguardando_confirmacao_delete = False

csv_upload = st.file_uploader(
    '📥 Atualizar cadastro — selecione o CSV',
    type='csv',
    help='Mesmo formato do arquivo exportado pela pesquisa.',
)

if csv_upload:
    try:
        df_csv = pd.read_csv(csv_upload, sep=';', decimal=',', dtype=str)
        df_csv.columns = [c.strip() for c in df_csv.columns]

        colunas_faltando = COLUNAS_ESPERADAS - set(df_csv.columns)
        if colunas_faltando:
            st.error(
                f'Arquivo rejeitado — coluna(s) ausente(s): **{", ".join(sorted(colunas_faltando))}**. '
                'Use **⬇️ Exportar CSV** na pesquisa para gerar o modelo correto com todas as colunas.'
            )
        else:
            col_map = {
                'NCM':                   'ncm',
                'CEST':                  'cest',
                'Remover':               'remover',
                'Seg.':                  'seguimento',
                'Descrição':             'descricao',
                'MVA Oper. Interna (%)': 'mva_interno',
                'MVA Alíq. 4%':          'mva_aliq4',
                'MVA Alíq. 7%':          'mva_aliq7',
                'MVA Alíq. 12%':         'mva_aliq12',
            }
            df_csv = df_csv.rename(columns={k: v for k, v in col_map.items() if k in df_csv.columns})

            mask_rem = df_csv['remover'].apply(
                lambda v: bool(str(v).strip()) and str(v).strip().lower() not in ('nan', '0', 'false', 'n', 'não', 'nao')
            )
            df_para_remover = df_csv[mask_rem]
            df_para_upsert  = df_csv[~mask_rem]
            n_rem = len(df_para_remover)
            n_upd = len(df_para_upsert)

            prev_cols = ['remover', 'ncm', 'cest', 'descricao', 'mva_interno']
            st.caption(f'Prévia — {len(df_csv)} linha(s): **{n_upd} para inserir/atualizar**, **{n_rem} para remover**. Verifique antes de confirmar.')
            st.dataframe(df_csv[prev_cols].head(10), use_container_width=True, hide_index=True)

            if not st.session_state.aguardando_confirmacao_delete:
                if st.button('✅ Confirmar importação', type='primary'):
                    if n_rem > 0:
                        st.session_state.aguardando_confirmacao_delete = True
                        st.rerun()
                    else:
                        _executar_importacao(df_csv)

            if st.session_state.aguardando_confirmacao_delete and n_rem > 0:
                st.divider()
                if n_rem == 1:
                    row_exc = df_para_remover.iloc[0]
                    ncm_val  = str(row_exc.get('ncm',  '') or '').strip()
                    cest_val = str(row_exc.get('cest', '') or '').strip()
                    st.warning(
                        f'⚠️ Deseja excluir permanentemente o NCM **{ncm_val}** '
                        f'e CEST **{cest_val}** da base de dados?'
                    )
                else:
                    st.warning(
                        f'⚠️ Deseja excluir permanentemente os **{n_rem} registros** abaixo da base de dados?'
                    )
                    df_exc = df_para_remover[['ncm', 'cest']].rename(columns={'ncm': 'NCM', 'cest': 'CEST'})
                    st.dataframe(df_exc, use_container_width=True, hide_index=True)

                col_sim, col_nao = st.columns(2)
                if col_sim.button('🗑️ Sim, excluir', type='primary', use_container_width=True):
                    _executar_importacao(df_csv)
                if col_nao.button('❌ Cancelar', use_container_width=True):
                    st.session_state.aguardando_confirmacao_delete = False
                    st.info('Operação cancelada.')
                    st.rerun()

    except Exception as e:
        st.error(f'Erro ao ler o arquivo: {e}')

st.divider()

# ── 3. Atualizar via Econet ───────────────────────────────────────────────────
with st.expander('🌐 Atualizar via Econet — Raspagem Automática', expanded=False):
    st.info('⏳ Aguarde em Desenvolvimento')
