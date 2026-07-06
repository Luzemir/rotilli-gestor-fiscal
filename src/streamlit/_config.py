"""Configuração compartilhada entre todas as páginas do Streamlit."""
import os
import sys
import sqlite3


def _load_logo() -> str:
    """Carrega logo_contili.png como data URI base64. Retorna '' se não encontrar."""
    import base64 as _b64
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'static', 'logo_contili.png')
    try:
        with open(_p, 'rb') as _f:
            return f'data:image/png;base64,{_b64.b64encode(_f.read()).decode()}'
    except Exception:
        return ''


_LOGO_SRC = _load_logo()

# ── CSS global do tema Contili ─────────────────────────────────────────────────
_TEMA_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@400;600;700;800&display=swap');

/* ── TOKENS ── */
:root {
  --c-bg:         #F3F5F8;
  --c-surface:    #FFFFFF;
  --c-fg:         #142158;
  --c-muted:      #5A6480;
  --c-border:     #E3E6EF;
  --c-primary:    #1B3A78;
  --c-accent:     #F7901E;
  --c-accent-dim: #D97B15;
  --c-sidebar:    #18223E;
  --c-success:    #2D8A5F;
  --c-success-bg: #EEF8F4;
  --c-warn:       #8A6200;
  --c-warn-bg:    #FDF6DC;
  --c-danger:     #B83228;
  --c-danger-bg:  #FDEEEC;
  --r-sm: 6px; --r-md: 10px; --r-lg: 14px;
  --ff-display: 'Nunito Sans', 'Segoe UI', system-ui, sans-serif;
  --ff-mono:    'JetBrains Mono', 'Cascadia Code', ui-monospace, monospace;
}

/* ── APP BACKGROUND ── */
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"] { background: var(--c-bg) !important; }

/* ── SIDEBAR SHELL ── */
[data-testid="stSidebar"],
[data-testid="stSidebar"] > div:first-child {
  background: var(--c-sidebar) !important;
}
[data-testid="stSidebarContent"] {
  display: flex !important;
  flex-direction: column !important;
  height: 100% !important;
  padding-bottom: 0 !important;
}
/* Logo injected via JS antes do stSidebarNav — ordem segue o DOM, sem order CSS */
.ctili-sidebar-logo { flex-shrink: 0; }

/* ── NAV LINKS ── */
[data-testid="stSidebarNavLink"] {
  display: flex !important;
  align-items: center !important;
  gap: 10px !important;
  padding: 9px 20px !important;
  color: rgba(255,255,255,0.55) !important;
  border-radius: 0 !important;
  font-size: 13px !important;
  font-weight: 600 !important;
  letter-spacing: 0.01em !important;
  border-left: 3px solid transparent !important;
  transition: background 0.12s, color 0.12s !important;
}
[data-testid="stSidebarNavLink"]:hover {
  background: rgba(255,255,255,0.05) !important;
  color: rgba(255,255,255,0.88) !important;
}
[data-testid="stSidebarNavLink"][aria-current="page"] {
  background: rgba(255,255,255,0.08) !important;
  color: #ffffff !important;
  border-left-color: var(--c-accent) !important;
}
[data-testid="stSidebarNavLink"] svg { opacity: 0.65; }
[data-testid="stSidebarNavLink"][aria-current="page"] svg { opacity: 1 !important; }

/* Texto genérico na sidebar */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span { color: rgba(255,255,255,0.55) !important; }
[data-testid="stSidebar"] label { color: rgba(255,255,255,0.75) !important; }

/* ── TOPBAR ── */
[data-testid="stHeader"] {
  background: var(--c-surface) !important;
  border-bottom: 1px solid var(--c-border) !important;
}

/* ── TIPOGRAFIA ── */
h1, h2, h3 { font-family: var(--ff-display) !important; font-weight: 800 !important; }

