"""Casos de uso das regras De/Para CFOP (sob RLS)."""
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.modules.cfop_rules.infrastructure.models import CfopRegra
from app.modules.cfop_rules.infrastructure.repositories import CfopRegraRepository, norm_cfop
from app.modules.fiscal.domain.cfop_sped import TIPOS_SPED

_CAMPOS = ("tipo_item", "cfop_destino", "usa_extensao", "extensao", "descricao")


class CfopRegraService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = CfopRegraRepository(session)

    async def list(self):
        return await self.repo.list()

    async def create(self, *, tenant_id: UUID, tipo_item: str, cfop_origem: str,
                     cfop_destino: str, usa_extensao: bool = False,
                     extensao: str | None = None, descricao: str | None = None) -> CfopRegra:
        if tipo_item not in TIPOS_SPED:
            raise DomainError(f"Tipo de item inválido: {tipo_item}.")
        co = norm_cfop(cfop_origem)
        cd = norm_cfop(cfop_destino) or co
        if len(co) != 4:
            raise DomainError("CFOP de origem deve ter 4 dígitos.")
        if await self.repo.by_origem(co):
            raise ConflictError(f"Já existe regra para o CFOP de origem {co}. Edite-a.")
        regra = CfopRegra(
            id=uuid4(), tenant_id=tenant_id, tipo_item=tipo_item,
            cfop_origem=co, cfop_destino=cd,
            usa_extensao=usa_extensao, extensao=(extensao or None) if usa_extensao else None,
            descricao=descricao,
        )
        self.repo.add(regra)
        await self.session.flush()
        return regra

    async def update(self, rid: UUID, fields: dict) -> CfopRegra:
        regra = await self.repo.by_id(rid)
        if regra is None:
            raise NotFoundError("Regra não encontrada.")
        if "tipo_item" in fields and fields["tipo_item"] and fields["tipo_item"] not in TIPOS_SPED:
            raise DomainError("Tipo de item inválido.")
        for k in _CAMPOS:
            if k in fields and fields[k] is not None:
                setattr(regra, k, norm_cfop(fields[k]) if k == "cfop_destino" else fields[k])
        if not regra.usa_extensao:
            regra.extensao = None
        await self.session.flush()
        return regra

    async def delete(self, rid: UUID) -> None:
        regra = await self.repo.by_id(rid)
        if regra is None:
            raise NotFoundError("Regra não encontrada.")
        await self.session.delete(regra)
