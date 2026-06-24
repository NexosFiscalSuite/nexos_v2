"""Logging estruturado mínimo (JSON em produção, legível em dev)."""
import logging
import sys

from app.core.config import get_settings


def setup_logging() -> None:
    settings = get_settings()
    level = logging.DEBUG if settings.debug else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    if settings.is_production:
        fmt = '{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}'
    else:
        fmt = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
