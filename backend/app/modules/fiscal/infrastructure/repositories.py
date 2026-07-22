"""Repositório de notas/itens/eventos."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import BigInteger, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.fiscal.infrastructure.models import (
    NfeCteVinculo,
    Nota,
    NotaEvento,
    NotaItem,
)

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
        q: str | None = None,
        sort: str | None = None,
        order: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        where = [Nota.empresa_id == empresa_id]
        if q and q.strip():
            # Busca livre: nome do emitente/destinatário (parcial, sem caixa) e,
            # quando o termo tem dígitos, número da NF, chave de acesso e CNPJs.
            termo = q.strip()
            like = f"%{termo}%"
            conds = [Nota.nome_emit.ilike(like), Nota.nome_dest.ilike(like)]
            digitos = "".join(ch for ch in termo if ch.isdigit())
            if digitos:
                dlike = f"%{digitos}%"
                conds += [
                    Nota.numero.like(dlike),
                    Nota.chave_acesso.like(dlike),
                    Nota.cnpj_emit.like(dlike),
                    Nota.cnpj_dest.like(dlike),
                ]
            where.append(or_(*conds))
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
        notas = list(res.scalars().all())
        # Marca quais NF-e têm CT-e vinculado (badge 🚚 na listagem — ADR-0001).
        chaves = [n.chave_acesso for n in notas if n.tipo in ("NFe", "NFCe")]
        com_cte: set[str] = set()
        if chaves:
            vinc = await self.session.execute(
                select(NfeCteVinculo.chave_nfe)
                .where(NfeCteVinculo.empresa_id == empresa_id, NfeCteVinculo.chave_nfe.in_(chaves))
                .distinct()
            )
            com_cte = {c for (c,) in vinc.all()}
        for n in notas:
            n.tem_cte = n.chave_acesso in com_cte
        return {"total": total or 0, "page": page, "page_size": page_size, "notas": notas}

    async def vinculos_da_nota(self, nota: Nota) -> dict:
        """Detalhe (ADR-0001): se NF-e → CT-e vinculados (transportador + frete);
        se CT-e → NF-e transportadas. Cada vínculo traz o nota_id (se importado)
        para o front abrir o documento."""
        emp = nota.empresa_id
        if nota.tipo in ("NFe", "NFCe"):
            cte = aliased(Nota)
            rows = await self.session.execute(
                select(
                    NfeCteVinculo.chave_cte, NfeCteVinculo.vtprest,
                    cte.id, cte.nome_emit, cte.numero,
                )
                .outerjoin(
                    cte, (cte.chave_acesso == NfeCteVinculo.chave_cte) & (cte.empresa_id == emp)
                )
                .where(NfeCteVinculo.empresa_id == emp, NfeCteVinculo.chave_nfe == nota.chave_acesso)
            )
            ctes = [
                {"chave_cte": ch, "vtprest": vt, "nota_id": nid,
                 "transportador": nm, "numero": num}
                for ch, vt, nid, nm, num in rows.all()
            ]
            return {"ctes_vinculados": ctes, "nfes_transportadas": []}
        if nota.tipo == "CTe":
            nfe = aliased(Nota)
            rows = await self.session.execute(
                select(NfeCteVinculo.chave_nfe, nfe.id, nfe.nome_emit, nfe.numero)
                .outerjoin(
                    nfe, (nfe.chave_acesso == NfeCteVinculo.chave_nfe) & (nfe.empresa_id == emp)
                )
                .where(NfeCteVinculo.empresa_id == emp, NfeCteVinculo.chave_cte == nota.chave_acesso)
            )
            nfes = [
                {"chave_nfe": ch, "nota_id": nid, "fornecedor": nm, "numero": num}
                for ch, nid, nm, num in rows.all()
            ]
            return {"ctes_vinculados": [], "nfes_transportadas": nfes}
        return {"ctes_vinculados": [], "nfes_transportadas": []}

    def add(self, nota: Nota) -> None:
        self.session.add(nota)

    def add_item(self, item: NotaItem) -> None:
        self.session.add(item)

    def add_evento(self, evento: NotaEvento) -> None:
        self.session.add(evento)

    def add_vinculo_cte(self, vinculo: NfeCteVinculo) -> None:
        self.session.add(vinculo)

    async def ctes_da_nfe(self, empresa_id: UUID, chave_nfe: str) -> list[NfeCteVinculo]:
        """Vínculos de CT-e de uma NF-e (para a agregação de frete do ADR-0001)."""
        res = await self.session.execute(
            select(NfeCteVinculo).where(
                NfeCteVinculo.empresa_id == empresa_id,
                NfeCteVinculo.chave_nfe == chave_nfe,
            )
        )
        return list(res.scalars().all())
