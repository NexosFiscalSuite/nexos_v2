"""Tasks Celery de auto-alimentação fiscal (agendadas no beat).

Fase 1 da automação: o crawler NUNCA escreve direto nas matrizes — o diff da
fonte vira PROPOSTA na fila de revisão (aba Revisão das Matrizes Fiscais).
Padrão: o I/O da fonte (fetch+parse) roda FORA da transação; só a persistência
abre a sessão global, POR unidade de trabalho.
"""
import asyncio
import logging
from datetime import UTC, date, datetime

from sqlalchemy import func, select

from app.core.alerts import notificar
from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.worker_db import worker_global_session
from app.modules.fiscal.crawlers.base import http_get
from app.modules.fiscal.crawlers.confaz_cest import ConfazCestExtractor
from app.modules.fiscal.crawlers.propor import propor_enquadramento, registrar_snapshot
from app.modules.fiscal.crawlers.reconferencia import propor_reconferencia
from app.modules.fiscal.infrastructure.propostas_models import FonteSnapshot

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
    """Baixa a relação NCM×CEST do CONFAZ (uma vez), registra o snapshot da
    fonte (hash + conteúdo) e gera PROPOSTAS de enquadramento por UF alvo
    ("MG,SP,…"; vazio = NEXOS_CRAWLER_UF_ALVO) — nada entra sem curadoria.
    Reagenda (retry) se a fonte estiver fora do ar."""
    try:
        return asyncio.run(_sync(_ufs_alvo(ufs)))
    except Exception as exc:  # noqa: BLE001 — portal público instável: retry, não falha o beat
        logger.warning("sync_cest_confaz falhou (%s); reagendando.", exc)
        raise self.retry(exc=exc, countdown=60 * 30) from exc


@celery_app.task(name="fiscal.reconferir_aliquotas", bind=True, max_retries=2)
def reconferir_aliquotas(self, ufs: str = ""):
    """Reconferência semestral (Fase 4): alíquota modal e FCP vigentes de cada
    UF alvo viram proposta REVALIDAR na fila — aprovar = 'continua valendo'
    (renova o carimbo); mudou? rejeite e ajuste pelo CRUD (vigência nova)."""
    try:
        return asyncio.run(_reconferir(_ufs_alvo(ufs)))
    except Exception as exc:  # noqa: BLE001 — retry, não falha o beat
        logger.warning("reconferir_aliquotas falhou (%s); reagendando.", exc)
        raise self.retry(exc=exc, countdown=60 * 30) from exc


async def _reconferir(ufs: list[str]) -> dict:
    agora = datetime.now(UTC)
    semestre = 1 if agora.month <= 6 else 2
    ciclo = f"{agora.year}-{semestre}"
    inicio_ciclo = datetime(agora.year, 1 if semestre == 1 else 7, 1, tzinfo=UTC)
    async with worker_global_session() as s:
        resumo = await propor_reconferencia(s, ufs, ciclo=ciclo, inicio_ciclo=inicio_ciclo)
    logger.info("Reconferência %s: %s", ciclo, resumo)
    return resumo


# Radar de Protocolos ICMS (Fase 3): o índice oficial por ano. Não extrai
# dado — DETECTA mudança e avisa; quem decide e cadastra é o curador.
URL_PROTOCOLOS = "https://www.confaz.fazenda.gov.br/legislacao/protocolos/{ano}"


@celery_app.task(name="fiscal.monitor_protocolos_confaz", bind=True, max_retries=2)
def monitor_protocolos_confaz(self):
    """Radar semanal: baixa o índice de Protocolos ICMS do CONFAZ (ano corrente
    e anterior), compara por hash (FonteSnapshot) e NOTIFICA quando a página
    muda — protocolo novo, adesão ou denúncia vira aviso, nunca dado calado."""
    try:
        return asyncio.run(_monitorar_protocolos())
    except Exception as exc:  # noqa: BLE001 — portal público instável: retry, não falha o beat
        logger.warning("monitor_protocolos_confaz falhou (%s); reagendando.", exc)
        raise self.retry(exc=exc, countdown=60 * 30) from exc


async def _monitorar_protocolos() -> dict:
    resultado: dict[str, dict] = {}
    ano_atual = date.today().year
    for ano in (ano_atual, ano_atual - 1):
        url = URL_PROTOCOLOS.format(ano=ano)
        fonte = f"CONFAZ — Protocolos ICMS {ano}"
        bruto = http_get(url)
        async with worker_global_session() as s:
            ja_tinha = await s.scalar(
                select(func.count()).select_from(FonteSnapshot)
                .where(FonteSnapshot.fonte == fonte)
            )
            mudou, snap_id = await registrar_snapshot(
                s, fonte=fonte, url=url, conteudo=bruto,
                resumo=f"índice {ano} ({len(bruto)} bytes)",
            )
        resultado[str(ano)] = {"mudou": mudou, "snapshot_id": snap_id}
        if mudou and ja_tinha:
            notificar(
                f"Nexos: índice de Protocolos ICMS {ano} mudou no CONFAZ",
                "A página oficial foi alterada — pode haver protocolo novo, adesão ou "
                "denúncia afetando os pares interestaduais. Confira e atualize a "
                "matriz de Protocolos (a aba Saúde mostra os pares em jogo).",
                {"url": url},
            )
            logger.warning("Radar CONFAZ: índice %s mudou (snapshot %s).", ano, snap_id)
        elif mudou:
            logger.info("Radar CONFAZ: primeira captura do índice %s registrada.", ano)
    return resultado


async def _sync(ufs: list[str]) -> dict:
    # 1) Extração (rede) UMA vez, fora da transação — a relação é nacional.
    extrator = ConfazCestExtractor()
    bruto = extrator.fetch()
    registros = extrator.parse(bruto)
    logger.info("CEST/CONFAZ: %d registros de %s", len(registros), extrator.fonte)

    # 2) Snapshot da fonte (trilha de origem + detecção de mudança).
    async with worker_global_session() as s:
        mudou, snapshot_id = await registrar_snapshot(
            s, fonte=extrator.fonte, url=extrator.url, conteudo=bruto,
            resumo=f"{len(registros)} registros NCM×CEST",
        )

    # 3) Diff → propostas, POR UF (sessão por unidade de trabalho). Roda mesmo
    # sem mudança na fonte: uma UF recém-adicionada precisa das propostas
    # ainda que a página do CONFAZ esteja idêntica; a vigência-piso fixa vem
    # da config (competências auditadas começam em jun/2026).
    vigencia = date.fromisoformat(get_settings().crawler_vigencia_inicio)
    resumos: dict[str, dict] = {}
    for uf in ufs:
        async with worker_global_session() as s:
            resumos[uf] = await propor_enquadramento(
                s, registros, uf=uf, vigencia_inicio=vigencia,
                fonte=extrator.fonte, snapshot_id=snapshot_id,
            )
        logger.info("CEST/CONFAZ propostas %s: %s", uf, resumos[uf])
    return {"fonte": extrator.fonte, "fonte_mudou": mudou, "ufs": resumos}
