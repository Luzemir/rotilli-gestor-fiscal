"""
cmed_downloader.py — Download e Import da Tabela CMED (Anvisa)

⚠️  ATENÇÃO — PASSO OBRIGATÓRIO:
    Antes de executar, o usuário DEVE fazer o download manual da tabela CMED.

    1. Acesse: https://www.gov.br/anvisa/pt-br/assuntos/medicamentos/cmed/precos
    2. Clique em "Consulta de Preços" e baixe o arquivo .xls ou .xlsx
    3. Salve o arquivo baixado na pasta: data/cmed/
    4. Execute novamente este script.

    ⛔ Sem o arquivo na pasta data/cmed/, a execução será BLOQUEADA.

Vigência:
    A competência (mês/ano) é extraída do nome do arquivo no padrão:
    xls_conformidade_site_YYYYMMDD_*.xlsx  →  YYYY-MM
    Se não encontrado no nome, tenta extrair da própria planilha.

Uso:
    python scripts/cmed_downloader.py
    python scripts/cmed_downloader.py --pasta Documentos/CMED    (carga histórica)
    python scripts/cmed_downloader.py --todos                     (processa todos os arquivos da pasta)
"""

import os
import re
import sys
import glob
import sqlite3
import datetime
import argparse
import pandas as pd
import requests
from bs4 import BeautifulSoup

# Garante saída UTF-8 no terminal Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DB_PATH = os.path.join("src", "db", "gestor_fiscal.db")
CMED_URL = "https://www.gov.br/anvisa/pt-br/assuntos/medicamentos/cmed/precos"
DATA_DIR = os.path.join("data", "cmed")

BANNER_BLOQUEIO = """
╔══════════════════════════════════════════════════════════════╗
║          ⛔  EXECUÇÃO BLOQUEADA — ARQUIVO CMED AUSENTE       ║
╠══════════════════════════════════════════════════════════════╣
║  Para continuar, você precisa baixar a tabela CMED           ║
║  mensalmente no site da Anvisa:                              ║
║                                                              ║
║  🌐 https://www.gov.br/anvisa/pt-br/assuntos/               ║
║        medicamentos/cmed/precos                              ║
║                                                              ║
║  Após o download, salve o arquivo .xlsx na pasta:            ║
║  📁 {pasta}
║                                                              ║
║  Depois execute novamente: python scripts/cmed_downloader.py ║
╚══════════════════════════════════════════════════════════════╝
"""