/* ── PAGE HEADER COMPONENT ── */
.ctili-page-hd { padding-bottom: 18px; }
.ctili-h1 {
  font-family: var(--ff-display) !important;
  font-size: 20px !important;
  font-weight: 800 !important;
  letter-spacing: -0.02em !important;
  line-height: 1.2 !important;
  color: var(--c-fg) !important;
  margin: 0 0 3px !important;
}
.ctili-sub {
  font-size: 13px !important;
  color: var(--c-muted) !important;
  margin: 0 !important;
}

/* ── BOTÕES ── */
.stButton > button {
  border-radius: var(--r-sm) !important;
  font-family: var(--ff-display) !important;
  font-weight: 700 !important;
  font-size: 13px !important;
  letter-spacing: 0.02em !important;
  transition: background 0.14s !important;
}
.stButton > button[kind="primary"] {
  background: var(--c-accent) !important;
  color: #fff !important;
  border: none !important;
}
.stButton > button[kind="primary"]:hover { background: var(--c-accent-dim) !important; }
.stButton > button[kind="secondary"] {
  background: var(--c-surface) !important;
  color: var(--c-fg) !important;
  border: 1px solid var(--c-border) !important;
}
.stButton > button[kind="secondary"]:hover { background: var(--c-bg) !important; }

/* ── KPI CARDS (st.metric) ── */
[data-testid="metric-container"],
[data-testid="stMetric"] {
  background: var(--c-surface) !important;
  border: 1px solid var(--c-border) !important;
  border-radius: var(--r-md) !important;
  padding: 18px 20px !important;
}
[data-testid="stMetricLabel"] > div,
[data-testid="stMetricLabel"] label {
  font-size: 10.5px !important;
  font-weight: 700 !important;
  color: var(--c-muted) !important;
  text-transform: uppercase !important;
  letter-spacing: 0.08em !important;
}
[data-testid="stMetricValue"] > div {
  font-family: var(--ff-display) !important;
  font-size: 28px !important;
  font-weight: 800 !important;
  color: var(--c-primary) !important;
}

/* ── CONTAINERS COM BORDA ── */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--c-surface) !important;
  border: 1px solid var(--c-border) !important;
  border-radius: var(--r-md) !important;
}

/* ── FILE UPLOADER ── */
[data-testid="stFileUploaderDropzone"] {
  border: 2px dashed var(--c-border) !important;
  border-radius: var(--r-lg) !important;
  background: var(--c-surface) !important;
}
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--c-accent) !important; }

/* ── DATAFRAME ── */
[data-testid="stDataFrame"] {
  border: 1px solid var(--c-border) !important;
  border-radius: var(--r-md) !important;
  overflow: hidden !important;
}

/* ── RADIO — FILTER PILLS ── */
[data-testid="stRadio"] > div { gap: 6px !important; flex-wrap: wrap !important; }
[data-testid="stRadio"] label {
  padding: 6px 14px !important;
  border-radius: 20px !important;
  border: 1.5px solid var(--c-border) !important;
  background: var(--c-surface) !important;
  font-size: 12px !important;
  font-weight: 700 !important;
  color: var(--c-muted) !important;
  cursor: pointer !important;
  transition: all 0.12s !important;
}
[data-testid="stRadio"] label:has(input:checked) {
  background: var(--c-primary) !important;
  border-color: var(--c-primary) !important;
  color: #fff !important;
}
[data-testid="stRadio"] label:has(input:checked) * {
  color: #fff !important;
}

/* ── TABS ── */
[data-testid="stTab"] button {
  font-weight: 700 !important;
  font-size: 12.5px !important;
  color: var(--c-muted) !important;
}
[data-testid="stTab"] button[aria-selected="true"] {
  color: var(--c-primary) !important;
  border-bottom-color: var(--c-accent) !important;
}

/* ── INPUTS ── */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input { border-radius: var(--r-sm) !important; font-size: 13px !important; }

/* ── ALERTAS / CALLOUTS ── */
[data-testid="stAlert"] { border-radius: var(--r-md) !important; }

