"""DTOs da camada de aplicação (independentes de HTTP/ORM)."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@dataclass(slots=True)
class UserView:
    id: UUID
    tenant_id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime | None
    last_login: datetime | None
