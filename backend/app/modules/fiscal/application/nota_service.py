"""Casos de uso de consulta/edição de notas (sob RLS).

Edita só os campos que faziam sentido editar no V1:
  - cabeçalho: data_entrada, competencia, iss_retido, tem_correcao
  - item: cfop, tipo_sped (cfop_original é SEMPRE preservado)
  - cancelamento manual
"""
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.fiscal.domain.cfop_sped import sugerir_tipo_sped
from app.modules.fiscal.infrastructure.models import Nota, NotaItem
from app.modules.fiscal.infrastructure.repositories import NotaRepository

_CAMPOS_NOTA = ("data_entrada", "competencia", "iss_retido", "tem_correcao", "tipo_nota")


class NotaService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = NotaRepository(session)

    async def get_detail(self, nota_id: UUID) -> tuple[Nota, list[NotaItem]]:
        nota = await self.repo.by_id(nota_id)
        if nota is None:
            raise NotFoundError("Nota não encontrada.")
        itens = await self.repo.items_for(nota_id)
        return nota, itens

    async def update_nota(self, nota_id: UUID, fields: dict) -> tuple[Nota, list[NotaItem]]:
        nota = await self.repo.by_id(nota_id)
        if nota is None:
            raise NotFoundError("Nota não encontrada.")
        for k in _CAMPOS_NOTA:
            if k in fields:
                setattr(nota, k, fields[k])
        await self.session.flush()
        return nota, await self.repo.items_for(nota_id)

    async def update_item(self, item_id: UUID, fields: dict) -> NotaItem:
        item = await self.session.get(NotaItem, item_id)
        if item is None:
            raise NotFoundError("Item não encontrado.")
        if fields.get("cfop") is not None:
            item.cfop = fields["cfop"]
        if fields.get("tipo_sped") is not None:
            item.tipo_sped = fields["tipo_sped"]
        await self.session.flush()
        return item

    async def cancelar(self, nota_id: UUID) -> tuple[Nota, list[NotaItem]]:
        nota = await self.repo.by_id(nota_id)
        if nota is None:
            raise NotFoundError("Nota não encontrada.")
        nota.status = "cancelada"
        nota.cancelada_em = datetime.now(UTC).isoformat()
        await self.session.flush()
        return nota, await self.repo.items_for(nota_id)

    # ── Operações em lote ──────────────────────────────────────────────────
    async def cancelar_lote(self, empresa_id: UUID, ids: list[UUID]) -> int:
        notas = await self.repo.by_ids(empresa_id, ids)
        agora = datetime.now(UTC).isoformat()
        for n in notas:
            n.status = "cancelada"
            n.cancelada_em = agora
        await self.session.flush()
        return len(notas)

    async def reativar_lote(self, empresa_id: UUID, ids: list[UUID]) -> int:
        """'Autorizar' no V2 = reverter um cancelamento local (volta para ativa)."""
        notas = await self.repo.by_ids(empresa_id, ids)
        for n in notas:
            n.status = "ativa"
            n.cancelada_em = None
        await self.session.flush()
        return len(notas)

    async def alterar_cfop_lote(self, empresa_id: UUID, ids: list[UUID], cfop: str) -> int:
        """Aplica um CFOP a todos os itens das notas selecionadas. cfop_original
        é preservado (nunca sobrescrito). Re-sugere o Tipo SPED pelo novo CFOP."""
        notas = await self.repo.by_ids(empresa_id, ids)
        nota_ids = [n.id for n in notas]
        if not nota_ids:
            return 0
        await self.session.execute(
            update(NotaItem)
            .where(NotaItem.nota_id.in_(nota_ids))
            .values(cfop=cfop, tipo_sped=sugerir_tipo_sped(cfop))
        )
        await self.session.flush()
        return len(nota_ids)

    async def tipo_nota_lote(self, empresa_id: UUID, ids: list[UUID], tipo_nota: str) -> int:
        """Classifica em lote o 'Tipo da Nota' (entradas)."""
        notas = await self.repo.by_ids(empresa_id, ids)
        for n in notas:
            n.tipo_nota = tipo_nota
        await self.session.flush()
        return len(notas)

    async def storage_keys(self, empresa_id: UUID, ids: list[UUID]) -> list[tuple[str, str]]:
        """[(chave_acesso, storage_key)] das notas com XML, para zipar."""
        notas = await self.repo.by_ids(empresa_id, ids)
        return [(n.chave_acesso, n.storage_key) for n in notas if n.storage_key]