def init_cmed_db(conn):
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cmed_historico (
            ean       TEXT,
            produto   TEXT,
            apresentacao TEXT,
            pmc_17    REAL,
            tipo_lista TEXT,
            mes_ano   TEXT,
            PRIMARY KEY (ean, mes_ano)
        )
    ''')
    conn.commit()


def extrair_mes_ano_do_nome(filepath):
    """
    Extrai a competência do nome do arquivo.
    Padrão esperado: xls_conformidade_site_YYYYMMDD_*.xlsx
    Ex: xls_conformidade_site_20260108_162952452.xlsx → 2026-01
    """
    nome = os.path.basename(filepath)
    match = re.search(r'(\d{4})(\d{2})\d{2}_', nome)
    if match:
        ano, mes = match.group(1), match.group(2)
        return f"{ano}-{mes}"
    return None


def extrair_mes_ano_da_planilha(df):
    """
    Tenta encontrar a data de vigência dentro das primeiras linhas da planilha.
    Procura por algo como 'Vigência' ou datas no cabeçalho.
    """
    for idx, row in df.head(20).iterrows():
        for val in row.values:
            if pd.isna(val):
                continue
            texto = str(val).upper()
            # Procura padrões de data como "01/01/2026" ou "JANEIRO/2026"
            match_num = re.search(r'(\d{2})/(\d{2})/(\d{4})', texto)
            if match_num:
                mes, ano = match_num.group(2), match_num.group(3)
                return f"{ano}-{mes}"
            match_ext = re.search(
                r'(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)[A-Z]*/(\d{4})',
                texto
            )
            if match_ext:
                meses_map = {
                    'JAN': '01', 'FEV': '02', 'MAR': '03', 'ABR': '04',
                    'MAI': '05', 'JUN': '06', 'JUL': '07', 'AGO': '08',
                    'SET': '09', 'OUT': '10', 'NOV': '11', 'DEZ': '12'
                }
                mes = meses_map.get(match_ext.group(1), '01')
                ano = match_ext.group(2)
                return f"{ano}-{mes}"
    return None


def tentar_download_automatico():
    """
    Tenta baixar o arquivo CMED diretamente do site da Anvisa.
    Pode falhar se o site usar JavaScript para renderizar o link.
    """
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    print("Tentando download automático do portal da CMED/Anvisa...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    response = requests.get(CMED_URL, headers=headers, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    download_url = None
    for a in soup.find_all('a', href=True):
        if a['href'].lower().endswith('.xls') or a['href'].lower().endswith('.xlsx'):
            download_url = a['href']
            break

    if not download_url:
        raise Exception("Link do arquivo não encontrado — o site provavelmente usa JavaScript dinâmico.")

    print(f"Link encontrado: {download_url}")
    filename = download_url.split('/')[-1]
    filepath = os.path.join(DATA_DIR, filename)

    print(f"Baixando para {filepath}...")
    xls_response = requests.get(download_url, headers=headers, timeout=120)
    with open(filepath, 'wb') as f:
        f.write(xls_response.content)

    print("Download automático concluído!")
    return filepath


def processar_arquivo_cmed(filepath, conn):
    """
    Lê um arquivo CMED, determina a competência e insere no banco de dados.
    """
    print(f"\nProcessando: {os.path.basename(filepath)}")

    # 1. Tenta extrair a competência do nome do arquivo
    mes_ano = extrair_mes_ano_do_nome(filepath)

    # 2. Se não encontrou no nome, lê a planilha e tenta extrair do conteúdo
    df_raw = pd.read_excel(filepath, header=None, nrows=25)
    if not mes_ano:
        mes_ano = extrair_mes_ano_da_planilha(df_raw)

    # 3. Fallback: usa o mês do arquivo (data de modificação)
    if not mes_ano:
        ts = os.path.getmtime(filepath)
        dt = datetime.datetime.fromtimestamp(ts)
        mes_ano = dt.strftime("%Y-%m")
        print(f"  [AVISO] Não foi possível identificar a vigência no nome/conteúdo. Usando data do arquivo: {mes_ano}")
    else:
        print(f"  ✅ Vigência identificada: {mes_ano}")

    # Verifica se essa competência já foi processada
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM cmed_historico WHERE mes_ano = ?", (mes_ano,))
    count = cursor.fetchone()[0]
    if count > 0:
        print(f"  ⚠️  Competência {mes_ano} já possui {count} registros no BD. Sobrescrevendo...")
        cursor.execute("DELETE FROM cmed_historico WHERE mes_ano = ?", (mes_ano,))
        conn.commit()

    # Lê o arquivo completo — procura o header real (linha com EAN, PRODUTO, PMC)
    df = pd.read_excel(filepath, header=None)
    header_idx = None
    for idx, row in df.head(60).iterrows():
        row_str = ' '.join(str(v).upper() for v in row.values if pd.notna(v))
        if 'EAN' in row_str and 'PRODUTO' in row_str and 'PMC' in row_str:
            header_idx = idx
            break

    if header_idx is not None:
        df = pd.read_excel(filepath, header=header_idx)
    else:
        # Usa a primeira linha como header
        df = pd.read_excel(filepath)

    # Padroniza nomes das colunas
    df.columns = [str(c).upper().strip().replace('\n', ' ') for c in df.columns]

    # Mapeia as colunas pelo nome (tolerante a variações)
    col_ean = next((c for c in df.columns if c.startswith('EAN')), None)
    col_produto = next((c for c in df.columns if c.startswith('PRODUTO')), None)
    col_apresentacao = next((c for c in df.columns if 'APRESENTA' in c), None)
    # PMC 17% pode vir como "PMC 17%", "PMC 17 %", "PMC17%"
    col_pmc = next((c for c in df.columns if 'PMC' in c and '17' in c), None)
    col_lista = next((c for c in df.columns if 'LISTA' in c), None)

    if not all([col_ean, col_produto, col_pmc]):
        print(f"  [ERRO] Colunas obrigatórias não encontradas. Colunas disponíveis:\n  {list(df.columns)}")
        return 0

    print(f"  Colunas mapeadas → EAN: '{col_ean}' | Produto: '{col_produto}' | PMC: '{col_pmc}' | Lista: '{col_lista}'")
    print(f"  Total de linhas no arquivo: {len(df)}")

    df_clean = df[[col_ean, col_produto, col_apresentacao, col_pmc, col_lista]].copy()
    df_clean = df_clean.dropna(subset=[col_ean])
    df_clean = df_clean[df_clean[col_ean].astype(str).str.match(r'^\d+')]  # Mantém apenas EANs numéricos

    inseridos = 0
    for _, row in df_clean.iterrows():
        ean = str(row[col_ean]).strip().split('.')[0]  # Remove casas decimais do EAN
        produto = str(row[col_produto]).strip() if pd.notna(row[col_produto]) else None
        apresentacao = str(row[col_apresentacao]).strip() if pd.notna(row[col_apresentacao]) else None
        pmc_17 = pd.to_numeric(str(row[col_pmc]).replace(',', '.'), errors='coerce')
        pmc_17 = float(pmc_17) if pd.notna(pmc_17) else None
        tipo_lista = str(row[col_lista]).strip() if pd.notna(row[col_lista]) else None

        cursor.execute('''
            INSERT OR REPLACE INTO cmed_historico (ean, produto, apresentacao, pmc_17, tipo_lista, mes_ano)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (ean, produto, apresentacao, pmc_17, tipo_lista, mes_ano))
        inseridos += 1

        if inseridos % 5000 == 0:
            print(f"  {inseridos} registros inseridos...")
            conn.commit()

    conn.commit()
    print(f"  ✅ {inseridos} medicamentos cadastrados para a competência {mes_ano}.")
    return inseridos


