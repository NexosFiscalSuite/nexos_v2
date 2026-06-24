"""Casos de uso de contrapartes (sob RLS)."""
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.modules.contrapartes.infrastructure.models import (
    TIPO_CLIENTE,
    TIPO_FORNECEDOR,
    Contraparte,
)
from app.modules.contrapartes.infrastructure.repositories import ContraparteRepository
from app.shared.domain.value_objects import only_digits

_TIPOS = (TIPO_CLIENTE, TIPO_FORNECEDOR)
_CAMPOS = (
    "razao_social", "nome_fantasia", "situacao", "uf", "municipio", "atividade",
    "porte", "regime", "inscricao_estadual", "logradouro", "numero", "complemento",
    "bairro", "cep", "pais",
)


class ContraparteService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ContraparteRepository(session)

    async def list(self, empresa_id: UUID, tipo: str | None = None, search: str | None = None):
        return await self.repo.list(empresa_id, tipo, search)

    async def create(self, *, tenant_id: UUID, empresa_id: UUID, tipo: str, cnpj: str, **data) -> Contraparte:
        if tipo not in _TIPOS:
            raise DomainError(f"Tipo inválido: {tipo}.")
        cnpj_clean = only_digits(cnpj)
        if len(cnpj_clean) not in (11, 14):
            raise DomainError("CNPJ/CPF inválido.")
        if await self.repo.by_cnpj(empresa_id, tipo, cnpj_clean):
            raise ConflictError(f"{tipo.capitalize()} já cadastrado para esta empresa.")
        c = Contraparte(
            id=uuid4(), tenant_id=tenant_id, empresa_id=empresa_id, tipo=tipo, cnpj=cnpj_clean,
            origem=data.get("origem", "manual"),
            pendente_revisao=data.get("pendente_revisao", False),
            **{k: data.get(k) for k in _CAMPOS},
        )
        self.repo.add(c)
        await self.session.flush()
        return c

    async def update(self, cid: UUID, fields: dict) -> Contraparte:
        c = await self.repo.by_id(cid)
        if c is None:
            raise NotFoundError("Contraparte não encontrada.")
        for k in (*_CAMPOS, "pendente_revisao", "origem"):
            if k in fields and fields[k] is not None:
                setattr(c, k, fields[k])
        await self.session.flush()
        return c

    async def upsert_from_xml(self, *, tenant_id: UUID, empresa_id: UUID, tipo: str,
                              cnpj: str, nome: str, uf: str) -> None:
        """Cria a contraparte a partir dos dados do XML (sem chamar API externa).
        Não sobrescreve se já existir. Usado pela importação."""
        cnpj_clean = only_digits(cnpj)
        if len(cnpj_clean) not in (11, 14):
            return
        if await self.repo.by_cnpj(empresa_id, tipo, cnpj_clean):
            return
        self.repo.add(Contraparte(
            id=uuid4(), tenant_id=tenant_id, empresa_id=empresa_id, tipo=tipo, cnpj=cnpj_clean,
            razao_social=nome or "", uf=uf or "", origem="xml", pendente_revisao=True,
        ))
