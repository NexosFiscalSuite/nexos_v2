"""Casos de uso de reporting: CRUD de modelos + carga de notas (com itens)."""
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.modules.fiscal.infrastructure.models import Nota, NotaItem
from app.modules.reporting.domain.tags import TAGS
from app.modules.reporting.infrastructure.models import RelatorioModelo


def _norm_cols(cols: list) -> list:
    """Normaliza colunas: tag de dados {tag,label} ou auditoria {audit,label}."""
    out = []
    for c in cols or []:
        if c.get("audit"):
            out.append({"audit": True, "label": (c.get("label") or "Auditoria")})
        elif c.get("tag") in TAGS:
            out.append({"tag": c["tag"], "label": c.get("label") or TAGS[c["tag"]]["label"]})
        else:
            raise DomainError(f"Tag inválida: {c.get('tag')}.")
    return out


def _valida_config(config: dict) -> dict:
    capa = _norm_cols(config.get("capa"))
    itens = _norm_cols(config.get("itens"))
    # ao menos uma coluna de DADOS (auditoria sozinha não gera relatório útil)
    if not any(not c.get("audit") for c in [*capa, *itens]):
        raise DomainError("Selecione ao menos uma coluna de dados (capa ou itens).")
    return {
        "capa": capa,
        "itens": itens,
        "totais": bool(config.get("totais", False)),
        "finalidade": bool(config.get("finalidade", True)),
        "calculos": bool(config.get("calculos", True)),
        "auditoria": [str(n).strip() for n in (config.get("auditoria") or []) if str(n).strip()],
    }


class ReportingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_modelos(self, empresa_id: UUID, fluxo: str | None = None) -> list[RelatorioModelo]:
        stmt = select(RelatorioModelo).where(RelatorioModelo.empresa_id == empresa_id)
        if fluxo:
            stmt = stmt.where(RelatorioModelo.fluxo == fluxo)
        res = await self.session.execute(stmt.order_by(RelatorioModelo.fluxo, RelatorioModelo.nome))
        return list(res.scalars().all())

    async def get_modelo(self, modelo_id: UUID) -> RelatorioModelo | None:
        return await self.session.get(RelatorioModelo, modelo_id)

    async def create_modelo(self, *, tenant_id: UUID, empresa_id: UUID, nome: str,
                            fluxo: str, config: dict, created_by: UUID) -> RelatorioModelo:
        cfg = _valida_config(config)
        dup = await self.session.execute(
            select(RelatorioModelo).where(
                RelatorioModelo.empresa_id == empresa_id,
                RelatorioModelo.nome == nome, RelatorioModelo.fluxo == fluxo,
            )
        )
        if dup.scalar_one_or_none():
            raise ConflictError("Já existe um modelo com esse nome para este fluxo.")
        modelo = RelatorioModelo(
            id=uuid4(), tenant_id=tenant_id, empresa_id=empresa_id,
            nome=nome.strip(), fluxo=fluxo, config_json=cfg, created_by=created_by,
        )
        self.session.add(modelo)
        await self.session.flush()
        return modelo

    async def update_modelo(self, modelo_id: UUID, *, nome: str | None, config: dict | None) -> RelatorioModelo:
        m = await self.get_modelo(modelo_id)
        if m is None:
            raise NotFoundError("Modelo não encontrado.")
        if nome:
            m.nome = nome.strip()
        if config is not None:
            m.config_json = _valida_config(config)
        await self.session.flush()
        return m

    async def delete_modelo(self, modelo_id: UUID) -> None:
        modelo = await self.session.get(RelatorioModelo, modelo_id)
        if modelo is None:
            raise NotFoundError("Modelo não encontrado.")
        await self.session.delete(modelo)

    async def load_notas_com_tipos(self, empresa_id: UUID, fluxo: str, ano: str | None, mes: str | None):
        """Retorna [(Nota, {numero_item: tipo_sped})] das notas ativas do período."""
        where = [Nota.empresa_id == empresa_id, Nota.fluxo == fluxo, Nota.status == "ativa"]
        if ano:
            where.append(Nota.ano == ano)
        if mes:
            where.append(Nota.mes == mes)
        notas = list((await self.session.execute(
            select(Nota).where(*where).order_by(Nota.numero)
        )).scalars().all())
        if not notas:
            return []
        ids = [n.id for n in notas]
        itens = (await self.session.execute(
            select(NotaItem.nota_id, NotaItem.numero_item, NotaItem.tipo_sped)
            .where(NotaItem.nota_id.in_(ids))
        )).all()
        tipos_por_nota: dict = {}
        for nota_id, numero_item, tipo_sped in itens:
            tipos_por_nota.setdefault(nota_id, {})[numero_item] = tipo_sped
        return [(n, tipos_por_nota.get(n.id, {})) for n in notas]