def main():
    parser = argparse.ArgumentParser(description='CMED Downloader — Gestor Fiscal Rotilli')
    parser.add_argument('--pasta', default=DATA_DIR, help='Pasta onde estão os arquivos CMED')
    parser.add_argument('--todos', action='store_true', help='Processa TODOS os arquivos xlsx da pasta')
    args = parser.parse_args()

    pasta = args.pasta
    if not os.path.exists(pasta):
        os.makedirs(pasta)

    # Busca arquivos na pasta indicada
    arquivos = sorted(glob.glob(os.path.join(pasta, "*.xls*")))

    if not arquivos:
        # Tenta download automático antes de bloquear
        print("Nenhum arquivo CMED local encontrado. Tentando download automático...")
        try:
            filepath = tentar_download_automatico()
            arquivos = [filepath]
        except Exception as e:
            # BLOQUEIO TOTAL
            caminho_abs = os.path.abspath(pasta)
            print(BANNER_BLOQUEIO.format(pasta=caminho_abs.ljust(52)))
            return

    if not args.todos:
        # Por padrão, processa apenas o arquivo mais recente
        arquivos = [max(arquivos, key=os.path.getmtime)]
        print(f"Processando arquivo mais recente. Use --todos para processar todos.\n")

    print(f"Arquivos a processar: {len(arquivos)}")

    conn = sqlite3.connect(DB_PATH)
    init_cmed_db(conn)

    total_inseridos = 0
    for filepath in arquivos:
        total_inseridos += processar_arquivo_cmed(filepath, conn)

    conn.close()

    print(f"\n{'='*60}")
    print(f" ✅ CARGA CMED CONCLUÍDA")
    print(f"    Total de registros inseridos/atualizados: {total_inseridos}")
    print(f"    Banco de dados: {os.path.abspath(DB_PATH)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
