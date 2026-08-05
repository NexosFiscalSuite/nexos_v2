"""Alerta operacional de falha nos jobs assíncronos (ponto único).

Sem ninguém olhando o log do worker, um job falho fica invisível até alguém
sentir falta do resultado. Todo caminho de falha de job passa por aqui:
  - loga SEMPRE em nível CRITICAL no logger "nexos.alerts" (grep-ável);
  - com NEXOS_ALERT_WEBHOOK_URL configurada, faz POST JSON best-effort
    (ntfy.sh, Slack/Teams incoming webhook, etc.).

O alerta nunca derruba o worker: falha no webhook vira warning no log e a
tarefa segue seu curso (o job já foi marcado como failed no banco).
"""
from __future__ import annotations

import json
import logging
import urllib.request

from app.core.config import get_settings

logger = logging.getLogger("nexos.alerts")

_TIMEOUT_S = 5


def notificar(titulo: str, mensagem: str, contexto: dict | None = None) -> None:
    """POST JSON best-effort no webhook (se configurado). Nunca levanta —
    também serve a avisos que NÃO são falha (ex.: radar de fontes oficiais)."""
    url = get_settings().alert_webhook_url
    if not url:
        return
    try:
        corpo = json.dumps(
            {"title": titulo, "message": mensagem, "context": contexto or {}},
            ensure_ascii=False, default=str,
        ).encode("utf-8")
        req = urllib.request.Request(
            url, data=corpo, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=_TIMEOUT_S)  # noqa: S310 — URL vem da config do operador
    except Exception:  # noqa: BLE001 — alerta é best-effort, nunca derruba o worker
        logger.warning("Webhook de alerta indisponível; aviso registrado só no log.")


def alertar_falha(origem: str, detalhe: str, contexto: dict | None = None) -> None:
    """Registra a falha (log CRITICAL) e notifica o webhook, se configurado."""
    logger.critical("[%s] %s | contexto=%s", origem, detalhe, contexto or {})
    notificar(f"Nexos: falha em {origem}", detalhe, contexto)
