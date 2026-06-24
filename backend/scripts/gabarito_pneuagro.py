"""Teste de laboratório (matemática pura) — Gabarito Pneuagro (MG -> MG).

Injeta dados estáticos de uma NF-e de saída real no motor de ST e imprime a
memória de cálculo passo a passo para conferência manual contra o gabarito.

Uso:  ./.venv/Scripts/python.exe scripts/gabarito_pneuagro.py
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

# --- Inputs (Mock Data) -----------------------------------------------------
UF_ORIGEM = "MG"
UF_DESTINO = "MG"
VALOR_MERC = Decimal("3300.00")
ALIQ_INTERNA = Decimal("18.00")
NCM = "40111000"
CEST = "0100500"
MVA_ORIGINAL = Decimal("42.00")

# ICMS próprio real destacado na nota (= 3300 × 18%).
ICMS_PROPRIO = (VALOR_MERC * ALIQ_INTERNA / 100).quantize(Decimal("0.01"))

# MVA original do NCM cadastrada na matriz (mock do repositório).
mva_repo = MvaEmMemoria({(NCM, CEST, UF_DESTINO): str(MVA_ORIGINAL)})
engine = StAuditEngine(mva_repo, EnquadramentoEmMemoria(), FcpEmMemoria())

item = ItemFiscal(
    numero_item=1, ncm=NCM, cest=CEST, cfop="5405", orig="0",
    cst="10", mod_bc_st=4,                # tributada com ST, base por MVA
    v_prod=VALOR_MERC,                    # sem frete/seguro/outras/desconto/IPI
    v_bc=VALOR_MERC, v_icms=ICMS_PROPRIO, p_icms=ALIQ_INTERNA,
    p_mva_st=MVA_ORIGINAL,                # operação interna: MVA não ajusta
    v_bc_st=Decimal("4686.00"),          # valores declarados no XML (gabarito)
    v_icms_st=Decimal("249.48"),
)
op = Operacao(uf_emit=UF_ORIGEM, uf_dest=UF_DESTINO, crt=Crt.NORMAL, data=date(2026, 6, 1))

r = engine.auditar_item(item, op)
m = r.memoria

print("=" * 64)
print(" INPUTS (Mock — NF-e Pneuagro, saída MG -> MG)")
print("=" * 64)
print(f"  UF origem -> destino : {UF_ORIGEM} -> {UF_DESTINO}  (operação interna)")
print(f"  Valor da mercadoria  : {VALOR_MERC}")
print("  Frete/Seguro/Outras  : 0.00")
print(f"  Alíquota interna     : {ALIQ_INTERNA}%")
print(f"  NCM / CEST           : {NCM} / {CEST}")
print(f"  MVA original         : {MVA_ORIGINAL}%")
print(f"  CST / modBCST / CRT  : {item.cst} / {item.mod_bc_st} / Normal")

print("\n" + "=" * 64)
print(" PASSO A PASSO DO MOTOR")
print("=" * 64)
print(f"  1) Base ICMS Próprio       = {VALOR_MERC}")
print(f"  2) ICMS Próprio (18%)      = {ICMS_PROPRIO}")
print(f"  3) MVA aplicada            = {m.mva_aplicada.quantize(Decimal('0.01'))}% "
      f"(ajustada={m.mva_foi_ajustada} — {m.motivo_nao_ajuste})")
print(f"  4) Base de Cálculo do ST   = {m.base_st_calculada}   "
      f"(= {VALOR_MERC} × 1,42)")
print(f"  5) Débito ST (base × 18%)  = {m.icms_st_debito}")
print(f"  6) (-) Dedução ICMS Próprio= {m.deducao_aplicada}   (tipo: {m.deducao_tipo})")
print(f"  7) ICMS-ST FINAL           = {m.icms_st_calculado}")

print("\n" + "=" * 64)
print(" CONFERÊNCIA CONTRA O GABARITO")
print("=" * 64)
GABARITO = {
    "Base ICMS Próprio": (VALOR_MERC, Decimal("3300.00")),
    "ICMS Próprio": (ICMS_PROPRIO, Decimal("594.00")),
    "Base de Cálculo ST": (m.base_st_calculada, Decimal("4686.00")),
    "ICMS-ST FINAL": (m.icms_st_calculado, Decimal("249.48")),
}
tudo_ok = True
for nome, (calc, esperado) in GABARITO.items():
    ok = calc == esperado
    tudo_ok = tudo_ok and ok
    print(f"  [{'OK ' if ok else 'X  '}] {nome:<20}: motor={calc}  | gabarito={esperado}")

print("-" * 64)
print(f"  STATUS auditoria: {r.status}  | erros: {r.codigos_erro or '-'}")
print(f"  >>> ICMS-ST = {m.icms_st_calculado} "
      f"({'BATEU com 249.48' if m.icms_st_calculado == Decimal('249.48') else 'NAO bateu'})")
raise SystemExit(0 if tudo_ok else 1)
