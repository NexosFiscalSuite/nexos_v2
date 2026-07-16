"""Carga de matrizes fiscais via CSV pela linha de comando.

Usa o MESMO motor do "Importar Planilha" da UI (validação por schema, upsert
por chave e trava de sobreposição de vigência) — serve para cargas preparadas
no repositório (backend/cargas/) sem depender de cliques.

Uso (no servidor, a partir de backend/):
    docker compose -f docker-compose.prod.yml exec api \
        python scripts/carga_matrizes.py enquadramento cargas/2026-06-supervisores/enquadramento_mg.csv

Tipos aceitos: mva | enquadramento | fcp | protocolos | aliquotas
Linha ruim vira relatório (linha + motivo) e NÃO derruba o lote.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.modules.fiscal.api.matrizes_bulk import MATRIZES  # noqa: E402
from app.shared.bulk_csv import importar_csv  # noqa: E402


async def _main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in MATRIZES:
        print(f"Uso: python scripts/carga_matrizes.py <{'|'.join(MATRIZES)}> <arquivo.csv>")
        return 2
    tipo, arquivo = sys.argv[1], Path(sys.argv[2])
    if not arquivo.exists():
        print(f"Arquivo não encontrado: {arquivo}")
        return 1

    engine = create_async_engine(get_settings().database_url)
    async with async_sessionmaker(engine)() as s, s.begin():
        resumo = await importar_csv(s, MATRIZES[tipo], arquivo.read_bytes())
    await engine.dispose()

    print(json.dumps({k: v for k, v in resumo.items() if k != "erros"}, ensure_ascii=False))
    for e in resumo["erros"][:30]:
        print("  erro:", e)
    if len(resumo["erros"]) > 30:
        print(f"  ... +{len(resumo['erros']) - 30} erros")
    return 1 if resumo["erros"] else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
