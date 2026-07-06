"""
Testes unitários para sanitizar_ean_gtin14.

Execução:
    cd c:/APP/Rotilli_GestorFIscal
    python -m pytest tests/test_sanitizar_ean.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'core'))

from cmed_comparador import sanitizar_ean_gtin14


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _calcular_dv_ean13(doze: str) -> int:
    """Calcula o dígito verificador EAN-13 para 12 dígitos — referência independente."""
    soma = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(doze))
    return (10 - (soma % 10)) % 10


# ---------------------------------------------------------------------------
# Cenários de CONVERSÃO — GTIN-14 iniciando com '1' deve ser convertido
# ---------------------------------------------------------------------------

class TestConversaoGtin14:

    def test_gtin14_tipico_medicamento(self):
        # GTIN-14: '1' + '789100031550' + dígito GTIN (qualquer valor, ignorado)
        # EAN-13 esperado: '789100031550' + dv
        doze = '789100031550'
        dv_esperado = _calcular_dv_ean13(doze)
        gtin14 = '1' + doze + str((dv_esperado + 1) % 10)  # dv GTIN propositalmente diferente
        resultado = sanitizar_ean_gtin14(gtin14)
        assert resultado == doze + str(dv_esperado), (
            f"GTIN-14 {gtin14!r} → esperado {doze + str(dv_esperado)!r}, obtido {resultado!r}"
        )

    def test_gtin14_digito_verificador_recalculado_independente_do_gtin_dv(self):
        # O dígito verificador GTIN-14 (último dígito) deve ser completamente ignorado.
        # Independente do valor do 14º dígito, o resultado deve sempre ser o mesmo EAN-13.
        doze = '456789012345'
        dv13 = _calcular_dv_ean13(doze)
        ean13_esperado = doze + str(dv13)
        for ultimo_digito in range(10):
            gtin14 = '1' + doze + str(ultimo_digito)
            assert sanitizar_ean_gtin14(gtin14) == ean13_esperado

    def test_gtin14_zeros(self):
        doze = '000000000000'
        dv = _calcular_dv_ean13(doze)  # 0
        assert sanitizar_ean_gtin14('1' + doze + '0') == doze + str(dv)

    def test_gtin14_noves(self):
        doze = '999999999999'
        dv = _calcular_dv_ean13(doze)
        assert sanitizar_ean_gtin14('1' + doze + '0') == doze + str(dv)

    def test_gtin14_digitos_uniformes(self):
        doze = '111111111111'
        dv = _calcular_dv_ean13(doze)  # 6
        assert sanitizar_ean_gtin14('1' + doze + '0') == doze + str(dv)

    def test_resultado_tem_exatamente_13_digitos(self):
        gtin14 = '17891000315504'
        resultado = sanitizar_ean_gtin14(gtin14)
        assert len(resultado) == 13

    def test_resultado_e_numerico(self):
        gtin14 = '17891000315504'
        resultado = sanitizar_ean_gtin14(gtin14)
        assert resultado.isdigit()

    def test_dv_ean13_correto(self):
        # Verifica que o dígito verificador do EAN-13 resultante é válido.
        doze = '789100031550'
        gtin14 = '1' + doze + '4'
        resultado = sanitizar_ean_gtin14(gtin14)
        dv_calculado = _calcular_dv_ean13(resultado[:12])
        assert int(resultado[12]) == dv_calculado


# ---------------------------------------------------------------------------
# Cenários de PASS-THROUGH — não devem ser alterados
# ---------------------------------------------------------------------------

class TestPassThrough:

    def test_ean13_normal_nao_altera(self):
        assert sanitizar_ean_gtin14('7891234567895') == '7891234567895'

    def test_ean13_iniciando_com_1_nao_altera(self):
        # 13 dígitos iniciando com '1' NÃO é GTIN-14
        assert sanitizar_ean_gtin14('1234567890128') == '1234567890128'

    def test_ean8_nao_altera(self):
        assert sanitizar_ean_gtin14('12345670') == '12345670'

    def test_ean12_upc_nao_altera(self):
        assert sanitizar_ean_gtin14('012345678905') == '012345678905'

    def test_gtin14_prefixo_0_nao_altera(self):
        assert sanitizar_ean_gtin14('07891234567890') == '07891234567890'

    def test_gtin14_prefixo_2_nao_altera(self):
        assert sanitizar_ean_gtin14('27891234567890') == '27891234567890'

    def test_gtin14_prefixo_9_nao_altera(self):
        assert sanitizar_ean_gtin14('97891234567890') == '97891234567890'

    def test_codigo_interno_alfanumerico_nao_altera(self):
        assert sanitizar_ean_gtin14('ABC12345678901') == 'ABC12345678901'

    def test_codigo_interno_curto_nao_altera(self):
        assert sanitizar_ean_gtin14('COD001') == 'COD001'

    def test_string_vazia_nao_altera(self):
        assert sanitizar_ean_gtin14('') == ''

    def test_15_digitos_nao_altera(self):
        assert sanitizar_ean_gtin14('178910003155049') == '178910003155049'

    def test_13_digitos_iniciando_com_1_nao_altera(self):
        # Deve passar intacto — não é GTIN-14 (tem 13, não 14 dígitos)
        ean = '1789100031550'
        assert sanitizar_ean_gtin14(ean) == ean

    def test_14_digitos_com_letra_nao_altera(self):
        # Tem 14 chars e começa com '1', mas não é totalmente numérico
        assert sanitizar_ean_gtin14('1A891000315504') == '1A891000315504'
