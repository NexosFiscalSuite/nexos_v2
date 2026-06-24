"""Detecção de quebra de sequência + registro de ciência (portado do V1).

Considera apenas notas EMITIDAS pela empresa (fluxo saída/serviço) e ativas.
Agrupa por (modelo, série), acha lacunas de numeração e exclui faixas que já
receberam ciência.
"""
import re
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, DomainError
from app.core.security import verify_password
from app.modules.compliance.infrastructure.models import QuebraCiencia
from app.modules.fiscal.infrastructure.models import Nota
from app.modules.identity.infrastructure.models import User

_FLUXOS_EMITIDOS = ("saida", "servico")
_CLASSIFICACOES = ("cancelada", "inutilizada", "outra")


def _num_int(valor) -> int | None:
    d = re.sub(r"\D", "", str(valor or ""))
    return int(d) if d else None


class ComplianceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def detectar_quebras(
        self, empresa_id: UUID, ano: str | None = None, mes: str | None = None
    ) -> list[dict]:
        where = [
            Nota.empresa_id == empresa_id,
            Nota.fluxo.in_(_FLUXOS_EMITIDOS),
            Nota.status == "ativa",
        ]
        if ano:
            where.append(Nota.ano == ano)
        if mes:
            where.append(Nota.mes == mes)

        rows = (
            await self.session.execute(select(Nota.modelo, Nota.serie, Nota.numero).where(*where))
        ).all()

        # faixas já reconhecidas (excluir)
        cienc = (
            await self.session.execute(
                select(
                    QuebraCiencia.modelo,
                    QuebraCiencia.serie,
                    QuebraCiencia.num_inicio,
                    QuebraCiencia.num_fim,
                ).where(QuebraCiencia.empresa_id == empresa_id)
            )
        ).all()
        resolvidas = {(c.modelo, c.serie, c.num_inicio, c.num_fim) for c in cienc}

        grupos: dict[tuple[str, str], set[int]] = {}
        for modelo, serie, numero in rows:
            n = _num_int(numero)
            if n is None:
                continue
            grupos.setdefault((modelo or "", serie or ""), set()).add(n)

        quebras = []
        for (modelo, serie), numeros in grupos.items():
            ordenados = sorted(numeros)
            for i in range(1, len(ordenados)):
                ant, atual = ordenados[i - 1], ordenados[i]
                if atual > ant + 1:
                    ini, fim = ant + 1, atual - 1
                    if (modelo, serie, ini, fim) in resolvidas:
                        continue
                    quebras.append(
                        {
                            "modelo": modelo,
                            "serie": serie,
                            "num_inicio": ini,
                            "num_fim": fim,
                            "qtd": fim - ini + 1,
                        }
                    )
        quebras.sort(key=lambda q: (q["modelo"], q["serie"], q["num_inicio"]))
        return quebras

    async def listar_ciencias(
        self, empresa_id: UUID, classificacao: str | None = None
    ) -> list[QuebraCiencia]:
        stmt = select(QuebraCiencia).where(QuebraCiencia.empresa_id == empresa_id)
        if classificacao:
            stmt = stmt.where(QuebraCiencia.classificacao == classificacao)
        res = await self.session.execute(
            stmt.order_by(QuebraCiencia.modelo, QuebraCiencia.serie, QuebraCiencia.num_inicio)
        )
        return list(res.scalars().all())

    async def _verificar_auditor(self, email: str, senha: str) -> User:
        """Valida e-mail+senha de um usuário do tenant (RLS já restringe ao tenant)."""
        res = await self.session.execute(select(User).where(User.email == email.strip().lower()))
        user = res.scalar_one_or_none()
        if user is None or not user.is_active or not verify_password(user.password_hash, senha):
            raise AuthenticationError("Credenciais do auditor inválidas.", code="auditor_invalid")
        return user

    async def registrar_ciencia_lote(
        self,
        *,
        tenant_id: UUID,
        empresa_id: UUID,
        faixas: list[dict],
        classificacao: str,
        justificativa: str | None,
        auditor_email: str,
        auditor_senha: str,
        registrado_por: UUID,
    ) -> int:
        """Dá ciência a várias faixas de uma vez, exigindo login de um auditor.
        Cada faixa: {modelo, serie, num_inicio, num_fim}."""
        if classificacao not in _CLASSIFICACOES:
            raise DomainError(f"Classificação inválida: {classificacao}.")
        auditor = await self._verificar_auditor(auditor_email, auditor_senha)
        criadas = 0
        for f in faixas:
            ini, fim = int(f["num_inicio"]), int(f["num_fim"])
            if fim < ini:
                continue
            self.session.add(QuebraCiencia(
                id=uuid4(), tenant_id=tenant_id, empresa_id=empresa_id,
                modelo=f.get("modelo", ""), serie=f.get("serie", ""),
                num_inicio=ini, num_fim=fim, classificacao=classificacao,
                justificativa=justificativa, ciente_nome=auditor.full_name,
                registrado_por=registrado_por,
            ))
            criadas += 1
        await self.session.flush()
        return criadas

    async def registrar_ciencia(
        self,
        *,
        tenant_id: UUID,
        empresa_id: UUID,
        modelo: str,
        serie: str,
        num_inicio: int,
        num_fim: int,
        classificacao: str,
        justificativa: str | None,
        ciente_nome: str | None,
        registrado_por: UUID,
    ) -> QuebraCiencia:
        if classificacao not in _CLASSIFICACOES:
            raise DomainError(f"Classificação inválida: {classificacao}.")
        if num_fim < num_inicio:
            raise DomainError("Faixa inválida (fim < início).")

        ciencia = QuebraCiencia(
            id=uuid4(),
            tenant_id=tenant_id,
            empresa_id=empresa_id,
            modelo=modelo,
            serie=serie,
            num_inicio=num_inicio,
            num_fim=num_fim,
            classificacao=classificacao,
            justificativa=justificativa,
            ciente_nome=ciente_nome,
            registrado_por=registrado_por,
        )
        self.session.add(ciencia)
        await self.session.flush()
        return ciencia
