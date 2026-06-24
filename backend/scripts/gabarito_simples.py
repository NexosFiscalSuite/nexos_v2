"""4º Teste de laboratório — Emitente Simples Nacional (CSOSN 201), SP->MG.

Prova duas regras de ouro do Cérebro Tributário:
  1. Remetente Simples (CRT=1) => a MVA NÃO ajusta (Conv. 142/2018, cl. 11ª §1º).
  2. Dedução do ICMS próprio é TEÓRICA = base × alíquota interestadual (12%),
     ignorando o que o Simples efetivamente pagou na guia (DAS).

Uso:  ./.venv/Scripts/python.exe scripts/gabarito_simples.py
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
ALIQ_INTER = Decimal("12.00")
ALIQ_INTERNA = Decimal("18.00")
MVA_ORIGINAL = Decimal("50.00")
NCM, CEST = "39173900", "1001100"   # NCM neutro (sem FCP em MG) com MVA mockada

engine = StAuditEngine(
    MvaEmMemoria({(NCM, CEST, "MG"): str(MVA_ORIGINAL)}),
    EnquadramentoEmMemoria(),
    FcpEmMemoria(),
)
# Emitente Simples: CSOSN 201, sem ICMS próprio destacado (v_icms/v_bc = 0).
item = ItemFiscal(
    numero_item=1, ncm=NCM, cest=CEST, cfop="6102", orig="0",
    csosn="201", mod_bc_st=4, v_prod=VALOR_MERC,
    p_mva_st=MVA_ORIGINAL,                        # declarado: MVA original (sem ajuste)
    v_bc_st=Decimal("1500.00"), v_icms_st=Decimal("150.00"),
)
op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.SIMPLES, data=date(2026, 6, 1))

r = engine.auditar_item(item, op)
m = r.memoria

print("=" * 64)
print(" INPUTS (Mock — Simples Nacional CSOSN 201, SP->MG)")
print("=" * 64)
print("  Emitente (CRT)       : 1 (Simples Nacional)")
print(f"  Valor da mercadoria  : {VALOR_MERC}")
print(f"  Alíq. inter / interna: {ALIQ_INTER}% / {ALIQ_INTERNA}%")
print(f"  MVA original         : {MVA_ORIGINAL}%")

print("\n" + "=" * 64)
print(" PASSO A PASSO DO MOTOR")
print("=" * 64)
print(f"  1) MVA aplicada            = {m.mva_aplicada.quantize(Decimal('0.01'))}%  "
      f"(ajustada={m.mva_foi_ajustada} — {m.motivo_nao_ajuste})")
print(f"  2) Base de Cálculo do ST   = {m.base_st_calculada}   (1000 × 1,50)")
print(f"  3) Débito ST (×18%)        = {m.icms_st_debito}")
print(f"  4) (-) Dedução TEÓRICA     = {m.deducao_aplicada}   "
      f"(tipo: {m.deducao_tipo} — 1000 × 12%)")
print(f"  5) ICMS-ST FINAL           = {m.icms_st_calculado}")

print("\n" + "=" * 64)
print(" CONFERÊNCIA CONTRA O GABARITO")
print("=" * 64)
GABARITO = {
    "MVA aplicada (%)": (m.mva_aplicada.quantize(Decimal("0.01")), Decimal("50.00")),
    "Base ST": (m.base_st_calculada, Decimal("1500.00")),
    "Débito ST": (m.icms_st_debito, Decimal("270.00")),
    "Dedução teórica": (m.deducao_aplicada, Decimal("120.00")),
    "ICMS-ST FINAL": (m.icms_st_calculado, Decimal("150.00")),
}
tudo_ok = True
for nome, (calc, esperado) in GABARITO.items():
    ok = calc == esperado
    tudo_ok = tudo_ok and ok
    print(f"  [{'OK ' if ok else 'X  '}] {nome:<18}: motor={calc}  | gabarito={esperado}")
print("-" * 64)
ajuste_ok = m.mva_foi_ajustada is False
ded_ok = m.deducao_tipo == "teorica"
print(f"  Trava de não-ajuste (CRT=1): {'OK' if ajuste_ok else 'FALHOU'}")
print(f"  Dedução teórica (não a guia): {'OK' if ded_ok else 'FALHOU'}")
print(f"  STATUS auditoria: {r.status}  | erros: {r.codigos_erro or '-'}")
print(f"  >>> ICMS-ST = {m.icms_st_calculado} "
      f"({'BATEU com 150,00' if m.icms_st_calculado == Decimal('150.00') else 'NAO bateu'})")
raise SystemExit(0 if (tudo_ok and ajuste_ok and ded_ok) else 1)
