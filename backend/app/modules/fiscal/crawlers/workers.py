"""Tasks Celery de auto-alimentação fiscal (agendadas no beat).

Padrão: o I/O da fonte (fetch+parse) roda FORA da transação; só a persistência
abre a sessão global. Cada task tem seu próprio event loop (asyncio.run), como
as demais workers do projeto.
"""
import asyncio
import logging
from datetime import date

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.worker_db import worker_global_session
from app.modules.fiscal.crawlers.confaz_cest import ConfazCestExtractor
from app.modules.fiscal.crawlers.upsert import upsert_enquadramento

logger = logging.getLogger(__name__)


def _ufs_alvo(ufs: str) -> list[str]:
    """'MG, sp,,GO' → ['MG', 'SP', 'GO'] (vazio → configuração)."""
    bruto = ufs or get_settings().crawler_uf_alvo
    vistos: list[str] = []
    for u in bruto.split(","):
        uf = u.strip().upper()
        if uf and uf not in vistos:
            vistos.append(uf)
    return vistos


@celery_app.task(name="fiscal.sync_cest_confaz", bind=True, max_retries=3)
def sync_cest_confaz(self, ufs: str = ""):
    """Baixa a relação NCM×CEST do CONFAZ (uma vez) e faz upsert na matriz de
    enquadramento de CADA UF alvo ("MG,SP,..."; vazio = NEXOS_CRAWLER_UF_ALVO).
    Reagenda (retry exponencial) se a fonte estiver fora do ar."""
    try:
        return asyncio.run(_sync(_ufs_alvo(ufs)))
    except Exception as exc:  # noqa: BLE001 — portal público instável: retry, não falha o beat
        logger.warning("sync_cest_confaz falhou (%s); reagendando.", exc)
        raise self.retry(exc=exc, countdown=60 * 30) from exc


async def _sync(ufs: list[str]) -> dict:
    # 1) Extração (rede) UMA vez, fora da transação — a relação é nacional.
    resultado = ConfazCestExtractor().extract()
    logger.info("CEST/CONFAZ: %d registros de %s", len(resultado.registros), resultado.fonte)

    # 2) Upsert idempotente por UF, sessão POR unidade de trabalho.
    resumos: dict[str, dict] = {}
    vigencia = date.today().replace(day=1)
    for uf in ufs:
        async with worker_global_session() as s:
            resumos[uf] = await upsert_enquadramento(
                s, resultado.registros, uf=uf, vigencia_inicio=vigencia,
            )
        logger.info("CEST/CONFAZ upsert %s: %s", uf, resumos[uf])
    return {"fonte": resultado.fonte, "ufs": resumos}
