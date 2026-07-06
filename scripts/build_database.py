"""
build_database.py — Reimportação histórica de produtos/produto_competencia

Varre Documentos/YYYY-MM/*.xls*, reconhece as planilhas RegimeEspecial
(ignorando os arquivos "Rotili - EnvioFiscal-..." que têm a mesma aba e
poluiriam os dados), e grava produto_competencia somente quando a
classificação realmente mudou em relação à última competência conhecida
(ver src/core/competencia_importer.py).

Processa TODAS as planilhas Original em ordem cronológica primeiro, depois
TODAS as Ajustada em ordem cronológica — cada trilha mantém seu próprio
"último estado conhecido" por produto.

Uso:
  python scripts/build_database.py              # dry-run, só mostra o que faria
  python scripts/build_database.py --confirmar   # faz backup, limpa e reimporta
"""

import os
import sys
import glob
import sqlite3
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'core'))
from competencia_importer import classificar_arquivo_historico, importar_competencia

from backup_and_reset_competencias import backup_db, resetar_tabelas_competencia

DB_PATH = os.path.join('src', 'db', 'gestor_fiscal.db')
BASE_DIR = 'Documentos'


def init_db(conn):
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            cnpj_remetente TEXT,
            cod_produto_origem TEXT,
            descricao_produto TEXT,
            unidade TEXT,
            PRIMARY KEY (cnpj_remetente, cod_produto_origem)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS produto_competencia (
            cnpj_remetente TEXT,
            cod_produto_origem TEXT,
            mes_ano TEXT,
            mod_bc_icms_st TEXT,
            pmc REAL,
            mva REAL,
            tipo_planilha TEXT,
            PRIMARY KEY (cnpj_remetente, cod_produto_origem, mes_ano, tipo_planilha),
            FOREIGN KEY (cnpj_remetente, cod_produto_origem) REFERENCES produtos(cnpj_remetente, cod_produto_origem)
        )
    ''')
    conn.commit()


def descobrir_arquivos(base_dir=BASE_DIR):
    """
    Varre base_dir/YYYY-MM/*.xls*, classifica cada arquivo via
    classificar_arquivo_historico(). Ignora (loga) arquivos não reconhecidos
    ou explicitamente excluídos (ex: "Rotili - EnvioFiscal-...").
    """
    encontrados = []
    ignorados = []

    for nome_pasta in sorted(os.listdir(base_dir)):
        pasta = os.path.join(base_dir, nome_pasta)
        if not os.path.isdir(pasta) or not nome_pasta.startswith('202'):
            continue

        for caminho in sorted(glob.glob(os.path.join(pasta, '*.xls*'))):
            nome_arquivo = os.path.basename(caminho)
            info = classificar_arquivo_historico(nome_arquivo)

            if info is None:
                ignorados.append(caminho)
                continue

            if info['mes_ano'] != nome_pasta:
                print(f'  [AVISO] {nome_arquivo}: competência no nome ({info["mes_ano"]}) '
                      f'difere da pasta ({nome_pasta}). Usando a pasta como referência.')
                info['mes_ano'] = nome_pasta

            encontrados.append({'caminho': caminho, **info})

    print(f'\nArquivos reconhecidos: {len(encontrados)}')
    print(f'Arquivos ignorados: {len(ignorados)}')
    for c in ignorados:
        print(f'  - IGNORADO: {c}')

    return encontrados


def _imprimir_relatorio(item, relatorio):
    print(
        f"  {item['mes_ano']} [{item['tipo_planilha']:8s}] "
        f"{os.path.basename(item['caminho']):55s} | "
        f"novos={relatorio['produtos_novos']:4d}  "
        f"gravadas={relatorio['linhas_gravadas']:4d}  "
        f"inalteradas={relatorio['linhas_inalteradas']:4d}  "
        f"total={relatorio['total_linhas']:4d}"
    )
    if relatorio['aviso_recalculo']:
        print(f"    [AVISO] {relatorio['aviso_recalculo']}")


def main(confirmar=False):
    arquivos = descobrir_arquivos()

    originais = sorted(
        [a for a in arquivos if a['tipo_planilha'] == 'Original'], key=lambda a: a['mes_ano']
    )
    ajustadas = sorted(
        [a for a in arquivos if a['tipo_planilha'] == 'Ajustada'], key=lambda a: a['mes_ano']
    )

    print(f'\nPlanilhas Original a processar: {len(originais)}')
    print(f'Planilhas Ajustada a processar: {len(ajustadas)}')

    if not confirmar:
        print('\n[DRY-RUN] Nenhuma alteração foi feita no banco. '
              'Rode com --confirmar para fazer backup, limpar e reimportar.')
        return

    caminho_backup = backup_db()
    print(f'\nBackup criado em: {caminho_backup}')

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    resetar_tabelas_competencia(conn)
    print('Tabelas produtos e produto_competencia foram limpas.\n')

    total_gravadas = total_inalteradas = total_novos = 0

    print('== Processando trilha ORIGINAL (ordem cronológica) ==')
    for item in originais:
        relatorio = importar_competencia(conn, item['caminho'], item['mes_ano'], 'Original')
        _imprimir_relatorio(item, relatorio)
        total_gravadas += relatorio['linhas_gravadas']
        total_inalteradas += relatorio['linhas_inalteradas']
        total_novos += relatorio['produtos_novos']

    print('\n== Processando trilha AJUSTADA (ordem cronológica) ==')
    for item in ajustadas:
        relatorio = importar_competencia(conn, item['caminho'], item['mes_ano'], 'Ajustada')
        _imprimir_relatorio(item, relatorio)
        total_gravadas += relatorio['linhas_gravadas']
        total_inalteradas += relatorio['linhas_inalteradas']
        total_novos += relatorio['produtos_novos']

    cursor = conn.cursor()
    total_produtos = cursor.execute('SELECT COUNT(*) FROM produtos').fetchone()[0]
    total_competencia = cursor.execute('SELECT COUNT(*) FROM produto_competencia').fetchone()[0]
    conn.close()

    print(f'\n{"="*70}')
    print(f' CARGA HISTÓRICA CONCLUÍDA')
    print(f'{"="*70}')
    print(f'   Produtos cadastrados:         {total_produtos}')
    print(f'   Linhas em produto_competencia: {total_competencia}')
    print(f'   (gravadas: {total_gravadas} | dedup/inalteradas: {total_inalteradas})')
    print(f'   Backup pré-reimportação: {caminho_backup}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Reimportação histórica do Gestor Fiscal')
    parser.add_argument('--confirmar', action='store_true',
                         help='Confirma o backup + limpeza + reimportação completa.')
    args = parser.parse_args()
    main(confirmar=args.confirmar)
