"""Carga de matrizes fiscais via CSV pela linha de comando.

Usa o MESMO motor do "Importar Planilha" da UI (validação por schema, upsert
por chave e trava de sobreposição de vigência) — serve para cargas preparadas
no repositório (backend/cargas/) sem depender de cliques.

Uso (no servidor, a partir de backend/):
    docker compose -f docker-compose.prod.yml exec api \
        python scripts/carga_matrizes.py enquadramento cargas/2026-06-supervisores/enquadramento_mg.csv

Tipos aceitos: mva | enquadramento | fcp | protocolos | aliquotas
Linha ruim vira relatório (linha + motivo) e NÃO derruba o lote.

Colunas da MVA (a mesma ordem que o export da tela devolve):

    ncm;cest;uf_origem;uf_destino;mva_original;base_legal;data_inicio_vigencia;data_fim_vigencia

`uf_origem` é a UF de onde a mercadoria vem; vazia ou `*` = a margem vale para
QUALQUER origem. Arquivo antigo (sem a coluna) continua carregando — todas as
linhas entram como `*`, e o script avisa antes de gravar.
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.modules.fiscal.api.matrizes_bulk import MATRIZES  # noqa: E402
from app.shared.bulk_csv import importar_csv  # noqa: E402
from app.shared.domain.uf import CURINGA_UF  # noqa: E402


def _avisar_colunas(tipo: str, conteudo: bytes) -> None:
    """Alerta o operador sobre coluna do schema ausente no arquivo — em especial
    o `uf_origem` da MVA, cuja ausência é silenciosa (vira curinga) e muda o
    alcance da regra carregada."""
    cabecalho = next(
        csv.reader(io.StringIO(conteudo.decode("utf-8-sig", errors="replace")), delimiter=";"),
        [],
    )
    presentes = {c.strip() for c in cabecalho}
    faltando = [c for c in MATRIZES[tipo].colunas if c not in presentes]
    if not faltando:
        return
    print(f"  aviso: colunas ausentes no arquivo ({', '.join(faltando)}).")
    if tipo == "mva" and "uf_origem" in faltando:
        print(f"  aviso: sem 'uf_origem' toda linha entra como '{CURINGA_UF}' "
              "(vale para qualquer UF de origem).")


async def _main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in MATRIZES:
        print(f"Uso: python scripts/carga_matrizes.py <{'|'.join(MATRIZES)}> <arquivo.csv>")
        return 2
    tipo, arquivo = sys.argv[1], Path(sys.argv[2])
    if not arquivo.exists():
        print(f"Arquivo não encontrado: {arquivo}")
        return 1
    _avisar_colunas(tipo, arquivo.read_bytes())

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
