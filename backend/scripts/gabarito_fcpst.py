"""5º Teste de laboratório — FCP-ST (Fundo de Combate à Pobreza) em trilha paralela.

Operação interna MG->MG, bebida alcoólica sujeita a FCP. Prova que o motor:
  1. calcula o FCP-ST numa trilha SEPARADA, nunca somada ao ICMS-ST;
  2. deduz o FCP próprio do FCP-ST (não-cumulatividade, NT 2016.002), evitando
     que a carga final do fundo ultrapasse o teto legal (bitributação).

Uso:  ./.venv/Scripts/python.exe scripts/gabarito_fcpst.py
"""
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.modules.fiscal.domain.st import (  # noqa: E402
    Crt,
    EnquadramentoEmMemoria,
    FcpEmMemoria,
    ItemFiscal,
    MvaEmMemoria,
    Operacao,
    StAuditEngine,
)

# --- Inputs (Mock) ----------------------------------------------------------
VALOR_MERC = Decimal("1000.00")
ALIQ_INTERNA = Decimal("18.00")
ALIQ_FCP = Decimal("2.00")
MVA_ORIGINAL = Decimal("50.00")
NCM, CEST = "22084000", "0202200"   # cachaça (NCM com FCP em MG no mock)

ICMS_PROPRIO = (VALOR_MERC * ALIQ_INTERNA / 100).quantize(Decimal("0.01"))  # 180,00
FCP_PROPRIO = (VALOR_MERC * ALIQ_FCP / 100).quantize(Decimal("0.01"))       # 20,00

engine = StAuditEngine(
    MvaEmMemoria({(NCM, CEST, "MG"): str(MVA_ORIGINAL)}),
    EnquadramentoEmMemoria(),
    FcpEmMemoria({("MG", NCM): str(ALIQ_FCP)}),   # FCP 2% para esse NCM em MG
)
item = ItemFiscal(
    numero_item=1, ncm=NCM, cest=CEST, cfop="5405", orig="0",
    cst="10", mod_bc_st=4, v_prod=VALOR_MERC,
    v_bc=VALOR_MERC, v_icms=ICMS_PROPRIO, p_icms=ALIQ_INTERNA, v_fcp=FCP_PROPRIO,
    p_mva_st=MVA_ORIGINAL,
    v_bc_st=Decimal("1500.00"), v_icms_st=Decimal("90.00"),
    p_fcp_st=ALIQ_FCP, v_bc_fcp_st=Decimal("1500.00"), v_fcp_st=Decimal("10.00"),
)
op = Operacao(uf_emit="MG", uf_dest="MG", crt=Crt.NORMAL, data=date(2026, 6, 1))

r = engine.auditar_item(item, op)
m = r.memoria

print("=" * 70)
print(" INPUTS (Mock — FCP-ST, bebida alcoólica, interna MG->MG)")
print("=" * 70)
print(f"  Valor da mercadoria : {VALOR_MERC}   |   MVA original: {MVA_ORIGINAL}%")
print(f"  Alíq. ICMS interna  : {ALIQ_INTERNA}%   |   Alíq. FCP: {ALIQ_FCP}%")

print("\n" + "=" * 70)
print(" TRILHA 1 — ICMS-ST")
print("=" * 70)
print(f"  Base ST              = {m.base_st_calculada}   (1000 × 1,50)")
print(f"  Débito ICMS-ST (18%) = {m.icms_st_debito}")
print(f"  (-) ICMS Próprio     = {m.deducao_aplicada}")
print(f"  ICMS-ST FINAL        = {m.icms_st_calculado}")

print("\n" + "=" * 70)
print(" TRILHA 2 — FCP-ST (paralela: NUNCA somada ao ICMS-ST)")
print("=" * 70)
print(f"  Débito FCP-ST (2%)   = {m.fcp_st_debito}   (1500 × 2%)")
print(f"  (-) FCP Próprio      = {m.fcp_st_deducao}   (não-cumulatividade, NT 2016.002)")
print(f"  FCP-ST FINAL         = {m.fcp_st_calculado}")

print("\n" + "=" * 70)
print(" CONFERÊNCIA CONTRA O GABARITO")
print("=" * 70)
GABARITO = {
    "ICMS-ST (trilha 1)": (m.icms_st_calculado, Decimal("90.00")),
    "FCP-ST (trilha 2)": (m.fcp_st_calculado, Decimal("10.00")),
}
tudo_ok = True
for nome, (calc, esperado) in GABARITO.items():
    ok = calc == esperado
    tudo_ok = tudo_ok and ok
    print(f"  [{'OK ' if ok else 'X  '}] {nome:<20}: motor={calc}  | gabarito={esperado}")
print("-" * 70)
print(f"  Trilhas independentes (FCP-ST nunca no ICMS-ST): "
      f"{'OK' if m.icms_st_calculado != m.fcp_st_calculado else 'verificar'}")
print(f"  STATUS auditoria: {r.status}  | erros: {r.codigos_erro or '-'}")
raise SystemExit(0 if tudo_ok else 1)