/* ── BADGES ── */
.ctili-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
  white-space: nowrap;
  line-height: 1.5;
}
.ctili-b-ok      { background: var(--c-success-bg); color: var(--c-success); }
.ctili-b-warn    { background: var(--c-warn-bg);    color: var(--c-warn); }
.ctili-b-danger  { background: var(--c-danger-bg);  color: var(--c-danger); }
.ctili-b-neutral { background: var(--c-bg);         color: var(--c-muted); border: 1px solid var(--c-border); }
.ctili-b-primary { background: rgba(27,58,120,0.08); color: var(--c-primary); }

/* ── MONO ── */
.ctili-mono { font-family: var(--ff-mono) !important; font-size: 11.5px; color: var(--c-muted); }

/* ── DIVIDER ── */
hr { border-color: var(--c-border) !important; }

/* ── OCULTAR CHROME DO STREAMLIT ── */
footer { display: none !important; }
#MainMenu { visibility: hidden !important; }
/* stToolbar só existe no DOM quando a sidebar está colapsada (renderizado condicionalmente)
   — contém stExpandSidebarButton, não pode ser ocultado */
[data-testid="stToolbar"] {
  background: transparent !important;
  box-shadow: none !important;
  border: none !important;
}
[data-testid="stDecoration"] { display: none !important; }

/* ── LOGO via st.logo() ── */
[data-testid="stSidebarHeader"] {
  padding: 14px 16px 10px !important;
  border-bottom: 1px solid rgba(255,255,255,0.07) !important;
}
[data-testid="stSidebarHeader"] img {
  height: 72px !important;
  width: auto !important;
  max-width: 100% !important;
}

/* Botão de expandir sidebar (aparece somente quando sidebar está colapsada) */
[data-testid="stExpandSidebarButton"] {
  background: var(--c-sidebar) !important;
  border-radius: 0 var(--r-sm) var(--r-sm) 0 !important;
}
[data-testid="stExpandSidebarButton"] svg {
  fill: #ffffff !important;
  color: #ffffff !important;
}

/* ── SIDEBAR: bloco de usuário logado ── */
.ctili-user-sidebar {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 16px 8px;
  border-top: 1px solid rgba(255,255,255,0.06);
  margin-top: 4px;
}
.ctili-us-avatar {
  width: 32px; height: 32px; border-radius: 50%;
  background: #F7901E;
  display: flex; align-items: center; justify-content: center;
  font-family: 'Nunito Sans', sans-serif;
  font-size: 12px; font-weight: 800; color: #fff; flex-shrink: 0;
}
.ctili-us-nome   { font-size: 13px; font-weight: 700; color: rgba(255,255,255,.85); line-height: 1.3; }
.ctili-us-perfil { font-size: 11px; color: rgba(255,255,255,.4); }

/* ── SIDEBAR: botão Sair — targeting direto em button para garantir override ── */
[data-testid="stSidebar"] button {
  background: rgba(255,255,255,0.06) !important;
  border: 1px solid rgba(255,255,255,0.14) !important;
  border-radius: 6px !important;
  font-size: 12.5px !important;
}
[data-testid="stSidebar"] button p,
[data-testid="stSidebar"] button span {
  color: rgba(255,255,255,0.65) !important;
}
[data-testid="stSidebar"] button:hover {
  background: rgba(255,255,255,0.11) !important;
  border-color: rgba(255,255,255,0.24) !important;
}
[data-testid="stSidebar"] button:hover p,
[data-testid="stSidebar"] button:hover span {
  color: rgba(255,255,255,0.85) !important;
}
</style>
"""

def _build_sidebar_js(perfil: str = "") -> str:
    """JS mínimo: esconde Admin para não-admins e renomeia 'app' → 'Painel Geral'."""
    import json
    p = json.dumps(perfil)
    return f"""
