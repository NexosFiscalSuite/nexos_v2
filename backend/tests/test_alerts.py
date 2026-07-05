"""Alerta operacional de job falho: log CRITICAL sempre; webhook best-effort."""
import json
import logging
from types import SimpleNamespace

from app.core import alerts


def test_sem_webhook_loga_critical(caplog):
    with caplog.at_level(logging.CRITICAL, logger="nexos.alerts"):
        alerts.alertar_falha("fiscal.import_xmls", "explodiu", {"job_id": "abc"})

    assert len(caplog.records) == 1
    reg = caplog.records[0]
    assert reg.levelno == logging.CRITICAL
    assert "fiscal.import_xmls" in reg.getMessage()
    assert "explodiu" in reg.getMessage()


def test_com_webhook_faz_post_json(monkeypatch):
    chamadas = []

    def _fake_urlopen(req, timeout):
        chamadas.append((req.full_url, json.loads(req.data.decode("utf-8")), timeout))

    monkeypatch.setattr(
        alerts, "get_settings",
        lambda: SimpleNamespace(alert_webhook_url="https://ntfy.sh/nexos"),
    )
    monkeypatch.setattr(alerts.urllib.request, "urlopen", _fake_urlopen)

    alerts.alertar_falha("reporting.generate", "sem storage", {"job_id": "xyz"})

    assert len(chamadas) == 1
    url, corpo, _ = chamadas[0]
    assert url == "https://ntfy.sh/nexos"
    assert corpo["title"] == "Nexos: falha em reporting.generate"
    assert corpo["message"] == "sem storage"
    assert corpo["context"] == {"job_id": "xyz"}


def test_webhook_fora_do_ar_nao_derruba_o_worker(monkeypatch, caplog):
    def _explode(req, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(
        alerts, "get_settings",
        lambda: SimpleNamespace(alert_webhook_url="https://ntfy.sh/nexos"),
    )
    monkeypatch.setattr(alerts.urllib.request, "urlopen", _explode)

    with caplog.at_level(logging.WARNING, logger="nexos.alerts"):
        alerts.alertar_falha("fiscal.import_xmls", "explodiu")   # não pode levantar

    assert any("Webhook" in r.getMessage() for r in caplog.records)
