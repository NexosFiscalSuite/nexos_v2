"""Testes unitários (sem banco) das peças críticas da Fase 2:
validação de CNPJ, hashing de senha, round-trip de JWT e hierarquia RBAC.
"""
from uuid import uuid4

import pytest

from app.core.exceptions import DomainError
from app.core.rbac import Role, role_level
from app.core.security import (
    ACCESS,
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.shared.domain.value_objects import CNPJ


# ── CNPJ ─────────────────────────────────────────────────────────────────────
def test_cnpj_valido_normaliza():
    cnpj = CNPJ("11.444.777/0001-61")
    assert cnpj.value == "11444777000161"
    assert cnpj.formatted == "11.444.777/0001-61"


@pytest.mark.parametrize("bad", ["123", "00.000.000/0000-00", "11.444.777/0001-60"])
def test_cnpj_invalido(bad):
    with pytest.raises(DomainError):
        CNPJ(bad)


# ── Senha ────────────────────────────────────────────────────────────────────
def test_hash_e_verify_senha():
    h = hash_password("s3nh4-forte")
    assert h != "s3nh4-forte"
    assert verify_password(h, "s3nh4-forte") is True
    assert verify_password(h, "errada") is False


# ── JWT ──────────────────────────────────────────────────────────────────────
def test_access_token_round_trip():
    uid, tid = uuid4(), uuid4()
    token = create_access_token(user_id=uid, tenant_id=tid, role="admin", plan="pro")
    claims = decode_token(token)
    assert claims.sub == uid
    assert claims.tid == tid
    assert claims.role == "admin"
    assert claims.plan == "pro"
    assert claims.type == ACCESS


# ── RBAC ─────────────────────────────────────────────────────────────────────
def test_hierarquia_papeis():
    assert role_level(Role.ADMIN.value) > role_level(Role.SUPERVISOR.value)
    assert role_level(Role.SUPERVISOR.value) > role_level(Role.USER.value)
    assert role_level("desconhecido") == 0