<script>
(function() {{
  var R = window.parent?.document ?? document;
  var _perfil  = {p};
  var _isAdmin = _perfil === 'Administrador';

  function processNavLinks() {{
    R.querySelectorAll('[data-testid="stSidebarNavLink"]').forEach(function(a) {{
      a.querySelectorAll('span').forEach(function(s) {{
        if (s.childElementCount > 0) return;
        var txt = s.textContent.trim();
        if (txt === 'app') s.textContent = 'Painel Geral';
        if (!_isAdmin && txt === 'Admin') {{
          (a.closest('li') || a.parentElement).style.display = 'none';
        }}
      }});
    }});
  }}

  new MutationObserver(processNavLinks).observe(R.body, {{ childList: true, subtree: true }});
  processNavLinks();
  setTimeout(processNavLinks, 300);
}})();
</script>
"""

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'src', 'core'))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
os.chdir(ROOT)

DB_PATH = os.environ.get("DB_PATH", os.path.join(ROOT, 'src', 'db', 'gestor_fiscal.db'))

MAPA_MOD_BC = {
    '0': 'PMC — Tabela CMED',
    '1': 'Lista Positiva',
    '2': 'Lista Negativa',
    '3': 'Lista Neutra',
    '4': 'MVA — Margem de Valor Agregado',
    '5': 'Normal / Sem Substituição Tributária',
}


def get_conn():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_senha(senha: str) -> str:
    import hashlib
    return hashlib.sha256(senha.encode('utf-8')).hexdigest()


def init_sessoes_table():
    conn = get_conn()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sessoes (
            token      TEXT PRIMARY KEY,
            username   TEXT NOT NULL,
            nome       TEXT,
            perfil     TEXT,
            iniciais   TEXT,
            criado_em  TEXT DEFAULT CURRENT_TIMESTAMP,
            expira_em  TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()


def criar_sessao(username: str, nome: str, perfil: str, iniciais: str) -> str:
    import uuid
    from datetime import datetime, timedelta, timezone
    token = uuid.uuid4().hex
    expira = (datetime.now(timezone.utc) + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    conn = get_conn()
    conn.execute(
        "DELETE FROM sessoes WHERE username=? OR expira_em < DATETIME('now')",
        (username,)
    )
    conn.execute(
        'INSERT INTO sessoes (token, username, nome, perfil, iniciais, expira_em) VALUES (?,?,?,?,?,?)',
        (token, username, nome, perfil, iniciais, expira)
    )
    conn.commit()
    conn.close()
    return token


def validar_sessao(token: str):
    if not token:
        return None
    try:
        conn = get_conn()
        row = conn.execute(
            "SELECT username, nome, perfil, iniciais FROM sessoes "
            "WHERE token=? AND expira_em > DATETIME('now')",
            (token,)
        ).fetchone()
        conn.close()
        if row:
            return dict(row)
        return None
    except Exception:
        return None


def revogar_sessao(token: str):
    if not token:
        return
    try:
        conn = get_conn()
        conn.execute('DELETE FROM sessoes WHERE token=?', (token,))
        conn.commit()
        conn.close()
    except Exception:
        pass


def autenticar():
    """
    Exibe tela de login se o usuário não estiver autenticado.
    Bloqueia o resto da página com st.stop() até autenticação.
    Credenciais configuradas em .streamlit/secrets.toml.
    """
    import streamlit as st

    if st.session_state.get("_auth_ok"):
        return

    init_sessoes_table()

    # Restaurar sessão pelo token persistido na URL (?s=...)
    _token = st.query_params.get("s", "")
    if _token:
        _dados = validar_sessao(_token)
        if _dados:
            st.session_state["_auth_ok"]       = True
            st.session_state["_auth_user"]     = _dados["username"]
            st.session_state["_auth_name"]     = _dados["nome"]
            st.session_state["_auth_perfil"]   = _dados["perfil"]
            st.session_state["_auth_iniciais"] = _dados["iniciais"]
            st.session_state["_auth_token"]    = _token
            return

    st.markdown(_TEMA_CSS, unsafe_allow_html=True)

    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown('<div style="margin-top:72px"></div>', unsafe_allow_html=True)
        if _LOGO_SRC:
            st.markdown(
                f'<div style="text-align:center;margin-bottom:28px">'
                f'<img src="{_LOGO_SRC}" style="width:200px;max-width:100%"></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="font-family:Nunito Sans,Segoe UI,sans-serif;font-size:28px;'
                'font-weight:800;letter-spacing:-0.02em;color:#142158;margin-bottom:2px">'
                '<span style="color:#1B3A78">CONT</span><span style="color:#F7901E">ILI</span></div>'
                '<div style="font-size:13px;color:#5A6480;margin-bottom:28px">Gestor Fiscal</div>',
                unsafe_allow_html=True,
            )
        with st.form("_login"):
            usuario = st.text_input("Usuário")
            senha   = st.text_input("Senha", type="password")
            entrar  = st.form_submit_button("Entrar", type="primary", use_container_width=True)

        if entrar:
            user_key       = usuario.strip().lower()
            autenticado    = False
            nome_display   = usuario
            perfil_display = ""

            # 1. Tabela usuarios no SQLite (gestão via app Admin)
            try:
                _conn = get_conn()
                _row  = _conn.execute(
                    'SELECT senha_hash, nome, perfil FROM usuarios '
                    'WHERE LOWER(username)=? AND ativo=1',
                    (user_key,)
                ).fetchone()
                _conn.close()
                if _row and _row['senha_hash'] == hash_senha(senha):
                    nome_display   = _row['nome']
                    perfil_display = _row['perfil']
                    autenticado    = True
            except Exception:
                pass

            # 2. Fallback: secrets.toml / env vars AUTH_USER_* (compatibilidade)
            if not autenticado:
                try:
                    try:
                        _usuarios = dict(st.secrets.get("usuarios", {}))
                        _nomes    = dict(st.secrets.get("nomes", {}))
                        _perfis   = dict(st.secrets.get("perfis", {}))
                    except Exception:
                        _usuarios, _nomes, _perfis = {}, {}, {}
                    for k, v in os.environ.items():
                        if k.startswith("AUTH_USER_"):
                            _usuarios[k[10:].lower()] = v
                        elif k.startswith("AUTH_NAME_"):
                            _nomes[k[10:].lower()] = v
                        elif k.startswith("AUTH_PERFIL_"):
                            _perfis[k[12:].lower()] = v
                    if user_key in _usuarios and _usuarios[user_key] == senha:
                        nome_display   = _nomes.get(user_key, usuario)
                        perfil_display = _perfis.get(user_key, "")
                        autenticado    = True
                except Exception:
                    pass

            if autenticado:
                iniciais = "".join(p[0].upper() for p in nome_display.split()[:2])
                _tok = criar_sessao(user_key, nome_display, perfil_display, iniciais)
                st.session_state["_auth_ok"]       = True
                st.session_state["_auth_user"]     = user_key
                st.session_state["_auth_name"]     = nome_display
                st.session_state["_auth_perfil"]   = perfil_display
                st.session_state["_auth_iniciais"] = iniciais
                st.session_state["_auth_token"]    = _tok
                st.query_params["s"]               = _tok
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")

    st.stop()


def aplicar_tema_contili():
    """
    Aplica o tema visual Contili: autenticação, CSS global, logo e user-row na sidebar.
    Chame logo após st.set_page_config(), antes de qualquer outro conteúdo.
    """
    import streamlit as st

    autenticar()
    bloquear_traducao_automatica()
    st.markdown(_TEMA_CSS, unsafe_allow_html=True)

    # Logo nativa do Streamlit na sidebar (st.logo disponível desde 1.36)
    _logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'static', 'logo_contili.png')
    if os.path.exists(_logo_path):
        st.logo(_logo_path)

    nome     = st.session_state.get("_auth_name", "Usuário")
    iniciais = st.session_state.get("_auth_iniciais", "U")
    perfil   = st.session_state.get("_auth_perfil", "")
    st.html(_build_sidebar_js(perfil))  # esconde Admin, renomeia 'app'

    with st.sidebar:
        # Bloco do usuário logado (abaixo dos nav links)
        st.markdown(
            f'<div class="ctili-user-sidebar">'
            f'<div class="ctili-us-avatar">{iniciais}</div>'
            f'<div><div class="ctili-us-nome">{nome}</div>'
            f'<div class="ctili-us-perfil">{perfil}</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("Sair", key="_logout", use_container_width=True):
            revogar_sessao(st.session_state.get("_auth_token", ""))
            for k in ["_auth_ok", "_auth_user", "_auth_name", "_auth_perfil", "_auth_iniciais", "_auth_token"]:
                st.session_state.pop(k, None)
            st.query_params.clear()
            st.rerun()


def page_header(titulo: str, subtitulo: str = ""):
    """
    Renderiza o cabeçalho padrão de página (título + subtítulo).
    Retorna a coluna direita para o botão CTA opcional.

    Uso:
        col_cta = page_header("Título", "Subtítulo")
        with col_cta:
            if st.button("Ação", type="primary"):
                ...
    """
    import streamlit as st
    col_t, col_cta = st.columns([3, 1])
    with col_t:
        sub = f'<p class="ctili-sub">{subtitulo}</p>' if subtitulo else ''
        st.markdown(
            f'<div class="ctili-page-hd"><h1 class="ctili-h1">{titulo}</h1>{sub}</div>',
            unsafe_allow_html=True,
        )
    return col_cta


def badge(texto: str, tipo: str = "neutral") -> str:
    """Retorna HTML de badge colorido. tipo: ok|warn|danger|neutral|primary"""
    _map = {
        "ok":      "ctili-b-ok",
        "warn":    "ctili-b-warn",
        "danger":  "ctili-b-danger",
        "neutral": "ctili-b-neutral",
        "primary": "ctili-b-primary",
    }
    return f'<span class="ctili-badge {_map.get(tipo, "ctili-b-neutral")}">{texto}</span>'


def bloquear_traducao_automatica():
    """
    Evita que o Google Tradutor (Chrome) reescreva o DOM da página.
    Quando o tradutor automático altera nós de texto fora do controle do React,
    o Streamlit pode falhar ao re-renderizar com erro 'NotFoundError: insertBefore'
    após uma interação (ex: clicar numa linha da tabela).
    """
    import streamlit as st
    st.html(
        """
        <script>
        try {
            var doc = window.parent?.document ?? document;
            doc.documentElement.setAttribute('translate', 'no');
            if (!doc.querySelector('meta[name="google"]')) {
                var meta = doc.createElement('meta');
                meta.name = 'google';
                meta.content = 'notranslate';
                doc.head.appendChild(meta);
            }
        } catch (e) {}
        </script>
        """
    )


def init_produtos_table():
    conn = get_conn()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            cnpj_remetente     TEXT NOT NULL,
            cod_produto_origem TEXT NOT NULL,
            descricao_produto  TEXT,
            unidade            TEXT,
            ean                TEXT,
            ncm                TEXT,
            cest               TEXT,
            criado_em          TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (cnpj_remetente, cod_produto_origem)
        )
    ''')
    for col, tipo in [
        ('ean',       'TEXT'),
        ('ncm',       'TEXT'),
        ('cest',      'TEXT'),
        ('criado_em', 'TEXT'),
    ]:
        try:
            conn.execute(f'ALTER TABLE produtos ADD COLUMN {col} {tipo}')
        except Exception:
            pass
    conn.commit()
    conn.close()


def init_alertas_table():
    conn = get_conn()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS produto_alerta (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj_emitente TEXT NOT NULL,
            cod_produto   TEXT NOT NULL,
            ean           TEXT,
            descricao     TEXT,
            ncm           TEXT,
            cest          TEXT,
            num_nf        TEXT,
            data_emissao  TEXT,
            criado_em     TEXT DEFAULT CURRENT_TIMESTAMP,
            status        TEXT DEFAULT 'PENDENTE',
            pre_mod_bc    TEXT,
            pre_pmc       REAL,
            pre_mva       REAL,
            UNIQUE(cnpj_emitente, cod_produto)
        )
    ''')
    # Migração para BD existentes: adiciona colunas novas se ainda não existirem
    for col, tipo in [('ncm', 'TEXT'), ('cest', 'TEXT'), ('pre_mod_bc', 'TEXT'), ('pre_pmc', 'REAL'), ('pre_mva', 'REAL'), ('pre_nota', 'TEXT')]:
        try:
            conn.execute(f'ALTER TABLE produto_alerta ADD COLUMN {col} {tipo}')
        except Exception:
            pass
    conn.commit()
    conn.close()


def init_ncm_st_table():
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


def init_nfe_item_apuracao_table():
    conn = get_conn()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS nfe_item_apuracao (
            chave_acesso       TEXT NOT NULL,
            num_item           INTEGER NOT NULL,
            mes_ano            TEXT NOT NULL,
            tipo_planilha      TEXT NOT NULL DEFAULT 'Original',
            num_nf             TEXT,
            data_emissao       TEXT,
            cnpj_remetente     TEXT,
            razao_remetente    TEXT,
            uf_remetente       TEXT,
            cest               TEXT,
            ncm                TEXT,
            ean                TEXT,
            cfop               TEXT,
            cod_produto_origem TEXT,
            descricao_produto  TEXT,
            unidade            TEXT,
            quantidade         REAL,
            valor_unitario     REAL,
            frete              REAL,
            seguro             REAL,
            ipi_despesas       REAL,
            desconto           REAL,
            bc_icms_origem     REAL,
            vlr_icms_origem    REAL,
            pmc                REAL,
            pmc_cmed           REAL,
            mva                REAL,
            mod_bc_icms_st     TEXT,
            criado_em          TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (chave_acesso, num_item, tipo_planilha)
        )
    ''')
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_nfe_item_mesano
        ON nfe_item_apuracao (mes_ano, tipo_planilha)
    ''')
    for _col, _tipo in [('bc_icms_st_nfe', 'REAL'), ('vlr_icms_st_nfe', 'REAL')]:
        try:
            conn.execute(f'ALTER TABLE nfe_item_apuracao ADD COLUMN {_col} {_tipo}')
        except Exception:
            pass
    conn.commit()
    conn.close()


def init_produto_competencia_table():
    conn = get_conn()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS produto_competencia (
            cnpj_remetente     TEXT,
            cod_produto_origem TEXT,
            mes_ano            TEXT,
            mod_bc_icms_st     TEXT,
            pmc                REAL,
            mva                REAL,
            tipo_planilha      TEXT,
            PRIMARY KEY (cnpj_remetente, cod_produto_origem, mes_ano, tipo_planilha)
        )
    ''')
    conn.commit()
    conn.close()


def init_cmed_historico_table():
    conn = get_conn()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS cmed_historico (
            ean          TEXT,
            produto      TEXT,
            apresentacao TEXT,
            pmc_17       REAL,
            tipo_lista   TEXT,
            mes_ano      TEXT,
            PRIMARY KEY (ean, mes_ano)
        )
    ''')
    conn.commit()
    conn.close()


def init_usuarios_table():
    conn = get_conn()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            username   TEXT NOT NULL UNIQUE COLLATE NOCASE,
            senha_hash TEXT NOT NULL,
            nome       TEXT NOT NULL,
            perfil     TEXT NOT NULL DEFAULT 'Usuário',
            ativo      INTEGER NOT NULL DEFAULT 1,
            criado_em  TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


def init_todas_tabelas():
    """Inicializa todas as tabelas do banco. Chamar no startup do app."""
    init_produtos_table()
    init_produto_competencia_table()
    init_alertas_table()
    init_ncm_st_table()
    init_nfe_item_apuracao_table()
    init_cmed_historico_table()
    init_usuarios_table()
    init_sessoes_table()
