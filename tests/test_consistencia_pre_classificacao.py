"""
Teste de consistência das 3 cópias deliberadas da pré-classificação ICMS-ST.

A mesma árvore de decisão (MOD 0-5, MVA por alíquota) existe em:
  - src/core/nfe_parser.py                  → _pre_classificar(item, competencia, conn)
  - src/streamlit/pages/1_Importar_NF_e.py  → _aplicar_pre_classificacao(item, competencia, conn)
  - src/streamlit/pages/2_Alertas.py        → _reclassificar_alerta(ean, ncm, cest, bc, vlr, competencia, conn)

As cópias são intencionais (cache __pycache__ stale no Streamlit — ver AGENTS.md),
mas DEVEM produzir o mesmo resultado. Este teste roda os mesmos cenários nas três
e falha se qualquer uma divergir em pre_mod_bc / pre_pmc / pre_mva.

A consulta à CMED é substituída por um fake controlado por cenário; a tabela
ncm_st vive num SQLite em memória.

Execução:
    python -m pytest tests/test_consistencia_pre_classificacao.py -v
"""
import sys
import os
import re
import sqlite3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'core'))
sys.path.insert(0, os.path.dirname(__file__))

import nfe_parser
from util_extracao import extrair_funcao

# ── Fake CMED compartilhado — cada cenário define o retorno ───────────────────
_CMED = {'resultado': (None, None)}


def _fake_consultar_pmc_cmed(ean, competencia, conn):
    return _CMED['resultado']


# ── As três implementações, com o mesmo fake injetado ─────────────────────────
_ns_importar = {'re': re, 'consultar_pmc_cmed': _fake_consultar_pmc_cmed}
_ns_alertas  = {'re': re, 'consultar_pmc_cmed': _fake_consultar_pmc_cmed}

fn_importar = extrair_funcao(
    'src/streamlit/pages/1_Importar_NF_e.py', '_aplicar_pre_classificacao', _ns_importar)
fn_alertas = extrair_funcao(
    'src/streamlit/pages/2_Alertas.py', '_reclassificar_alerta', _ns_alertas)


@pytest.fixture()
def conn():
    c = sqlite3.connect(':memory:')
    c.execute('''
        CREATE TABLE ncm_st (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seguimento INTEGER, item TEXT, cest TEXT, cest_norm TEXT,
            ncm TEXT, ncm_norm TEXT, mva_interno REAL, mva_aliq4 REAL,
            mva_aliq7 REAL, mva_aliq12 REAL, descricao TEXT, dispositivo_legal TEXT
        )
    ''')
    # Registro com CEST (match exato → MVA preenchível)
    c.execute(
        "INSERT INTO ncm_st (seguimento, cest, cest_norm, ncm, ncm_norm,"
        " mva_interno, mva_aliq4, mva_aliq7, mva_aliq12, descricao)"
        " VALUES (13, '13.001.00', '1300100', '3004', '3004',"
        " 35.12, 41.83, 38.57, 32.22, 'Medicamentos de referência')"
    )
    # Registro só-NCM (raiz 8708, CEST diferente do usado nos cenários)
    c.execute(
        "INSERT INTO ncm_st (seguimento, cest, cest_norm, ncm, ncm_norm,"
        " mva_interno, mva_aliq4, mva_aliq7, mva_aliq12, descricao)"
        " VALUES (1, '01.999.00', '0199900', '8708', '8708',"
        " 71.78, 96.53, 90.16, 79.45, 'Autopeças')"
    )
    yield c
    c.close()


