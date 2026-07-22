"""Reprocessamento RETROATIVO de notas travadas.

Fecha a lacuna temporal: uma nota importada ontem sem regra de CFOP (gargalo) ou
sem matriz (NAO_AUDITAVEL) fica parada; ao cadastrar a regra/matriz hoje, este
serviço re-aplica o De/Para CFOP nos itens existentes e re-roda o StAuditService.
"""
from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cfop_rules.infrastructure.repositories import CfopRegraRepository
from app.modules.fiscal.application.st_audit_service import StAuditService
from app.modules.fiscal.infrastructure.models import AuditoriaIcmsSt, Nota, NotaItem


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


class ReprocessService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.audit = StAuditService(session)

    async def reprocessar_pendentes(self, empresa_id: UUID | None = None) -> dict:
        regras = await CfopRegraRepository(self.session).as_map()
        alvo: dict[UUID, UUID] = {}     # nota_id -> empresa_id

        # 1) Notas TRAVADAS por falta de matriz: NAO_AUDITAVEL COM código de erro
        #    (ex.: ERRO_MVA_NAO_ENCONTRADA, ERRO_ENQUADRAMENTO_NAO_CADASTRADO). As
        #    sem código são TN por cadastro explícito (fora do motor POR DECISÃO)
        #    — legítimas, nunca mudam, não entram no reprocesso.
        q = select(AuditoriaIcmsSt.nota_id, AuditoriaIcmsSt.empresa_id).where(
            AuditoriaIcmsSt.status == "NAO_AUDITAVEL",
            or_(
                and_(
                    AuditoriaIcmsSt.codigo_erro.isnot(None),
                    AuditoriaIcmsSt.codigo_erro != "",
                ),
                # Legado pré-fallback de CEST: TN mudo (sem código). Re-audita
                # uma vez — o motor re-rotula em "TN por cadastro" (novo texto,
                # não volta a casar aqui) ou em ERRO_ENQUADRAMENTO_NAO_CADASTRADO.
                AuditoriaIcmsSt.observacao == "regime TN (fora do motor de ST)",
                # Legado pré-Parte 1: "modBCST=None fora do núcleo v1" sem código.
                # Re-audita uma vez — vira cálculo real (matriz decide a base),
                # entrada CST 60 OK, ou ERRO_MODBCST_NAO_SUPORTADO (pauta).
                AuditoriaIcmsSt.observacao.like("modBCST=%fora do núcleo v1"),
            ),
        )
        if empresa_id:
            q = q.where(AuditoriaIcmsSt.empresa_id == empresa_id)
        for nid, eid in (await self.session.execute(q.distinct())).all():
            alvo[nid] = eid

        # 2) Itens de ENTRADA cujo CFOP agora tem regra mas ainda não foi aplicada
        #    → re-aplica o De/Para (destrava o gargalo) e marca a nota para re-auditar.
        cfop_reclassificados = 0
        if regras:
            qi = (
                select(NotaItem, Nota.empresa_id)
                .join(Nota, Nota.id == NotaItem.nota_id)
                .where(Nota.fluxo == "entrada", NotaItem.cfop_original.in_(list(regras.keys())))
            )
            if empresa_id:
                qi = qi.where(Nota.empresa_id == empresa_id)
            for item, eid in (await self.session.execute(qi)).all():
                regra = regras.get(_digits(item.cfop_original))
                if regra and item.cfop != regra.cfop_destino:
                    item.cfop = regra.cfop_destino or item.cfop_original
                    item.tipo_sped = regra.tipo_item
                    cfop_reclassificados += 1
                    alvo[item.nota_id] = eid
            await self.session.flush()

        # 3) Re-audita as notas-alvo; conta as que saíram de NAO_AUDITAVEL.
        destravadas = 0
        for nid, eid in alvo.items():
            tinha_pendente = await self._tem_nao_auditavel(nid)
            await self.audit.auditar_nota(eid, nid)
            if tinha_pendente and not await self._tem_nao_auditavel(nid):
                destravadas += 1

        return {
            "notas_reprocessadas": len(alvo),
            "cfop_reclassificados": cfop_reclassificados,
            "notas_destravadas": destravadas,
        }

    async def _tem_nao_auditavel(self, nota_id: UUID) -> bool:
        return bool(
            await self.session.scalar(
                select(AuditoriaIcmsSt.id)
                .where(
                    AuditoriaIcmsSt.nota_id == nota_id,
                    AuditoriaIcmsSt.status == "NAO_AUDITAVEL",
                )
                .limit(1)
            )
        )
