"""
Testes de _normalizar_mva — comportamento e consistência entre as 3 cópias.

A função existe deliberadamente em 3 lugares (ver AGENTS.md → Armadilhas):
  - src/core/planilha_credito_outorgado.py  (coluna Z da planilha)
  - src/streamlit/pages/2_Alertas.py         (gravação no banco, classificação)
  - src/streamlit/pages/3_Produtos.py        (edição de histórico)

Se alguém alterar uma cópia e esquecer as outras, o teste de consistência quebra.

Execução:
    python -m pytest tests/test_normalizar_mva.py -v
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'core'))
sys.path.insert(0, os.path.dirname(__file__))

from planilha_credito_outorgado import _normalizar_mva as mva_core
from util_extracao import extrair_funcao

mva_alertas  = extrair_funcao('src/streamlit/pages/2_Alertas.py',  '_normalizar_mva', {})
mva_produtos = extrair_funcao('src/streamlit/pages/3_Produtos.py', '_normalizar_mva', {})

TODAS_AS_COPIAS = [
    pytest.param(mva_core,     id='core-planilha'),
    pytest.param(mva_alertas,  id='pagina-alertas'),
    pytest.param(mva_produtos, id='pagina-produtos'),
]

# (entrada, saída esperada) — a regra: >5 é percentual cheio digitado errado → /100;
# senão mantém; sempre arredonda a 4 casas; None passa direto.
CASOS = [
    (None,     None),      # ausente
    (0,        0.0),       # zero
    (0.3824,   0.3824),    # fracionário legítimo (38,24%)
    (0.6,      0.6),       # fracionário legítimo (60%)
    (4.9999,   4.9999),    # fracionário alto mas válido (<5)
    (5.0,      5.0),       # limite exato — NÃO divide (fórmula AD aceita Z<=5)
    (5.01,     0.0501),    # acima do limite → era percentual (5,01%)
    (38.24,    0.3824),    # percentual cheio típico (caso real do bug)
    (60,       0.6),       # percentual cheio inteiro
    (60.0,     0.6),
    (100,      1.0),       # 100% digitado cheio
    (0.123456, 0.1235),    # arredondamento a 4 casas
    ('38.24',  0.3824),    # string numérica (vinda de widget/CSV)
]


class TestComportamento:

    @pytest.mark.parametrize('fn', TODAS_AS_COPIAS)
    @pytest.mark.parametrize('entrada,esperado', CASOS)
    def test_caso(self, fn, entrada, esperado):
        assert fn(entrada) == esperado

    @pytest.mark.parametrize('fn', TODAS_AS_COPIAS)
    def test_resultado_nunca_excede_5(self, fn):
        # Propriedade central: para qualquer entrada numérica de 0 a 500,
        # o resultado deve caber no limite Z<=5 da fórmula da coluna AD.
        for i in range(0, 5001):
            v = i / 10
            r = fn(v)
            assert r is not None and r <= 5, f'entrada {v} produziu {r} > 5'


class TestConsistenciaEntreCopias:

    def test_copias_identicas_em_varredura(self):
        # Varre uma faixa densa de valores e exige saída idêntica nas 3 cópias.
        valores = [None] + [i / 100 for i in range(0, 12001, 7)]
        for v in valores:
            r_core, r_al, r_pr = mva_core(v), mva_alertas(v), mva_produtos(v)
            assert r_core == r_al == r_pr, (
                f'Divergência para entrada {v!r}: '
                f'core={r_core} alertas={r_al} produtos={r_pr} — '
                f'as 3 cópias de _normalizar_mva devem ser alteradas juntas (ver AGENTS.md)'
            )
