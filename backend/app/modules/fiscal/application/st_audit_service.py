"""Orquestrador da auditoria de ICMS-ST de uma NF-e (a prova viva do ADR-0001).

Fluxo: agrega o frete dos CT-e vinculados → rateia por item → monta o ItemFiscal
ENRIQUECIDO (vProd + fração do frete) → carrega as matrizes (async, com vigência)
→ roda o motor PURO e síncrono → persiste o resultado em auditoria_icms_st.
"""
from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.application.frete_service import agregar_frete, ratear_frete
from app.modules.fiscal.domain.st import (
    Crt,
    ItemFiscal,
    Operacao,
    StAuditEngine,
)
from app.modules.fiscal.domain.st.money import ZERO, centavos
from app.modules.fiscal.infrastructure.matrizes_loaders import MatrizesLoader
from app.modules.fiscal.infrastructure.models import AuditoriaIcmsSt, NotaItem
from app.modules.fiscal.infrastructure.repositories import NotaRepository


def _crt(valor: str | None) -> Crt:
    """CRT do XML ('1'..'4') -> enum. Ausente assume Regime Normal (mais comum)."""
    try:
        return Crt(int(valor))
    except (TypeError, ValueError):
        return Crt.NORMAL


def _item_fiscal(it: NotaItem, frete_rateado: Decimal) -> ItemFiscal:
    """Monta o ItemFiscal enriquecido: frete do XML + fração do CT-e agregado."""
    return ItemFiscal(
        numero_item=it.numero_item, ncm=it.ncm or "", cest=it.cest or "",
        cfop=it.cfop or "", orig=it.orig or "0", cst=it.cst, csosn=it.csosn,
        mod_bc_st=it.mod_bc_st,
        v_prod=it.valor_produto, q_com=it.quantidade,
        v_frete=(it.valor_frete or ZERO) + frete_rateado,
        v_seg=it.valor_seguro, v_outro=it.valor_outro, v_desc=it.valor_desconto,
        v_ipi=it.valor_ipi,
        v_bc=it.base_calculo, v_icms=it.valor_icms, p_icms=it.p_icms, p_red_bc=it.p_red_bc,
        v_fcp=it.v_fcp,
        p_mva_st=it.p_mva_st, p_red_bc_st=it.p_red_bc_st, p_icms_st=it.p_icms_st,
        v_bc_st=it.v_bc_st, v_icms_st=it.valor_icms_st,
        p_fcp_st=it.p_fcp_st, v_bc_fcp_st=it.v_bc_fcp_st, v_fcp_st=it.v_fcp_st,
    )


def _memoria_json(memoria) -> dict | None:
    """Serializa a MemoriaCalculo para JSON (Decimal -> str)."""
    if memoria is None:
        return None
    return {
        k: (str(v) if isinstance(v, Decimal) else v)
        for k, v in dataclasses.asdict(memoria).items()
    }


class StAuditService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = NotaRepository(session)
        self.loader = MatrizesLoader(session)

    async def auditar_nota(self, empresa_id: UUID, nota_id: UUID) -> list[AuditoriaIcmsSt]:
        nota = await self.repo.by_id(nota_id)
        if nota is None:
            return []
        itens_db = await self.repo.items_for(nota_id)
        if not itens_db:
            return []

        # ADR-0001: agrega o frete dos CT-e vinculados e rateia por item.
        vinculos = await self.repo.ctes_da_nfe(empresa_id, nota.chave_acesso)
        rateio = ratear_frete(itens_db, agregar_frete(vinculos))
        operacao = Operacao(
            uf_emit=nota.uf_emit or "", uf_dest=nota.uf_dest or "",
            crt=_crt(nota.crt_emit), data=date.fromisoformat(nota.data_emissao),
            saida=(nota.fluxo == "saida"),   # bifurcação tpNF no motor
        )
        itens_fiscais = [_item_fiscal(it, rateio[it.numero_item]) for it in itens_db]

        # Carrega-então-calcula: hidrata os repos sync e roda o motor puro.
        matrizes = await self.loader.hidratar(itens_fiscais, operacao)
        engine = StAuditEngine(
            mva_repo=matrizes.mva,
            enquadramento_repo=matrizes.enquadramento,
            fcp_repo=matrizes.fcp,
            protocolo_repo=matrizes.protocolo,
        )
        resultados = engine.auditar_nota(itens_fiscais, operacao)

        # Idempotente: re-auditar (ex.: CT-e que chegou depois) substitui o anterior.
        await self.session.execute(
            delete(AuditoriaIcmsSt).where(AuditoriaIcmsSt.nota_id == nota_id)
        )

        registros: list[AuditoriaIcmsSt] = []
        for it_db, res in zip(itens_db, resultados, strict=False):
            m = res.memoria
            registros.append(AuditoriaIcmsSt(
                id=uuid4(), tenant_id=nota.tenant_id, empresa_id=empresa_id, nota_id=nota.id,
                chave_acesso=nota.chave_acesso, numero_item=it_db.numero_item,
                cst_csosn=it_db.cst or it_db.csosn, mod_bc_st=it_db.mod_bc_st,
                pmva_xml=it_db.p_mva_st, pmva_calculada=(centavos(m.mva_aplicada) if m else ZERO),
                vbc_st_xml=it_db.v_bc_st, vbc_st_calculado=(m.base_st_calculada if m else ZERO),
                vicms_st_xml=it_db.valor_icms_st,
                vicms_st_calculado=(m.icms_st_calculado if m else ZERO),
                vicms_st_divergencia=res.divergencia_icms_st,
                vfcp_st_xml=it_db.v_fcp_st, vfcp_st_calculado=(m.fcp_st_calculado if m else ZERO),
                status=res.status, codigo_erro=(", ".join(res.codigos_erro) or None),
                observacao=res.observacao,
                memoria=_memoria_json(m),
            ))
        self.session.add_all(registros)
        await self.session.flush()
        return registros
