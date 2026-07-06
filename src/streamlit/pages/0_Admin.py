"""
0_Admin.py — Utilitários administrativos (somente Administrador)
"""
import os
import sys
import shutil
import sqlite3
from datetime import datetime

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _config import (
    aplicar_tema_contili, page_header, badge,
    DB_PATH, get_conn, hash_senha, init_usuarios_table,
)

st.set_page_config(
    page_title='Admin — Gestor Fiscal',
    page_icon='⚙️',
    layout='wide',
)

aplicar_tema_contili()
init_usuarios_table()

# ── Restrição: somente Administrador ──────────────────────────────────────────
perfil_atual = st.session_state.get('_auth_perfil', '')
user_atual   = st.session_state.get('_auth_user', '')
if perfil_atual != 'Administrador':
    st.error('Acesso restrito a administradores.')
    st.stop()

page_header('Administração', 'Gestão de usuários e utilitários do sistema')

# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 1 — GESTÃO DE USUÁRIOS
# ══════════════════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.markdown(
        '<p style="font-size:13px;font-weight:700;color:#142158;margin-bottom:16px">'
        '👥 Usuários do Sistema</p>',
        unsafe_allow_html=True,
    )

    conn = get_conn()
    usuarios_db = conn.execute(
        'SELECT id, username, nome, perfil, ativo, criado_em FROM usuarios ORDER BY criado_em'
    ).fetchall()
    conn.close()

    if not usuarios_db:
        st.info('Nenhum usuário cadastrado no banco ainda. Use o formulário abaixo para adicionar.')
    else:
        # Cabeçalho da tabela
        h1, h2, h3, h4, h5, h6 = st.columns([2, 3, 2, 1, 1, 1])
        h1.markdown('<span style="font-size:11px;font-weight:700;color:#5A6480;text-transform:uppercase">Login</span>', unsafe_allow_html=True)
        h2.markdown('<span style="font-size:11px;font-weight:700;color:#5A6480;text-transform:uppercase">Nome</span>', unsafe_allow_html=True)
        h3.markdown('<span style="font-size:11px;font-weight:700;color:#5A6480;text-transform:uppercase">Perfil</span>', unsafe_allow_html=True)
        h4.markdown('<span style="font-size:11px;font-weight:700;color:#5A6480;text-transform:uppercase">Status</span>', unsafe_allow_html=True)
        h5.markdown('<span style="font-size:11px;font-weight:700;color:#5A6480;text-transform:uppercase">Acesso</span>', unsafe_allow_html=True)
        h6.markdown('<span style="font-size:11px;font-weight:700;color:#5A6480;text-transform:uppercase">Excluir</span>', unsafe_allow_html=True)
        st.markdown('<hr style="margin:4px 0 8px">', unsafe_allow_html=True)

        for u in usuarios_db:
            c1, c2, c3, c4, c5, c6 = st.columns([2, 3, 2, 1, 1, 1])
            eh_eu = u['username'].lower() == user_atual.lower()

            c1.markdown(f'`{u["username"]}`')
            c2.write(u['nome'])
            c3.markdown(badge(u['perfil'], 'primary' if u['perfil'] == 'Administrador' else 'neutral'), unsafe_allow_html=True)
            c4.markdown(badge('Ativo', 'ok') if u['ativo'] else badge('Inativo', 'danger'), unsafe_allow_html=True)

            with c5:
                if eh_eu:
                    st.markdown('<span style="font-size:11px;color:#5A6480">você</span>', unsafe_allow_html=True)
                elif u['ativo']:
                    if st.button('Desativar', key=f'desativ_{u["id"]}', use_container_width=True):
                        conn = get_conn()
                        conn.execute('UPDATE usuarios SET ativo=0 WHERE id=?', (u['id'],))
                        conn.commit()
                        conn.close()
                        st.rerun()
                else:
                    if st.button('Ativar', key=f'ativ_{u["id"]}', use_container_width=True):
                        conn = get_conn()
                        conn.execute('UPDATE usuarios SET ativo=1 WHERE id=?', (u['id'],))
                        conn.commit()
                        conn.close()
                        st.rerun()

            with c6:
                if eh_eu:
                    st.markdown('')
                else:
                    if st.button('🗑️', key=f'del_{u["id"]}', help=f'Excluir {u["username"]}'):
                        st.session_state[f'_confirm_del_{u["id"]}'] = True
                        st.rerun()

            # Confirmação de exclusão inline
            if st.session_state.get(f'_confirm_del_{u["id"]}'):
                st.warning(f'Confirma exclusão do usuário **{u["username"]} — {u["nome"]}**?')
                col_ok, col_cancel = st.columns(2)
                with col_ok:
                    if st.button('Confirmar exclusão', key=f'ok_del_{u["id"]}', type='primary'):
                        conn = get_conn()
                        conn.execute('DELETE FROM usuarios WHERE id=?', (u['id'],))
                        conn.commit()
                        conn.close()
                        st.session_state.pop(f'_confirm_del_{u["id"]}', None)
                        st.success('Usuário excluído.')
                        st.rerun()
                with col_cancel:
                    if st.button('Cancelar', key=f'cancel_del_{u["id"]}'):
                        st.session_state.pop(f'_confirm_del_{u["id"]}', None)
                        st.rerun()

    st.markdown('<div style="margin-top:20px"></div>', unsafe_allow_html=True)

    # ── Adicionar usuário ──────────────────────────────────────────────────────
    with st.expander('➕ Adicionar Usuário'):
        with st.form('form_add_user', clear_on_submit=True):
            a1, a2 = st.columns(2)
            novo_login  = a1.text_input('Login (username)', placeholder='ex: joao')
            novo_nome   = a2.text_input('Nome completo', placeholder='ex: João Silva')
            a3, a4 = st.columns(2)
            novo_perfil = a3.selectbox('Perfil', ['Usuário', 'Administrador'])
            novo_senha  = a4.text_input('Senha inicial', type='password')
            novo_senha2 = st.text_input('Confirmar senha', type='password')
            salvar = st.form_submit_button('Adicionar usuário', type='primary', use_container_width=True)

        if salvar:
            erros = []
            if not novo_login.strip():
                erros.append('Login obrigatório.')
            if not novo_nome.strip():
                erros.append('Nome obrigatório.')
            if not novo_senha:
                erros.append('Senha obrigatória.')
            if novo_senha != novo_senha2:
                erros.append('As senhas não coincidem.')
            if erros:
                for e in erros:
                    st.error(e)
            else:
                try:
                    conn = get_conn()
                    conn.execute(
                        'INSERT INTO usuarios (username, senha_hash, nome, perfil) VALUES (?,?,?,?)',
                        (novo_login.strip().lower(), hash_senha(novo_senha),
                         novo_nome.strip(), novo_perfil)
                    )
                    conn.commit()
                    conn.close()
                    st.success(f'Usuário **{novo_login.strip().lower()}** adicionado com sucesso.')
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f'Login `{novo_login.strip().lower()}` já existe.')

    # ── Redefinir senha ────────────────────────────────────────────────────────
    with st.expander('🔑 Redefinir Senha'):
        conn = get_conn()
        lista_users = [u['username'] for u in conn.execute(
            'SELECT username FROM usuarios ORDER BY nome'
        ).fetchall()]
        conn.close()

        if not lista_users:
            st.info('Nenhum usuário no banco ainda.')
        else:
            with st.form('form_reset_senha', clear_on_submit=True):
                user_sel   = st.selectbox('Usuário', lista_users)
                nova_senha  = st.text_input('Nova senha', type='password')
                nova_senha2 = st.text_input('Confirmar nova senha', type='password')
                resetar = st.form_submit_button('Redefinir senha', type='primary', use_container_width=True)

            if resetar:
                if not nova_senha:
                    st.error('Senha obrigatória.')
                elif nova_senha != nova_senha2:
                    st.error('As senhas não coincidem.')
                else:
                    conn = get_conn()
                    conn.execute(
                        'UPDATE usuarios SET senha_hash=? WHERE username=?',
                        (hash_senha(nova_senha), user_sel)
                    )
                    conn.commit()
                    conn.close()
                    st.success(f'Senha de **{user_sel}** redefinida com sucesso.')

