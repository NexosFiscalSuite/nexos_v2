"""Abstração de storage de XML, isolado por tenant.

Dois backends:
* ``local`` (dev) — grava em disco sob ``storage_local_dir``.
* ``s3``    (prod) — MinIO/S3 via boto3 (import preguiçoso).

As chaves SEMPRE começam com ``{tenant_id}/`` — o isolamento físico do tenant
acompanha o isolamento lógico (RLS). Segmentos são sanitizados (anti path-traversal).
"""
import abc
import re
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings

settings = get_settings()

_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _safe(seg: str, fallback: str = "x") -> str:
    seg = _SAFE.sub("", seg or "")
    return seg or fallback


def xml_key(tenant_id: UUID, cnpj: str, ano: str, mes: str, chave: str, suffix: str = "") -> str:
    """Chave definitiva do XML: {tenant}/{cnpj}/{ano}/{mes}/{chave}{suffix}.xml"""
    return "/".join(
        [
            str(tenant_id),
            _safe(cnpj, "sem_cnpj"),
            _safe(ano, "0000"),
            _safe(mes, "00"),
            f"{_safe(chave, 'sem_chave')}{_safe(suffix)}.xml",
        ]
    )


def staging_key(tenant_id: UUID, job_id: UUID, filename: str) -> str:
    """Chave temporária do upload bruto, antes do processamento na fila."""
    return f"{tenant_id}/_staging/{job_id}/{_safe(filename, 'arquivo')}"


class Storage(abc.ABC):
    @abc.abstractmethod
    def put(self, key: str, data: bytes) -> str: ...

    @abc.abstractmethod
    def get(self, key: str) -> bytes: ...

    @abc.abstractmethod
    def delete(self, key: str) -> None: ...


class LocalStorage(Storage):
    def __init__(self, base_dir: str):
        self.base = Path(base_dir)

    def _path(self, key: str) -> Path:
        return self.base / key

    def put(self, key: str, data: bytes) -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()


class S3Storage(Storage):
    def __init__(self):
        import boto3  # import preguiçoso: só carrega se backend=s3

        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        """Idempotente: provisiona o bucket se ainda não existe. Tolera corrida
        entre API e worker subindo ao mesmo tempo (BucketAlreadyOwnedByYou)."""
        from botocore.exceptions import ClientError

        try:
            self.client.head_bucket(Bucket=self.bucket)
            return  # já existe
        except ClientError:
            pass
        try:
            self.client.create_bucket(Bucket=self.bucket)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                raise  # erro real de provisionamento de storage

    def put(self, key: str, data: bytes) -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return key

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def get_storage() -> Storage:
    if settings.storage_backend == "s3":
        return S3Storage()
    return LocalStorage(settings.storage_local_dir)


def ensure_storage_ready() -> None:
    """Provisiona o storage no startup — garante o bucket S3 antes do 1º upload,
    para que a importação de XML nunca falhe por falta de provisionamento.
    No backend local não há o que provisionar (diretórios são criados sob demanda)."""
    if settings.storage_backend == "s3":
        S3Storage()  # __init__ chama _ensure_bucket()
