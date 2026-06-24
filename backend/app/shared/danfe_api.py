"""DANFE no layout oficial via API externa (consultadanfe.com) — portado do V1.

Envia o XML COMPLETO (multipart) e recebe o PDF. Aceita NF-e/NFC-e/CT-e/NFS-e.
Stdlib (urllib), síncrono — chame de endpoint `def` ou via run_in_threadpool.
Retorna (pdf_bytes, None) ou (None, erro). Nunca levanta exceção dura.

Config: DANFE_API_URL (default consultadanfe.com), DANFE_API_TOKEN (opcional).
"""
import base64
import json
import os
import urllib.error
import urllib.request
import uuid


def _api_url() -> str:
    return os.environ.get("DANFE_API_URL", "https://consultadanfe.com/api/v1/danfe")


def _timeout() -> float:
    try:
        return float(os.environ.get("DANFE_API_TIMEOUT", "25"))
    except ValueError:
        return 25.0


def _montar_multipart(xml_texto: str):
    boundary = "----NexosBoundary" + uuid.uuid4().hex
    nl = "\r\n"
    partes = [
        f"--{boundary}{nl}",
        f'Content-Disposition: form-data; name="format"{nl}{nl}', f"pdf{nl}",
        f"--{boundary}{nl}",
        f'Content-Disposition: form-data; name="xml"; filename="nota.xml"{nl}',
        f"Content-Type: application/xml{nl}{nl}", xml_texto, nl,
        f"--{boundary}--{nl}",
    ]
    return "".join(partes).encode("utf-8"), boundary


def gerar_danfe(xml_texto: str):
    """Retorna (pdf_bytes, None) ou (None, erro)."""
    if not xml_texto or not xml_texto.strip():
        return None, "XML vazio."
    corpo, boundary = _montar_multipart(xml_texto)
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/pdf, application/json",
        "User-Agent": "NexosFiscalSuite/2.0",
    }
    token = os.environ.get("DANFE_API_TOKEN")
    if token:
        headers["Authorization"] = token

    req = urllib.request.Request(_api_url(), data=corpo, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_timeout()) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            raw = resp.read()
    except urllib.error.HTTPError as e:
        detalhe = ""
        try:
            j = json.loads(e.read().decode("utf-8"))
            detalhe = j.get("message") or j.get("error") or ""
        except Exception:
            pass
        if e.code == 429:
            return None, "Limite de uso da API de DANFE atingido. Tente novamente em instantes."
        return None, f"API de DANFE: {detalhe or ('HTTP ' + str(e.code))}"
    except urllib.error.URLError as e:
        return None, f"Falha de conexão com a API de DANFE: {e.reason}"
    except Exception as e:  # noqa: BLE001
        return None, f"Erro ao chamar a API de DANFE: {e}"

    if raw[:4] == b"%PDF":
        return raw, None
    if "application/json" in ctype or raw[:1] in (b"{", b"["):
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return None, "Resposta da API de DANFE não reconhecida."
        b64 = data.get("pdf_base64") or (data.get("pdf") or {}).get("base64")
        if not b64:
            return None, str(data.get("message") or data.get("error") or "API não retornou o PDF.")
        try:
            pdf = base64.b64decode(b64)
        except Exception:
            return None, "Não foi possível decodificar o PDF."
        return (pdf, None) if pdf[:4] == b"%PDF" else (None, "Conteúdo não é um PDF válido.")
    return None, "Resposta inesperada da API de DANFE."
