"""2º Teste de laboratório — Operação INTERESTADUAL com Ajuste de MVA.

NF-e de ENTRADA: origem SP, destino MG, autopeça (paralama, NCM 87082919).
O remetente NÃO destacou ST → responsabilidade do destinatário em MG
(antecipação tributária). O motor recalcula o ST devido.

⚠️ A matriz de exemplo do Vault não traz o NCM 87082919. Para reproduzir o ST
confirmado pelo cliente (R$ 177,50), a MVA Original cadastrada teria de ser
~87,77%. Esse valor está registrado no mock abaixo e deve ser conferido contra
o RICMS-MG / Protocolo de autopeças real.

Uso:  ./.venv/Scripts/python.exe scripts/gabarito_autopeca.py
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
UF_ORIGEM = "SP"
UF_DESTINO = "MG"
VALOR_MERC = Decimal("731.35")
FRETE_RATEADO = Decimal("68.05")   # CT-e separado (R$136,10) rateado por 2 itens
ALIQ_INTER = Decimal("12.00")
ALIQ_INTERNA = Decimal("18.00")
NCM = "87082919"
CEST = "0107500"                 # CEST real do paralama (01.075.00)
MVA_ORIGINAL = Decimal("71.78")  # MVA Original real — legislação de MG (autopeças)

ICMS_PROPRIO = (VALOR_MERC * ALIQ_INTER / 100).quantize(Decimal("0.01"))  # 12% destacado

mva_repo = MvaEmMemoria({(NCM, CEST, UF_DESTINO): str(MVA_ORIGINAL)})
engine = StAuditEngine(mva_repo, EnquadramentoEmMemoria(), FcpEmMemoria())

# Entrada: remetente destacou só o ICMS próprio (12%), sem ST (antecipação).
item = ItemFiscal(
    numero_item=1, ncm=NCM, cest=CEST, cfop="6102", orig="0",
    cst="00", mod_bc_st=4,
    v_prod=VALOR_MERC, v_frete=FRETE_RATEADO,       # frete entra na base do ST
    v_bc=VALOR_MERC, v_icms=ICMS_PROPRIO, p_icms=ALIQ_INTER,
    v_bc_st=Decimal("0"), v_icms_st=Decimal("0"),   # ST omitido pelo remetente
)
op = Operacao(uf_emit=UF_ORIGEM, uf_dest=UF_DESTINO, crt=Crt.NORMAL, data=date(2026, 6, 1))

r = engine.auditar_item(item, op)
m = r.memoria

print("=" * 66)
print(" INPUTS (NF-e de entrada — autopeça, SP -> MG, antecipação)")
print("=" * 66)
print(f"  UF origem -> destino : {UF_ORIGEM} -> {UF_DESTINO}  (interestadual)")
print(f"  Valor da mercadoria  : {VALOR_MERC}")
print(f"  Frete rateado (CT-e) : {FRETE_RATEADO}   (entra na base do ST, não no próprio)")
print(f"  Alíq. interestadual  : {ALIQ_INTER}%   (ICMS próprio destacado)")
print(f"  Alíq. interna (MG)   : {ALIQ_INTERNA}%")
print(f"  NCM / CEST           : {NCM} / {CEST}")

print("\n" + "=" * 66)
print(" PASSO A PASSO DO MOTOR")
print("=" * 66)
print(f"  1) Operação           : interestadual={op.interestadual}  "
      f"(alq_inter detectada={m.alq_inter}%, alq_intra={m.alq_intra}%)")
print(f"  2) MVA Original (matriz)  = {m.mva_original}%")
print(f"  3) MVA AJUSTADA aplicada  = {m.mva_aplicada.quantize(Decimal('0.01'))}%  "
      f"(ajustada={m.mva_foi_ajustada})")
print(f"  4) Base de Cálculo do ST  = {m.base_st_calculada}   "
      f"(= {VALOR_MERC} × (1 + MVA_aj))")
print(f"  5) Débito ST (base × 18%) = {m.icms_st_debito}")
print(f"  6) (-) ICMS Próprio (12%) = {m.deducao_aplicada}   (tipo: {m.deducao_tipo})")
print(f"  7) ICMS-ST DEVIDO         = {m.icms_st_calculado}")

print("\n" + "=" * 66)
print(" RESULTADO (teste independente com a MVA real 71,78%)")
print("=" * 66)
print(f"  ICMS Próprio (abatimento) : {m.deducao_aplicada}")
print(f"  ICMS-ST DEVIDO (motor)    : {m.icms_st_calculado}")
print(f"  STATUS auditoria          : {r.status}  | erros: {r.codigos_erro or '-'}")
delta = (m.icms_st_calculado - Decimal("177.50"))
print("-" * 66)
print(f"  Comparação com o nº citado pelo cliente (177,50): delta = R$ {delta}")
raise SystemExit(0)
