"""Consulta de CNPJ via OpenCNPJ (https://api.opencnpj.org/) — portado do V1.

Gratuito, sem chave. Usa stdlib (urllib) — sem dependência nova. Função é
síncrona (bloqueante); chame de um endpoint `def` (FastAPI roda em threadpool)
para não travar o event loop. Nunca levanta exceção: retorna ok=False em falha.
"""
import json
import os
import re
import urllib.error
import urllib.request

OPENCNPJ_URL = "https://api.opencnpj.org"
HTTP_TIMEOUT = 10

_CNAE_TABELA: dict | None = None


def _descricao_cnae(codigo: str) -> str:
    global _CNAE_TABELA
    if _CNAE_TABELA is None:
        try:
            caminho = os.path.join(os.path.dirname(__file__), "cnae_tabela.json")
            with open(caminho, encoding="utf-8") as fh:
                _CNAE_TABELA = json.load(fh)
        except Exception:
            _CNAE_TABELA = {}
    return _CNAE_TABELA.get(codigo, "")


def limpar_cnpj(cnpj: str) -> str:
    return "".join(c for c in (cnpj or "") if c.isdigit())


def formatar_cnpj(cnpj: str) -> str:
    c = limpar_cnpj(cnpj)
    if len(c) == 14:
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    return cnpj or ""


def _regime(data: dict, contexto: str) -> str:
    mei = (data.get("opcao_pelo_mei") or data.get("opcao_mei") or "").upper()
    simples = (data.get("opcao_pelo_simples") or data.get("opcao_simples") or "").upper()
    if mei in ("S", "SIM", "TRUE", "1"):
        return "MEI"
    if simples in ("S", "SIM", "TRUE", "1"):
        return "Simples Nacional"
    # empresa: deixa em branco (admin escolhe Lucro Presumido/Real); contraparte: Normal
    return "" if contexto == "empresa" else "Normal"


def _normalize(data: dict, contexto: str) -> dict:
    municipio = data.get("municipio") or data.get("municipio_nome") or data.get("nome_municipio") or ""
    atividade = (
        data.get("cnae_principal_descricao")
        or data.get("atividade_principal")
        or data.get("cnae_fiscal_descricao")
        or ""
    )
    if isinstance(atividade, list) and atividade:
        item = atividade[0]
        atividade = (item.get("text") or item.get("descricao") or "") if isinstance(item, dict) else str(item)
    if not atividade:
        codigo = re.sub(r"\D", "", str(data.get("cnae_principal") or data.get("cnae_fiscal") or ""))
        if codigo:
            atividade = _descricao_cnae(codigo) or f"CNAE {codigo}"

    return {
        "razao_social": data.get("razao_social") or data.get("nome") or "",
        "nome_fantasia": data.get("nome_fantasia") or data.get("fantasia") or "",
        "situacao": data.get("situacao_cadastral") or data.get("situacao") or "",
        "uf": data.get("uf") or "",
        "municipio": municipio,
        "atividade": atividade,
        "porte": data.get("porte_empresa") or data.get("porte") or "",
        "regime": _regime(data, contexto),
        "logradouro": data.get("logradouro") or "",
        "numero": data.get("numero") or "",
        "complemento": data.get("complemento") or "",
        "bairro": data.get("bairro") or "",
        "cep": data.get("cep") or "",
    }


def consultar_opencnpj(cnpj: str, contexto: str = "empresa") -> dict:
    """Retorna {ok, cnpj, dados, error}. `contexto`: 'empresa' | 'contraparte'."""
    cnpj_clean = limpar_cnpj(cnpj)
    cnpj_fmt = formatar_cnpj(cnpj_clean)
    empty = {
        "razao_social": "", "nome_fantasia": "", "situacao": "", "uf": "", "municipio": "",
        "atividade": "", "porte": "", "regime": "", "logradouro": "", "numero": "",
        "complemento": "", "bairro": "", "cep": "",
    }
    if len(cnpj_clean) != 14:
        return {"ok": False, "cnpj": cnpj_fmt, "dados": empty, "error": "CNPJ deve ter 14 dígitos"}

    req = urllib.request.Request(
        f"{OPENCNPJ_URL}/{cnpj_clean}",
        headers={"User-Agent": "Nexos/2.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        msg = "CNPJ não encontrado" if e.code == 404 else f"Erro HTTP {e.code}"
        return {"ok": False, "cnpj": cnpj_fmt, "dados": empty, "error": msg}
    except urllib.error.URLError as e:
        return {"ok": False, "cnpj": cnpj_fmt, "dados": empty, "error": f"Erro de conexão: {e.reason}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "cnpj": cnpj_fmt, "dados": empty, "error": f"Resposta inválida: {e}"}

    if isinstance(data, dict) and data.get("error"):
        return {"ok": False, "cnpj": cnpj_fmt, "dados": empty, "error": str(data.get("error"))}

    try:
        return {"ok": True, "cnpj": cnpj_fmt, "dados": _normalize(data, contexto), "error": None}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "cnpj": cnpj_fmt, "dados": empty, "error": f"Erro ao processar: {e}"}
