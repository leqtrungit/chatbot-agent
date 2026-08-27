"""Identity module: principals and FastAPI dependencies."""

from app.core.security import (
    OperatorPrincipal,
    TenantPrincipal,
    MultipleOrgsError,
    UnauthorizedPrincipalError,
)

__all__ = [
    "OperatorPrincipal",
    "TenantPrincipal",
    "MultipleOrgsError",
    "UnauthorizedPrincipalError",
]
