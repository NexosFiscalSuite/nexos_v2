FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Instala dependências primeiro (cache de camada)
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY . .

# Roda como usuário sem privilégio (defesa em profundidade).
RUN useradd --system --create-home --uid 1000 nexos && chown -R nexos:nexos /app
USER nexos

EXPOSE 8000

# Healthcheck via stdlib (slim não traz curl). Bate no endpoint /health.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status==200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