def _rodar_as_tres(conn, ncm, cest, ean, bc, vlr, cmed):
    """Executa o mesmo cenário nas 3 implementações e devolve os 3 resultados
    normalizados como (pre_mod_bc, pre_pmc, pre_mva, tem_nota)."""
    _CMED['resultado'] = cmed
    competencia = '2026-05'

    # 1. nfe_parser (importável — fake via monkeypatch de atributo do módulo)
    original = nfe_parser.consultar_pmc_cmed
    nfe_parser.consultar_pmc_cmed = _fake_consultar_pmc_cmed
    try:
        item1 = {'ncm': ncm, 'cest': cest, 'ean': ean,
                 'bc_icms_origem': bc, 'vlr_icms_origem': vlr}
        nfe_parser._pre_classificar(item1, competencia, conn)
    finally:
        nfe_parser.consultar_pmc_cmed = original

    # 2. Página Importar NF-e
    item2 = {'ncm': ncm, 'cest': cest, 'ean': ean,
             'bc_icms_origem': bc, 'vlr_icms_origem': vlr}
    fn_importar(item2, competencia, conn)

    # 3. Página Alertas (assinatura posicional, retorna dict)
    res3 = fn_alertas(ean, ncm, cest, bc, vlr, competencia, conn)

    def _norm(d):
        return (d.get('pre_mod_bc'), d.get('pre_pmc'), d.get('pre_mva'),
                bool(d.get('pre_nota')))

    return _norm(item1), _norm(item2), _norm(res3)


# Cenários: (id, ncm, cest, bc, vlr, retorno_cmed, esperado (mod, pmc, mva, tem_nota))
CENARIOS = [
    ('mod0_pmc_positivo',
     '30049099', '13.001.00', 100.0, 17.0, (150.0, 'Positiva'),
     ('0', 150.0, None, False)),

    ('mod1_lista_positiva_pmc_zero',
     '30049099', '13.001.00', 100.0, 17.0, (0, 'Positiva'),
     ('1', None, None, False)),

    ('mod2_lista_negativa',
     '30049099', '13.001.00', 100.0, 17.0, (None, 'Negativa'),
     ('2', None, None, False)),

    ('mod3_lista_neutra',
     '30049099', '13.001.00', 100.0, 17.0, (0, 'Neutra'),
     ('3', None, None, False)),

    ('lista_desconhecida_nao_classifica',
     '30049099', '13.001.00', 100.0, 17.0, (0, 'Inexistente'),
     (None, None, None, True)),

    # MOD 4 — MVA escolhido pela alíquota efetiva de origem (vlr/bc)
    ('mod4_aliq_interna_17',
     '30049099', '13.001.00', 100.0, 17.0, (None, None),
     ('4', None, round(35.12 / 100, 4), False)),

    ('mod4_aliq_12',
     '30049099', '13.001.00', 100.0, 12.0, (None, None),
     ('4', None, round(32.22 / 100, 4), False)),

    ('mod4_aliq_7',
     '30049099', '13.001.00', 100.0, 7.0, (None, None),
     ('4', None, round(38.57 / 100, 4), False)),

    ('mod4_aliq_4',
     '30049099', '13.001.00', 100.0, 4.0, (None, None),
     ('4', None, round(41.83 / 100, 4), False)),

    ('mod4_sem_bc_mva_vazio',
     '30049099', '13.001.00', 0.0, 0.0, (None, None),
     ('4', None, None, False)),

    ('mod4_match_so_por_ncm_sem_mva',
     '87081000', '', 100.0, 12.0, (None, None),
     ('4', None, None, False)),   # MVA só via CEST exato

    ('mod5_normal',
     '99999999', '', 100.0, 17.0, (None, None),
     ('5', None, None, False)),

    ('mod5_anomalia_cmed_sem_st',
     '99999999', '', 100.0, 17.0, (100.0, 'Positiva'),
     ('5', None, None, True)),
]


class TestConsistencia:

    @pytest.mark.parametrize(
        'ncm,cest,bc,vlr,cmed,esperado',
        [c[1:] for c in CENARIOS],
        ids=[c[0] for c in CENARIOS],
    )
    def test_cenario(self, conn, ncm, cest, bc, vlr, cmed, esperado):
        r_parser, r_importar, r_alertas = _rodar_as_tres(
            conn, ncm, cest, '7891000315507', bc, vlr, cmed)

        assert r_parser == r_importar == r_alertas, (
            f'DIVERGÊNCIA entre as cópias da pré-classificação — '
            f'nfe_parser={r_parser} importar={r_importar} alertas={r_alertas}. '
            f'As 3 devem ser alteradas juntas (ver AGENTS.md → Armadilhas).'
        )
        assert r_parser == esperado, (
            f'Comportamento mudou: esperado {esperado}, obtido {r_parser}'
        )
