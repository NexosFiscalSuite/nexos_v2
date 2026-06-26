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


# Templates de fábrica (modelos oficiais, criados sob demanda por empresa).
def _cols(*keys):
    return [{"tag": k} for k in keys]


_TEMPLATES = [
    {
        "nome": "Apuração de ICMS-ST", "fluxo": "entrada",
        "config": {
            "capa": _cols("chNFe", "dhEmi", "emit_CNPJ", "emit_xNome", "dest_CNPJ"),
            "itens": _cols("it_xProd", "it_NCM", "it_vProd", "it_vICMSST", "it_pMVAST", "it_vBCST"),
            "totais": True, "finalidade": True, "calculos": True,
        },
    },
    {
        "nome": "Conferência de Entradas", "fluxo": "entrada",
        "config": {
            "capa": _cols("chNFe", "serie", "dhEmi", "natOp"),
            "itens": _cols("it_cProd", "it_xProd", "it_NCM", "it_qCom", "it_vUnCom", "it_vProd"),
            "totais": True, "finalidade": False, "calculos": False,
        },
    },
]


class ReportingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _ensure_templates(self, tenant_id: UUID, empresa_id: UUID) -> None:
        """Cria os templates de fábrica que faltarem para a empresa (idempotente)."""
        existentes = set((await self.session.execute(
            select(RelatorioModelo.nome).where(
                RelatorioModelo.empresa_id == empresa_id, RelatorioModelo.sistema.is_(True))
        )).scalars().all())
        novos = [
            RelatorioModelo(
                id=uuid4(), tenant_id=tenant_id, empresa_id=empresa_id,
                nome=t["nome"], fluxo=t["fluxo"], config_json=_valida_config(t["config"]),
                sistema=True, created_by=None,
            )
            for t in _TEMPLATES if t["nome"] not in existentes
        ]
        if novos:
            self.session.add_all(novos)
            await self.session.flush()

    async def list_modelos(
        self, empresa_id: UUID, fluxo: str | None = None, tenant_id: UUID | None = None
    ) -> list[RelatorioModelo]:
        if tenant_id is not None:
            await self._ensure_templates(tenant_id, empresa_id)
        stmt = select(RelatorioModelo).where(RelatorioModelo.empresa_id == empresa_id)
        if fluxo:
            stmt = stmt.where(RelatorioModelo.fluxo == fluxo)
        # Templates de fábrica primeiro, depois os do usuário.
        res = await self.session.execute(
            stmt.order_by(RelatorioModelo.sistema.desc(), RelatorioModelo.fluxo, RelatorioModelo.nome)
        )
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
        if m.sistema:
            raise DomainError(
                "Template de fábrica não pode ser editado — duplique para personalizar.",
                code="template_sistema",
            )
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
        if modelo.sistema:
            raise DomainError(
                "Template de fábrica não pode ser excluído.", code="template_sistema"
            )
        await self.session.delete(modelo)

    async def duplicar_modelo(
        self, modelo_id: UUID, *, tenant_id: UUID, created_by: UUID, novo_nome: str | None = None
    ) -> RelatorioModelo:
        """Cria uma cópia EDITÁVEL (sistema=False) de um modelo — o caminho para
        personalizar um template de fábrica sem tocar no original."""
        origem = await self.get_modelo(modelo_id)
        if origem is None:
            raise NotFoundError("Modelo não encontrado.")
        base = (novo_nome or f"Cópia de {origem.nome}").strip()
        # Resolve colisão de nome (uq: empresa_id, nome, fluxo) com sufixo incremental.
        nome = base
        for i in range(2, 100):
            existe = await self.session.execute(
                select(RelatorioModelo.id).where(
                    RelatorioModelo.empresa_id == origem.empresa_id,
                    RelatorioModelo.nome == nome,
                    RelatorioModelo.fluxo == origem.fluxo,
                )
            )
            if existe.scalar_one_or_none() is None:
                break
            nome = f"{base} ({i})"
        copia = RelatorioModelo(
            id=uuid4(), tenant_id=tenant_id, empresa_id=origem.empresa_id,
            nome=nome, fluxo=origem.fluxo, config_json=dict(origem.config_json or {}),
            sistema=False, created_by=created_by,
        )
        self.session.add(copia)
        await self.session.flush()
        return copia

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
