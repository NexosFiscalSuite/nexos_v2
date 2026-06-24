"""Repositório de notas/itens/eventos."""
from uuid import UUID

from sqlalchemy import BigInteger, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.infrastructure.models import Nota, NotaEvento, NotaItem

# Número como inteiro, robusto a não-dígitos/vazios (ordenação correta).
_NUMERO_INT = cast(
    func.nullif(func.regexp_replace(Nota.numero, "[^0-9]", "", "g"), ""), BigInteger
)
_SORT_COLS = {
    "numero": _NUMERO_INT,
    "serie": Nota.serie,
    "modelo": Nota.modelo,
    "fluxo": Nota.fluxo,
    "valor": Nota.valor_total,
    "valor_total": Nota.valor_total,
    "data_emissao": Nota.data_emissao,
    "emissao": Nota.data_emissao,
    "status": Nota.status,
}


class NotaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_chave(self, empresa_id: UUID, chave: str) -> Nota | None:
        res = await self.session.execute(
            select(Nota).where(Nota.empresa_id == empresa_id, Nota.chave_acesso == chave)
        )
        return res.scalar_one_or_none()

    async def by_id(self, nota_id: UUID) -> Nota | None:
        return await self.session.get(Nota, nota_id)

    async def by_ids(self, empresa_id: UUID, ids: list[UUID]) -> list[Nota]:
        if not ids:
            return []
        res = await self.session.execute(
            select(Nota).where(Nota.empresa_id == empresa_id, Nota.id.in_(ids))
        )
        return list(res.scalars().all())

    async def items_for(self, nota_id: UUID) -> list[NotaItem]:
        res = await self.session.execute(
            select(NotaItem).where(NotaItem.nota_id == nota_id).order_by(NotaItem.numero_item)
        )
        return list(res.scalars().all())

    async def list(
        self,
        empresa_id: UUID,
        *,
        fluxo: str | None = None,
        ano: str | None = None,
        mes: str | None = None,
        status: str | None = None,
        tipo: str | None = None,
        tipo_excluir: str | None = None,
        sort: str | None = None,
        order: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        where = [Nota.empresa_id == empresa_id]
        if fluxo:
            where.append(Nota.fluxo == fluxo)
        if ano:
            where.append(Nota.ano == ano)
        if mes:
            where.append(Nota.mes == mes)
        if status in ("ativa", "cancelada"):
            where.append(Nota.status == status)
        if tipo:  # ex.: 'NFSe' para a aba Serviço (Tomador)
            where.append(Nota.tipo == tipo)
        if tipo_excluir:  # ex.: excluir 'NFSe' da aba Entrada
            where.append(Nota.tipo != tipo_excluir)

        total = await self.session.scalar(select(func.count()).select_from(Nota).where(*where))
        page = max(1, page)
        page_size = max(1, min(200, page_size))

        # Ordenação: whitelist; sem sort => padrão (emissão desc). 'contraparte'
        # depende do fluxo (dest na saída, emit no resto).
        if sort == "contraparte":
            col = Nota.nome_dest if fluxo == "saida" else Nota.nome_emit
        else:
            col = _SORT_COLS.get(sort)
        if col is not None:
            order_by = col.desc() if (order or "").lower() == "desc" else col.asc()
        else:
            order_by = Nota.data_emissao.desc()

        res = await self.session.execute(
            select(Nota)
            .where(*where)
            .order_by(order_by)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return {
            "total": total or 0,
            "page": page,
            "page_size": page_size,
            "notas": list(res.scalars().all()),
        }

    def add(self, nota: Nota) -> None:
        self.session.add(nota)

    def add_item(self, item: NotaItem) -> None:
        self.session.add(item)

    def add_evento(self, evento: NotaEvento) -> None:
        self.session.add(evento)
