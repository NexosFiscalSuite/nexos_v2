"""Consulta de divergências de ICMS-ST (REL_Divergencia_ST do Vault).

Lê a `auditoria_icms_st` (aproveitando o índice parcial WHERE status='DIVERGENTE')
e cruza com a nota para trazer fornecedor, UFs e período. Ordena pelo maior
"rombo" fiscal (|divergência|).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.infrastructure.models import AuditoriaIcmsSt, Nota
from app.shared.domain.value_objects import only_digits

_STATUS_DIVERGENTE = "DIVERGENTE"


async def listar_divergencias(
    session: AsyncSession,
    *,
    empresa_id: UUID,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    cnpj: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    a, n = AuditoriaIcmsSt, Nota
    where = [a.empresa_id == empresa_id, a.status == _STATUS_DIVERGENTE]
    # data_emissao é 'YYYY-MM-DD' (ISO): comparação lexicográfica = cronológica.
    if data_inicio:
        where.append(n.data_emissao >= data_inicio)
    if data_fim:
        where.append(n.data_emissao <= data_fim)
    if cnpj:
        where.append(n.cnpj_emit == only_digits(cnpj))

    page = max(1, page)
    page_size = max(1, min(200, page_size))

    total = await session.scalar(
        select(func.count()).select_from(a).join(n, a.nota_id == n.id).where(*where)
    )
    res = await session.execute(
        select(a, n)
        .join(n, a.nota_id == n.id)
        .where(*where)
        .order_by(func.abs(a.vicms_st_divergencia).desc())   # maior rombo primeiro
        .limit(page_size)
        .offset((page - 1) * page_size)
    )

    itens = [
        {
            "chave_acesso": a_row.chave_acesso,
            "numero_item": a_row.numero_item,
            "numero_nota": n_row.numero,
            "fornecedor": n_row.nome_emit,
            "cnpj_emit": n_row.cnpj_emit,
            "uf_origem": n_row.uf_emit,
            "uf_destino": n_row.uf_dest,
            "data_emissao": n_row.data_emissao,
            "cst_csosn": a_row.cst_csosn,
            "mod_bc_st": a_row.mod_bc_st,
            "pmva_xml": a_row.pmva_xml,
            "pmva_calculada": a_row.pmva_calculada,
            "vbc_st_xml": a_row.vbc_st_xml,
            "vbc_st_calculado": a_row.vbc_st_calculado,
            "vicms_st_xml": a_row.vicms_st_xml,
            "vicms_st_calculado": a_row.vicms_st_calculado,
            "divergencia": a_row.vicms_st_divergencia,   # o "rombo" (XML − calculado)
            "vfcp_st_xml": a_row.vfcp_st_xml,
            "vfcp_st_calculado": a_row.vfcp_st_calculado,
            "codigo_erro": a_row.codigo_erro,
            "memoria": a_row.memoria,
        }
        for a_row, n_row in res.all()
    ]
    return {"total": total or 0, "page": page, "page_size": page_size, "itens": itens}
