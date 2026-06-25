"""Tasks Celery de auto-alimentação fiscal (agendadas no beat).

Padrão: o I/O da fonte (fetch+parse) roda FORA da transação; só a persistência
abre a sessão global. Cada task tem seu próprio event loop (asyncio.run), como
as demais workers do projeto.
"""
import asyncio
import logging
from datetime import date

from app.core.celery_app import celery_app
from app.core.worker_db import worker_global_session
from app.modules.fiscal.crawlers.confaz_cest import ConfazCestExtractor
from app.modules.fiscal.crawlers.upsert import upsert_enquadramento

logger = logging.getLogger(__name__)


@celery_app.task(name="fiscal.sync_cest_confaz", bind=True, max_retries=3)
def sync_cest_confaz(self, uf: str = "MG"):
    """Baixa a relação NCM×CEST do CONFAZ e faz upsert na matriz de enquadramento
    da UF do nicho. Reagenda (retry exponencial) se a fonte estiver fora do ar."""
    try:
        return asyncio.run(_sync(uf))
    except Exception as exc:  # noqa: BLE001 — portal público instável: retry, não falha o beat
        logger.warning("sync_cest_confaz falhou (%s); reagendando.", exc)
        raise self.retry(exc=exc, countdown=60 * 30) from exc


async def _sync(uf: str) -> dict:
    # 1) Extração (rede) fora da transação.
    resultado = ConfazCestExtractor().extract()
    logger.info("CEST/CONFAZ: %d registros de %s", len(resultado.registros), resultado.fonte)

    # 2) Upsert idempotente na vigência do mês corrente.
    async with worker_global_session() as s:
        resumo = await upsert_enquadramento(
            s, resultado.registros, uf=uf, vigencia_inicio=date.today().replace(day=1),
        )
    logger.info("CEST/CONFAZ upsert: %s", resumo)
    return {"fonte": resultado.fonte, **resumo}