st.markdown('<div style="margin-top:24px"></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 2 — UPLOAD DO BANCO DE DADOS
# ══════════════════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.markdown(
        '<p style="font-size:13px;font-weight:700;color:#142158;margin-bottom:4px">'
        '⬆️ Restaurar Banco de Dados</p>'
        '<p style="font-size:12px;color:#5A6480;margin-bottom:16px">'
        'Substitui o banco atual pelo arquivo enviado. Use para migrar dados entre ambientes.</p>',
        unsafe_allow_html=True,
    )

    tamanho_atual = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    if tamanho_atual:
        st.info(f'Banco atual: `{DB_PATH}` — {tamanho_atual / 1_048_576:.1f} MB')
    else:
        st.warning(f'Banco não encontrado em `{DB_PATH}` — será criado no upload.')

    arquivo = st.file_uploader('Selecione o arquivo `.db` (SQLite)', type=['db'])

    if arquivo is not None:
        header = arquivo.read(16)
        arquivo.seek(0)
        if not header.startswith(b'SQLite format 3'):
            st.error('O arquivo não parece ser um banco SQLite válido.')
        else:
            st.success(f'Arquivo válido — {arquivo.size / 1_048_576:.1f} MB')
            if st.button('Substituir banco atual', type='primary'):
                try:
                    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
                    if tamanho_atual > 0:
                        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                        shutil.copy2(DB_PATH, DB_PATH.replace('.db', f'_backup_{ts}.db'))
                    with open(DB_PATH, 'wb') as f:
                        f.write(arquivo.read())
                    st.success(f'Banco substituído — {os.path.getsize(DB_PATH) / 1_048_576:.1f} MB gravados.')
                    st.info('Navegue para o Painel Geral para verificar os dados.')
                except Exception as e:
                    st.error(f'Erro ao gravar: {e}')

st.markdown('<div style="margin-top:24px"></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 3 — INFORMAÇÕES DO AMBIENTE
# ══════════════════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.markdown(
        '<p style="font-size:13px;font-weight:700;color:#142158;margin-bottom:12px">'
        '🔍 Informações do Ambiente</p>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f'**DB_PATH:** `{DB_PATH}`')
        existe = os.path.exists(DB_PATH)
        st.markdown(f'**Banco existe:** {"✅ Sim" if existe else "❌ Não"}')
        if existe:
            st.markdown(f'**Tamanho:** {os.path.getsize(DB_PATH) / 1_048_576:.1f} MB')
    with c2:
        st.markdown(f'**Python:** `{sys.version.split()[0]}`')
        st.markdown(f'**SQLite:** `{sqlite3.sqlite_version}`')
        st.markdown(f'**Streamlit:** `{st.__version__}`')
