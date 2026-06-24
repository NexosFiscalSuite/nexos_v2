"""3º Teste de laboratório — CST 70 (Redução de Base de Cálculo).

Operação INTERNA (MG->MG) para isolar a lógica de redução (sem ajuste de MVA).
Verifica se o motor aplica pRedBC (próprio) e pRedBCST (ST) antes dos débitos.

Uso:  ./.venv/Scripts/python.exe scripts/gabarito_cst70.py
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
MVA_ORIGINAL = Decimal("40.00")
P_RED_BC = Decimal("33.33")      # redução da base do ICMS próprio
P_RED_BC_ST = Decimal("33.33")   # redução da base do ST
NCM, CEST = "84099900", "0102200"   # NCM neutro (sem FCP em MG) com MVA mockada

# Operação própria (CST 70): base reduzida e ICMS próprio destacado na nota.
BASE_PROPRIO_RED = (VALOR_MERC * (1 - P_RED_BC / 100)).quantize(Decimal("0.01"))  # 666,70
ICMS_PROPRIO = (BASE_PROPRIO_RED * ALIQ_INTERNA / 100).quantize(Decimal("0.01"))  # 120,01

engine = StAuditEngine(
    MvaEmMemoria({(NCM, CEST, "MG"): str(MVA_ORIGINAL)}),
    EnquadramentoEmMemoria(),
    FcpEmMemoria(),
)
item = ItemFiscal(
    numero_item=1, ncm=NCM, cest=CEST, cfop="5405", orig="0",
    cst="70", mod_bc_st=4,
    v_prod=VALOR_MERC,
    v_bc=BASE_PROPRIO_RED, v_icms=ICMS_PROPRIO, p_icms=ALIQ_INTERNA, p_red_bc=P_RED_BC,
    p_red_bc_st=P_RED_BC_ST, p_mva_st=MVA_ORIGINAL,
    v_bc_st=Decimal("933.38"), v_icms_st=Decimal("48.00"),   # declarados (corretos)
)
op = Operacao(uf_emit="MG", uf_dest="MG", crt=Crt.NORMAL, data=date(2026, 6, 1))

r = engine.auditar_item(item, op)
m = r.memoria
base_st_bruta = (VALOR_MERC * (1 + MVA_ORIGINAL / 100)).quantize(Decimal("0.01"))  # 1400,00

print("=" * 64)
print(" INPUTS (Mock — CST 70, redução de base, interna MG->MG)")
print("=" * 64)
print(f"  Valor da mercadoria  : {VALOR_MERC}")
print(f"  Alíquota interna     : {ALIQ_INTERNA}%   |   MVA original: {MVA_ORIGINAL}%")
print(f"  pRedBC (próprio)     : {P_RED_BC}%   |   pRedBCST (ST): {P_RED_BC_ST}%")
print("  CST / modBCST / CRT  : 70 / 4 / Normal")

print("\n" + "=" * 64)
print(" PASSO A PASSO DO MOTOR")
print("=" * 64)
print(f"  1) Base Próprio REDUZIDA   = {BASE_PROPRIO_RED}   (1000 × (1 − 33,33%))")
print(f"  2) ICMS Próprio (18%)      = {ICMS_PROPRIO}")
print(f"  3) MVA aplicada            = {m.mva_aplicada.quantize(Decimal('0.01'))}%  "
      f"(ajustada={m.mva_foi_ajustada})")
print(f"  4) Base ST BRUTA           = {base_st_bruta}   (1000 × 1,40)")
print(f"  5) Base ST REDUZIDA        = {m.base_st_calculada}   (1400 × (1 − 33,33%))")
print(f"  6) Débito ST (×18%)        = {m.icms_st_debito}")
print(f"  7) (-) Dedução ICMS Próprio= {m.deducao_aplicada}   (tipo: {m.deducao_tipo})")
print(f"  8) ICMS-ST FINAL           = {m.icms_st_calculado}")

print("\n" + "=" * 64)
print(" CONFERÊNCIA CONTRA O GABARITO")
print("=" * 64)
GABARITO = {
    "Base Próprio Reduzida": (BASE_PROPRIO_RED, Decimal("666.70")),
    "ICMS Próprio": (ICMS_PROPRIO, Decimal("120.01")),
    "Base ST Bruta": (base_st_bruta, Decimal("1400.00")),
    "Base ST Reduzida": (m.base_st_calculada, Decimal("933.38")),
    "Débito ST": (m.icms_st_debito, Decimal("168.01")),
    "ICMS-ST FINAL": (m.icms_st_calculado, Decimal("48.00")),
}
tudo_ok = True
for nome, (calc, esperado) in GABARITO.items():
    ok = calc == esperado
    tudo_ok = tudo_ok and ok
    print(f"  [{'OK ' if ok else 'X  '}] {nome:<22}: motor={calc}  | gabarito={esperado}")
print("-" * 64)
print(f"  STATUS auditoria: {r.status}  | erros: {r.codigos_erro or '-'}")
print(f"  >>> ICMS-ST = {m.icms_st_calculado} "
      f"({'BATEU com 48,00' if m.icms_st_calculado == Decimal('48.00') else 'NAO bateu'})")
raise SystemExit(0 if tudo_ok else 1)
