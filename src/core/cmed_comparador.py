"""
cmed_comparador.py — Comparação de PMC com a tabela CMED (Anvisa)

Para produtos com mod_bc_icms_st = 0, consulta o PMC 17% atualizado na
tabela cmed_historico e sinaliza divergências em relação ao valor histórico.

Possíveis status após comparação:
  PMC_OK          — CMED encontrada, PMC coincide com o histórico (< R$0,01 de diff)
  PMC_DIVERGENTE  — CMED encontrada, PMC diverge do histórico
  PMC_SEM_CMED    — EAN não encontrado na tabela CMED para nenhuma competência
  PMC_SEM_EAN     — Produto não tem EAN válido na NF-e, consulta impossível

item['pmc'] NUNCA é sobrescrito por este módulo — sempre mantém o PMC histórico
(o que vai para a coluna Y da planilha). O valor da CMED fica em item['pmc_cmed']
(coluna AN da planilha), e a divergência em item['pmc_divergencia'].
"""

import sys
import os

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PMC_OK = 'PMC_OK'
PMC_DIVERGENTE = 'PMC_DIVERGENTE'
PMC_SEM_CMED = 'PMC_SEM_CMED'
PMC_SEM_EAN = 'PMC_SEM_EAN'

_EAN_INVALIDOS = {'SEM GTIN', 'SEMGTIN', '0', 'NONE', '', 'N/A'}


def sanitizar_ean_gtin14(ean_str: str) -> str:
    """
    Converte GTIN-14 de caixa fechada para o EAN-13 da unidade de venda.

    Regra: exatamente 14 dígitos numéricos iniciando com '1'.
      - Remove o prefixo '1' e o dígito verificador GTIN-14 (último dígito).
      - Recalcula o dígito verificador EAN-13 para os 12 dígitos do meio.
    Qualquer outro formato é devolvido sem alteração.
    """
    if len(ean_str) != 14 or ean_str[0] != '1' or not ean_str.isdigit():
        return ean_str
    doze = ean_str[1:13]
    soma = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(doze))
    dv = (10 - (soma % 10)) % 10
    return doze + str(dv)


def _normalizar_ean(ean):
    """Remove pontos/vírgulas e espaços; converte GTIN-14; retorna None se inválido."""
    if ean is None:
        return None
    ean_str = str(ean).strip().split('.')[0]
    if ean_str.upper() in _EAN_INVALIDOS:
        return None
    return sanitizar_ean_gtin14(ean_str)


def consultar_pmc_cmed(ean, mes_ano, conn):
    """
    Busca o PMC 17% para o EAN na competência indicada.
    Se não houver registro exato, usa o mais recente anterior (fallback mensal).
    Retorna (pmc_17: float, tipo_lista: str) ou (None, None).
    """
    ean_norm = _normalizar_ean(ean)
    if not ean_norm:
        return None, None

    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT pmc_17, tipo_lista
        FROM cmed_historico
        WHERE ean = ? AND mes_ano <= ?
        ORDER BY mes_ano DESC
        LIMIT 1
        ''',
        (ean_norm, mes_ano),
    )
    row = cursor.fetchone()
    if row:
        return row[0], row[1]
    return None, None


def comparar_pmc(item, mes_ano, conn):
    """
    Compara o PMC do item (vindo do BD histórico, item['pmc']) com o PMC da
    CMED para mes_ano. Modifica o item em-place e retorna o item atualizado.

    Campos adicionados (item['pmc'] nunca é alterado por esta função):
      pmc_cmed        — PMC 17% encontrado na CMED (None se não encontrado)
      tipo_lista_cmed — tipo da lista CMED (Positiva/Negativa/Neutra)
      pmc_divergencia — diferença em R$ (pmc_cmed - pmc histórico); None se não consultado
      status          — PMC_OK | PMC_DIVERGENTE | PMC_SEM_CMED | PMC_SEM_EAN
    """
    ean = item.get('ean')

    if not _normalizar_ean(ean):
        item.update({'pmc_cmed': None, 'tipo_lista_cmed': None, 'pmc_divergencia': None, 'status': PMC_SEM_EAN})
        return item

    pmc_cmed, tipo_lista = consultar_pmc_cmed(ean, mes_ano, conn)

    if pmc_cmed is None:
        item.update({'pmc_cmed': None, 'tipo_lista_cmed': None, 'pmc_divergencia': None, 'status': PMC_SEM_CMED})
        return item

    item['pmc_cmed'] = pmc_cmed
    item['tipo_lista_cmed'] = tipo_lista

    pmc_bd = float(item.get('pmc') or 0.0)
    divergencia = round(pmc_cmed - pmc_bd, 2)
    item['pmc_divergencia'] = divergencia
    item['status'] = PMC_OK if abs(divergencia) < 0.01 else PMC_DIVERGENTE

    return item
