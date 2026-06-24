"""Teste manual da consulta optante sobre uma pasta de XMLs (sem banco/worker).

Lê os XMLs, extrai e deduplica os CNPJs (emitente + destinatário) usando o
mesmo parser do sistema, consulta o optante e aplica a MESMA regra de negócio
do import (classificar_optante). Serve para conferir o regime das contrapartes
antes/depois de importar um lote.

Uso:
    ./.venv/Scripts/python.exe scripts/testar_optante.py "C:\\caminho\\dos\\xmls"
    ./.venv/Scripts/python.exe scripts/testar_optante.py "C:\\...\\xmls" --delay 0.2
"""
import sys
import time
from pathlib import Path

# Permite rodar como script solto (python scripts/testar_optante.py): põe o
# diretório `backend/` no sys.path para achar o pacote `app`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.modules.contrapartes.application.service import classificar_optante  # noqa: E402
from app.modules.fiscal.domain import parser as xmlparser  # noqa: E402
from app.shared.cnpj_lookup import consultar_opencnpj, formatar_cnpj  # noqa: E402


def _coletar_cnpjs(pasta: Path) -> dict[str, str]:
    """Varre os XMLs e retorna {cnpj_limpo: melhor_nome_conhecido} deduplicado."""
    encontrados: dict[str, str] = {}
    arquivos = sorted(pasta.glob("*.xml"))
    if not arquivos:
        print(f"Nenhum .xml encontrado em {pasta}")
        return encontrados

    print(f"Lendo {len(arquivos)} arquivo(s)...")
    for arq in arquivos:
        try:
            notas = xmlparser.parse_xml_multi(arq.read_bytes())
        except Exception as e:  # noqa: BLE001 — script de diagnóstico, tolerante
            print(f"  ! {arq.name}: ignorado ({e})")
            continue
        for nota in notas:
            for cnpj_key, nome_key in (("cnpj_emit", "nome_emit"), ("cnpj_dest", "nome_dest")):
                cnpj = (nota.get(cnpj_key) or "").strip()
                if len(cnpj) == 14:  # CPF (11) não tem optante
                    encontrados.setdefault(cnpj, nota.get(nome_key) or "")
    return encontrados


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 1
    pasta = Path(args[0])
    if not pasta.is_dir():
        print(f"Pasta inválida: {pasta}")
        return 1
    delay = 0.2
    if "--delay" in sys.argv:
        delay = float(sys.argv[sys.argv.index("--delay") + 1])

    cnpjs = _coletar_cnpjs(pasta)
    print(f"\n{len(cnpjs)} CNPJ(s) único(s) para consultar.\n")
    print(f"{'CNPJ':<18} {'REGIME':<18} {'PENDENTE':<9} RAZÃO SOCIAL")
    print("-" * 90)

    resumo = {"simples": 0, "pendente": 0, "falha": 0}
    for i, (cnpj, nome_xml) in enumerate(sorted(cnpjs.items()), 1):
        res = consultar_opencnpj(cnpj, "contraparte")
        regime, pendente = classificar_optante(res)
        if regime is None:
            resumo["falha"] += 1
            regime_txt, pend_txt = f"FALHA: {res.get('error')}", "—"
        else:
            resumo["pendente" if pendente else "simples"] += 1
            regime_txt, pend_txt = regime, "SIM" if pendente else "não"
        nome = (res.get("dados") or {}).get("razao_social") or nome_xml
        print(f"{formatar_cnpj(cnpj):<18} {regime_txt:<18} {pend_txt:<9} {nome[:40]}")
        if i < len(cnpjs):
            time.sleep(delay)  # cortesia com a API pública

    print("-" * 90)
    print(
        f"Resolvidos (Simples/MEI): {resumo['simples']}  |  "
        f"Ponto de observação (Normal/pendente): {resumo['pendente']}  |  "
        f"Falhas: {resumo['falha']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
