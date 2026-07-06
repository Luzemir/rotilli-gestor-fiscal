"""
backup_and_reset_competencias.py — Backup do banco e limpeza de produtos/produto_competencia

Usado pelo script de reimportação histórica (build_database.py) antes de
reconstruir produtos/produto_competencia do zero. NÃO toca em cmed_historico
nem produto_alerta.
"""

import os
import shutil
import sqlite3
import datetime

DB_PATH = os.path.join('src', 'db', 'gestor_fiscal.db')
BACKUP_DIR = os.path.join('src', 'db', 'backups')


def backup_db(db_path=DB_PATH):
    """Copia o .db inteiro para src/db/backups/gestor_fiscal_YYYYMMDD_HHMMSS.db."""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    destino = os.path.join(BACKUP_DIR, f'gestor_fiscal_{timestamp}.db')
    shutil.copy2(db_path, destino)
    return destino


def resetar_tabelas_competencia(conn):
    """Apaga produto_competencia e produtos (nessa ordem, por causa da FK)."""
    cursor = conn.cursor()
    cursor.execute('DELETE FROM produto_competencia')
    cursor.execute('DELETE FROM produtos')
    conn.commit()


if __name__ == '__main__':
    caminho = backup_db()
    print(f'Backup criado em: {caminho}')
    conn = sqlite3.connect(DB_PATH)
    resetar_tabelas_competencia(conn)
    conn.close()
    print('Tabelas produtos e produto_competencia foram limpas.')
