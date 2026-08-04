"""Testa o parser do CONFAZ (puro, sem rede) e os defaults de configuração.
A persistência (propostas/snapshot) vive em test_matrizes_propostas.py."""
from datetime import date

from app.modules.fiscal.crawlers.base import CestRecord
from app.modules.fiscal.crawlers.confaz_cest import ConfazCestExtractor
from app.modules.fiscal.crawlers.workers import _ufs_alvo

# Amostra no formato da página oficial consolidada do CV 142/18: Anexo I é a
# tabela de segmentos (3 colunas); os demais anexos têm 4 colunas
# (ITEM | CEST | NCM/SH | DESCRIÇÃO), com ruído proposital: cabeçalhos,
# máscara, célula com vários NCM, CEST inválido e linha repetida.
_HTML = """
<html><body>
<p>ANEXO I — SEGMENTOS DE MERCADORIAS</p>
<table>
 <tr><td>ITEM</td><td>NOME DO SEGMENTO</td><td>C&Oacute;DIGO DO SEGMENTO</td></tr>
 <tr><td>01</td><td>Autope&ccedil;as</td><td>01</td></tr>
 <tr><td>03</td><td>Cervejas, chopes, refrigerantes, &aacute;guas e outras bebidas</td><td>03</td></tr>
</table>
<p>ANEXO II — AUTOPEÇAS</p>
<table>
 <tr><th>ITEM</th><th>CEST</th><th>NCM/SH</th><th>DESCRI&Ccedil;&Atilde;O</th></tr>
 <tr><td>1.0</td><td>01.001.00</td><td>3815.12.10, 3815.12.90</td><td>Catalisadores</td></tr>
 <tr><td>5.0</td><td>01.005.00</td><td>4011.10.00</td><td>Pneus novos</td></tr>
 <tr><td>9.9</td><td>99999</td><td>1234</td><td>linha-lixo (CEST curto)</td></tr>
 <tr><td>5.0</td><td>01.005.00</td><td>4011.10.00</td><td>Pneus novos</td></tr>
</table>
<p>ANEXO III — CERVEJAS</p>
<table>
 <tr><td>1.0</td><td>03.001.00</td><td>2203.00.00</td><td>Cerveja</td></tr>
</table>
</body></html>
"""


def test_parse_confaz_html_normaliza_e_descarta_lixo():
    regs = ConfazCestExtractor().parse(_HTML.encode("utf-8"))
    # Célula com 2 NCM vira 2 registros; lixo (CEST curto) fica fora; a linha
    # repetida permanece — o dedup é papel do diff de propostas.
    assert [(r.cest, r.ncm) for r in regs] == [
        ("0100100", "38151210"),
        ("0100100", "38151290"),
        ("0100500", "40111000"),
        ("0100500", "40111000"),
        ("0300100", "22030000"),
    ]
    # Segmento vem do Anexo I via prefixo do CEST (2 dígitos).
    assert regs[2] == CestRecord("0100500", "40111000", "Pneus novos", "Autopeças")
    assert regs[4].segmento.startswith("Cervejas")


def test_ufs_alvo_normaliza_e_deduplica():
    assert _ufs_alvo("MG, sp,,go,MG") == ["MG", "SP", "GO"]


def test_config_padrao_do_crawler():
    """Defaults: as 7 UFs com clientes do escritório e a vigência-piso de
    jun/2026 (início das competências auditadas) parseável como data."""
    from app.core.config import Settings

    s = Settings(_env_file=None, database_url="x", database_privileged_url="x", jwt_secret="x")
    assert _ufs_alvo(s.crawler_uf_alvo) == ["MG", "PR", "SP", "DF", "RS", "RJ", "GO"]
    assert date.fromisoformat(s.crawler_vigencia_inicio) == date(2026, 6, 1)
