"""Base compartilhada das cartas timbradas Sol (PDF via fpdf2).

Identidade visual extraída do timbrado oficial ("cabecalhosol 2.0"):
azul-marinho #24477B, lilás #A4A7C6 e a logomarca Sol. As cartas de IBS/CBS
e de ICMS-ST montam o corpo; o timbre (cabeçalho/rodapé), a tipografia
latin-1 e os formatadores pt-BR vivem aqui (uma fonte só).
"""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

NAVY = (36, 71, 123)      # #24477B
LILAS = (164, 167, 198)   # #A4A7C6
CINZA = (90, 96, 105)
_LOGO = Path(__file__).resolve().parents[3] / "shared" / "assets" / "sol-logo.png"

_TROCAS = str.maketrans({"—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "→": ">"})


def _t(s) -> str:
    """Fontes core do PDF são latin-1 — cobre o português; travessões e aspas
    tipográficas são normalizados antes (senão virariam '?')."""
    return (
        str(s if s is not None else "")
        .translate(_TROCAS)
        .encode("latin-1", "replace")
        .decode("latin-1")
    )


def _pct(v) -> str:
    return f"{float(v or 0):.2f}%".replace(".", ",")


def _brl(v) -> str:
    s = f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _cnpj(c) -> str:
    c = str(c or "")
    if len(c) == 14:
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    return c or "—"


class CartaTimbrada(FPDF):
    """Papel timbrado Sol: logo + barras da marca + filete duplo no cabeçalho;
    razão social/CNPJ e nº de página no rodapé."""

    def header(self):
        # Logo quase quadrada (472×378): 30mm de largura ≈ 24mm de altura.
        if _LOGO.exists():
            self.image(str(_LOGO), x=14, y=8, w=30)
        # Barras da marca (eco das faixas diagonais do timbrado)
        self.set_fill_color(*NAVY)
        self.rect(176, 8, 5.5, 24, "F")
        self.set_fill_color(*LILAS)
        self.rect(184, 8, 3.5, 24, "F")
        self.set_draw_color(*NAVY)
        self.set_line_width(0.7)
        self.line(14, 35, 196, 35)
        self.set_draw_color(*LILAS)
        self.set_line_width(0.4)
        self.line(14, 36.6, 196, 36.6)
        self.set_y(43)

    def footer(self):
        self.set_y(-17)
        self.set_draw_color(*LILAS)
        self.set_line_width(0.4)
        self.line(14, self.get_y(), 196, self.get_y())
        self.set_font("helvetica", "", 8)
        self.set_text_color(*CINZA)
        self.cell(0, 9, _t("Sol Contabilidade e Consultoria · CNPJ 04.640.241/0001-56"), align="C")
        self.set_x(-30)
        self.cell(0, 9, _t(f"pág. {self.page_no()}"), align="R")


def nova_carta() -> CartaTimbrada:
    pdf = CartaTimbrada(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=22)
    pdf.set_margins(14, 10, 14)
    pdf.add_page()
    return pdf
