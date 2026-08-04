"""Revisão das propostas da auto-alimentação: aprovar aplica na matriz,
rejeitar veta (e suprime a re-proposta idêntica — regra do propor).

A aplicação reusa o registry das matrizes (modelo + schema + normalização do
bulk/CRUD): o payload é validado pelo MESMO caminho da digitação manual, e a
regra de vigência do ADR-0002 (sem sobreposição) vale igual — proposta que
conflita NÃO entra e explica o porquê.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.modules.fiscal.api.matrizes_bulk import MATRIZES
from app.modules.fiscal.infrastructure.propostas_models import (
    ACAO_ATUALIZAR,
    ACAO_ENCERRAR_VIGENCIA,
    ACAO_INSERIR,
    ACAO_NOVA_VIGENCIA,
    STATUS_APROVADA,
    STATUS_PENDENTE,
    STATUS_REJEITADA,
    MatrizProposta,
)
from app.modules.fiscal.infrastructure.vigencia import sobreposicao_existente


class PropostasService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _pendente(self, proposta_id: int) -> MatrizProposta:
        p = await self.session.get(MatrizProposta, proposta_id)
        if p is None:
            raise NotFoundError("Proposta não encontrada.")
        if p.status != STATUS_PENDENTE:
            raise ConflictError(f"Proposta já revisada (status {p.status}).")
        return p

    async def aprovar(self, proposta_id: int, *, revisor: str) -> MatrizProposta:
        p = await self._pendente(proposta_id)
        await self._aplicar(p)
        self._marcar(p, STATUS_APROVADA, revisor)
        await self.session.flush()
        return p

    async def rejeitar(
        self, proposta_id: int, *, revisor: str, motivo: str | None = None
    ) -> MatrizProposta:
        p = await self._pendente(proposta_id)
        self._marcar(p, STATUS_REJEITADA, revisor)
        p.motivo_rejeicao = (motivo or "").strip()[:300] or None
        await self.session.flush()
        return p

    async def aprovar_lote(
        self, *, revisor: str, tipo: str | None = None, uf: str | None = None,
        ids: list[int] | None = None,
    ) -> dict:
        """Aprova as pendentes do filtro; conflito de UMA não derruba o lote —
        vira relatório (id + motivo), como no import de planilha."""
        stmt = select(MatrizProposta).where(MatrizProposta.status == STATUS_PENDENTE)
        if tipo:
            stmt = stmt.where(MatrizProposta.tipo_matriz == tipo)
        if ids:
            stmt = stmt.where(MatrizProposta.id.in_(ids))
        if uf:
            # chave_resumo começa com a UF ("MG · …") — filtro portátil.
            stmt = stmt.where(MatrizProposta.chave_resumo.like(f"{uf.upper()} ·%"))
        pendentes = (await self.session.execute(stmt.order_by(MatrizProposta.id))).scalars().all()

        aprovadas, falhas = 0, []
        for p in pendentes:
            try:
                await self._aplicar(p)
            except DomainError as e:
                falhas.append({"id": p.id, "chave": p.chave_resumo, "erro": str(e)})
                continue
            self._marcar(p, STATUS_APROVADA, revisor)
            aprovadas += 1
        await self.session.flush()
        return {"aprovadas": aprovadas, "falhas": falhas}

    # ------------------------------------------------------------------ #
    def _marcar(self, p: MatrizProposta, status: str, revisor: str) -> None:
        p.status = status
        p.revisado_por = revisor
        p.revisado_em = datetime.now(UTC)

    async def _aplicar(self, p: MatrizProposta) -> None:
        spec = MATRIZES.get(p.tipo_matriz)
        if spec is None:
            raise ConflictError(f"Tipo de matriz desconhecido: {p.tipo_matriz}.")
        dados = spec.normalizar(spec.schema(**p.payload))
        modelo = spec.modelo

        if p.acao == ACAO_INSERIR:
            conflito = await sobreposicao_existente(self.session, modelo, dados)
            if conflito is not None:
                raise ConflictError(
                    f"Vigência sobrepõe a linha #{conflito.id} da matriz — "
                    "confira a linha existente e rejeite a proposta se ela já estiver coberta."
                )
            self.session.add(modelo(**dados))
            return

        linha = (
            await self.session.get(modelo, p.linha_atual_id)
            if p.linha_atual_id else None
        )
        if linha is None:
            raise ConflictError("A linha alvo não existe mais — rejeite a proposta.")

        if p.acao == ACAO_ATUALIZAR:
            for campo, valor in dados.items():
                setattr(linha, campo, valor)
        elif p.acao == ACAO_NOVA_VIGENCIA:
            fim_original = linha.data_fim_vigencia
            linha.data_fim_vigencia = dados["data_inicio_vigencia"] - timedelta(days=1)
            conflito = await sobreposicao_existente(
                self.session, modelo, dados, excluir_id=linha.id
            )
            if conflito is not None:
                linha.data_fim_vigencia = fim_original
                raise ConflictError(
                    f"Vigência sobrepõe a linha #{conflito.id} da matriz — resolva antes de aprovar."
                )
            self.session.add(modelo(**dados))
        elif p.acao == ACAO_ENCERRAR_VIGENCIA:
            linha.data_fim_vigencia = dados.get("data_fim_vigencia") or datetime.now(
                UTC
            ).date()
        else:
            raise ConflictError(f"Ação desconhecida: {p.acao}.")
