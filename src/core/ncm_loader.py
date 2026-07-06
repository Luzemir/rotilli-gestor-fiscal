"""ncm_loader.py — Tabela TIPI × ICMS-ST (TIPIvsICMSST_Processado.xlsx)

Indexa todos os NCMs com Situação Tributária = 'ST' e expõe
verificar_ncm_st(ncm, cest=None) para pré-classificação automática
de produtos novos detectados nas NF-es.

Matching:
  1. NCM + CEST exato (prioridade — dá o MVA correto para o segmento)
  2. NCM sozinho — fallback quando a NF-e não traz CEST (retorna ST=True
     se qualquer linha do NCM for ST; MVA da primeira linha ST encontrada)

Arquivo esperado: data/TIPIvsICMSST_Processado.xlsx
  - skiprows=2, header=0 (os 2 primeiros blocos são título/subtítulo)
  - Colunas relevantes (após strip()): NCM | CEST | Situação Tributária |
    Margem - Oper. interna
"""
import os
import re
import pandas as pd

_ARQUIVO = os.path.join('data', 'TIPIvsICMSST_Processado.xlsx')
_COL_NCM  = 'NCM'
_COL_CEST = 'CEST'
_COL_SIT  = 'Situação Tributária'
_COL_MVA  = 'Margem - Oper. interna'

_cache: dict = {}


def _norm_ncm(v) -> str:
    return re.sub(r'[.\s]', '', str(v))


def _norm_cest(v) -> str:
    return re.sub(r'[.\s]', '', str(v))


def _carregar(arquivo: str):
    if arquivo in _cache:
        return _cache[arquivo]

    df = pd.read_excel(arquivo, sheet_name=0, skiprows=2, header=0)
    df.columns = df.columns.str.strip()

    df = df[df[_COL_NCM].notna()].copy()
    df['_ncm']   = df[_COL_NCM].apply(_norm_ncm)
    df['_cest']  = df[_COL_CEST].apply(lambda v: _norm_cest(v) if pd.notna(v) else '')
    df['_is_st'] = df[_COL_SIT].astype(str).str.strip().str.upper() == 'ST'
    df['_mva']   = pd.to_numeric(df[_COL_MVA], errors='coerce').fillna(0.0)

    # Índice (ncm, cest) → (is_st, mva) — primeira ocorrência vence
    idx_ncm_cest: dict = {}
    # Índice ncm → (is_st, mva) — prefere a primeira linha ST encontrada
    idx_ncm: dict = {}

    for _, row in df.iterrows():
        ncm   = row['_ncm']
        cest  = row['_cest']
        is_st = bool(row['_is_st'])
        mva   = float(row['_mva'])

        if not ncm or not ncm.isdigit():
            continue

        if cest:
            idx_ncm_cest.setdefault((ncm, cest), (is_st, mva))

        if ncm not in idx_ncm:
            idx_ncm[ncm] = (is_st, mva)
        elif is_st and not idx_ncm[ncm][0]:
            idx_ncm[ncm] = (True, mva)

    _cache[arquivo] = (idx_ncm_cest, idx_ncm)
    return idx_ncm_cest, idx_ncm


def verificar_ncm_st(ncm, cest=None, arquivo: str | None = None) -> tuple[bool, float]:
    """
    Verifica se o NCM está sujeito ao ICMS-ST segundo a tabela TIPIvsICMSST.

    Parâmetros:
      ncm    — código NCM da NF-e (ex: '30049099' ou '3004.90.99')
      cest   — código CEST da NF-e (ex: '1300101' ou '13.001.01'), opcional
      arquivo — caminho para o xlsx; usa o padrão se None

    Retorna:
      (is_st: bool, mva: float)
      mva = Margem Oper. Interna (%). 0.0 quando não encontrado.
    """
    if not ncm:
        return False, 0.0

    arq = arquivo or _ARQUIVO
    if not os.path.exists(arq):
        return False, 0.0

    ncm_n = _norm_ncm(ncm)
    if not ncm_n.isdigit():
        return False, 0.0

    try:
        idx_ncm_cest, idx_ncm = _carregar(arq)
    except Exception:
        return False, 0.0

    # 1. NCM + CEST exato
    if cest:
        cest_n = _norm_cest(cest)
        resultado = idx_ncm_cest.get((ncm_n, cest_n))
        if resultado is not None:
            return resultado

    # 2. NCM sozinho (fallback)
    resultado = idx_ncm.get(ncm_n)
    if resultado is not None:
        return resultado

    return False, 0.0
