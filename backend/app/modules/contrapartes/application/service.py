"""Casos de uso de contrapartes (sob RLS)."""
import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.modules.contrapartes.infrastructure.models import (
    TIPO_CLIENTE,
    TIPO_FORNECEDOR,
    Contraparte,
)
from app.modules.contrapartes.infrastructure.repositories import ContraparteRepository
from app.shared.cnpj_lookup import consultar_opencnpj
from app.shared.domain.value_objects import only_digits

_TIPOS = (TIPO_CLIENTE, TIPO_FORNECEDOR)
# Regimes em que conhecemos o CRT com certeza (Simples=1, MEI=4) → não fica pendente.
_REGIMES_SIMPLES = ("Simples Nacional", "MEI")


def classificar_optante(res: dict) -> tuple[str | None, bool]:
    """Resultado da consulta optante → (regime, pendente_revisao).

    Função pura (sem I/O), núcleo da regra de negócio:
      - lookup falhou → (None, True): não dá para confirmar, fica pendente.
      - Simples/MEI → (regime, False): CRT conhecido, resolvido.
      - qualquer outro → (regime ou "Normal", True): optante não distingue
        Presumido de Real, então vira ponto de observação.
    """
    if not res.get("ok"):
        return None, True
    regime = (res.get("dados") or {}).get("regime") or "Normal"
    return regime, regime not in _REGIMES_SIMPLES
_CAMPOS = (
    "razao_social", "nome_fantasia", "situacao", "uf", "municipio", "atividade",
    "cnae", "porte", "regime", "inscricao_estadual", "logradouro", "numero",
    "complemento", "bairro", "cep", "pais",
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

    async def enriquecer_optante(
        self, empresa_id: UUID, consultar: Callable[[str, str], dict] = consultar_opencnpj
    ) -> dict:
        """Consulta o regime (optante) das contrapartes sem regime e atualiza o
        cadastro. Roda como etapa separada pós-import (worker), não inline.

        Regra de negócio:
          - Simples Nacional / MEI → regime preenchido, `pendente_revisao=False`
            (CRT conhecido: 1 ou 4).
          - Qualquer outro → regime "Normal" e `pendente_revisao=True`: a consulta
            optante NÃO distingue Lucro Presumido de Real, então fica como ponto
            de observação para conferência manual.
          - Falha no lookup (API fora/CNPJ não encontrado) → mantém pendente.
          - CPF (11 dígitos) não tem optante → ignorado.

        Dedupe por CNPJ (um lookup por CNPJ único, aplicado a cliente+fornecedor).
        Tolerante a falha: nunca levanta — devolve um resumo.
        """
        candidatas = await self.repo.sem_regime(empresa_id)
        por_cnpj: dict[str, list[Contraparte]] = {}
        for c in candidatas:
            cnpj = only_digits(c.cnpj)
            if len(cnpj) == 14:  # CPF não é consultável no optante
                por_cnpj.setdefault(cnpj, []).append(c)

        resumo = {"consultados": 0, "simples": 0, "normal_pendente": 0, "falhas": 0}
        agora = datetime.now(UTC).isoformat()
        for cnpj, grupo in por_cnpj.items():
            # urllib é bloqueante: offload para thread mantém o event loop livre.
            res = await asyncio.to_thread(consultar, cnpj, "contraparte")
            resumo["consultados"] += 1
            regime, pendente = classificar_optante(res)
            for c in grupo:
                c.last_lookup_at = agora
            if regime is None:
                resumo["falhas"] += 1
                continue  # mantém pendente_revisao=True: não dá para confirmar
            for c in grupo:
                c.regime = regime
                c.pendente_revisao = pendente
                c.origem = "opencnpj"
            resumo["normal_pendente" if pendente else "simples"] += len(grupo)
        await self.session.flush()
        return resumo
