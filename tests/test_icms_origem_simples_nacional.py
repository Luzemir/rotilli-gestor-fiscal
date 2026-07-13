"""
Testes da extração de BC/VLR de ICMS de origem para notas do Simples Nacional
com permissão de crédito (nfe_parser).

Notas normais (ICMS00, ICMS10, ...) trazem vBC/vICMS. Notas do Simples Nacional
CSOSN 101 (ICMSSN101) e 201 (ICMSSN201) NÃO têm vBC/vICMS — declaram o crédito
de ICMS aproveitável em vCredICMSSN. Mapeamento nas colunas da planilha Original:
  [VLR ICMS (ORIGEM)] = vCredICMSSN
  [BC  ICMS (ORIGEM)] = vProd + frete + seguro/desp. acess. - desconto
A BC é composta em parsear_xml, depois do rateio de frete/seguro/despesas.

Execução:
    python -m pytest tests/test_icms_origem_simples_nacional.py -v
"""
import sys
import os
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'core'))

import nfe_parser as np


# ── Extração direta do grupo ICMS (BC composta só ocorre no parsear_xml) ──────

def _det(icms_xml, vprod='100.00'):
    """Monta um <det> com o grupo de ICMS informado, no namespace da NF-e."""
    xml = (
        '<det xmlns="http://www.portalfiscal.inf.br/nfe" nItem="1">'
        f'<prod><vProd>{vprod}</vProd></prod>'
        f'<imposto><ICMS>{icms_xml}</ICMS></imposto>'
        '</det>'
    )
    return ET.fromstring(xml)


class TestExtrairGrupoICMS:

    def test_icms00_le_vbc_vicms(self):
        det = _det('<ICMS00><orig>0</orig><CST>00</CST>'
                   '<vBC>100.00</vBC><pICMS>12.00</pICMS><vICMS>12.00</vICMS></ICMS00>')
        assert np._extrair_icms_origem(det) == (100.0, 12.0, False)

    def test_icms40_isento_sem_bc_retorna_none(self):
        det = _det('<ICMS40><orig>0</orig><CST>40</CST></ICMS40>')
        assert np._extrair_icms_origem(det) == (None, None, False)

    def test_sn101_retorna_credito_e_sinaliza_compor_base(self):
        det = _det('<ICMSSN101><orig>0</orig><CSOSN>101</CSOSN>'
                   '<pCredSN>2.5600</pCredSN><vCredICMSSN>2.56</vCredICMSSN></ICMSSN101>')
        assert np._extrair_icms_origem(det) == (None, 2.56, True)

    def test_sn102_sem_credito_retorna_none(self):
        det = _det('<ICMSSN102><orig>0</orig><CSOSN>102</CSOSN></ICMSSN102>')
        assert np._extrair_icms_origem(det) == (None, None, False)


# ── Composição da BC ponta a ponta (parsear_xml) ──────────────────────────────

_NS_DECL = 'xmlns="http://www.portalfiscal.inf.br/nfe"'


def _nfe_xml(itens_xml, tot_frete='0.00', tot_seg='0.00', tot_outro='0.00'):
    """Monta uma NF-e mínima com os <det> informados e totais para rateio."""
    return (
        f'<nfeProc {_NS_DECL}><NFe><infNFe Id="NFe31260400000000000000550010000000011000000001">'
        '<ide><nNF>123</nNF><dhEmi>2026-05-15T10:00:00-03:00</dhEmi></ide>'
        '<emit><CNPJ>00000000000191</CNPJ><xNome>FORN SIMPLES</xNome>'
        '<enderEmit><UF>MG</UF></enderEmit></emit>'
        f'{itens_xml}'
        f'<total><ICMSTot><vFrete>{tot_frete}</vFrete><vSeg>{tot_seg}</vSeg>'
        f'<vOutro>{tot_outro}</vOutro></ICMSTot></total>'
        '</infNFe></NFe></nfeProc>'
    )


def _det_sn(nitem, vprod, vcred, frete='0.00', seg='0.00', outro='0.00', desc='0.00'):
    return (
        f'<det nItem="{nitem}"><prod><cProd>P{nitem}</cProd><xProd>ITEM {nitem}</xProd>'
        f'<vProd>{vprod}</vProd><vFrete>{frete}</vFrete><vSeg>{seg}</vSeg>'
        f'<vOutro>{outro}</vOutro><vDesc>{desc}</vDesc></prod>'
        '<imposto><ICMS><ICMSSN101><orig>0</orig><CSOSN>101</CSOSN>'
        f'<pCredSN>2.5600</pCredSN><vCredICMSSN>{vcred}</vCredICMSSN></ICMSSN101></ICMS></imposto></det>'
    )


def _parsear(xml, tmp_path):
    caminho = tmp_path / 'nota.xml'
    caminho.write_text(xml, encoding='utf-8')
    return np.parsear_xml(str(caminho))


class TestComporBaseParsearXml:

    def test_base_composta_valores_por_item(self, tmp_path):
        # BC = vProd 100 + frete 5 + (seg 2 + desp.acess 3) - desc 1 = 109
        item_xml = _det_sn(1, '100.00', '2.56', frete='5.00', seg='2.00', outro='3.00', desc='1.00')
        nota = _parsear(_nfe_xml(item_xml), tmp_path)
        item = nota['itens'][0]
        assert item['vlr_icms_origem'] == 2.56
        assert item['bc_icms_origem'] == 109.0

    def test_base_composta_apos_rateio_do_total(self, tmp_path):
        # Frete só no total da nota (10) e único item -> rateio joga tudo no item.
        # BC = vProd 100 + frete 10 = 110
        item_xml = _det_sn(1, '100.00', '2.56')
        nota = _parsear(_nfe_xml(item_xml, tot_frete='10.00'), tmp_path)
        assert nota['itens'][0]['bc_icms_origem'] == 110.0

    def test_nota_normal_nao_e_afetada(self, tmp_path):
        det = (
            '<det nItem="1"><prod><cProd>P1</cProd><xProd>ITEM</xProd><vProd>100.00</vProd>'
            '<vFrete>5.00</vFrete></prod>'
            '<imposto><ICMS><ICMS00><orig>0</orig><CST>00</CST>'
            '<vBC>105.00</vBC><vICMS>12.60</vICMS></ICMS00></ICMS></imposto></det>'
        )
        nota = _parsear(_nfe_xml(det), tmp_path)
        item = nota['itens'][0]
        assert item['bc_icms_origem'] == 105.0    # vBC declarado, não composto
        assert item['vlr_icms_origem'] == 12.60
