"""Authentication dependency.

# PHASE-0 STUB
Phase 0 accepts any well-formed `Authorization: Bearer <token>` header and
injects a fixed dev identity. Real Supabase JWT verification (against
`SUPABASE_URL` / `SUPABASE_JWT_SECRET`) lands in Phase 1 once the Supabase
project exists — see docs/DECISIONS.md. Do not mistake this for production
auth: any non-empty token is accepted here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, Request, status
from shared.domain import ApiUser, UserRole

# PHASE-0 STUB — fixed dev identity; replaced by real JWT claims in Phase 1.
_STUB_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
_STUB_ORG_ID = UUID("00000000-0000-0000-0000-000000000002")


def _stub_user() -> ApiUser:
    """Build the fixed Phase-0 dev identity."""
    return ApiUser(
        id=_STUB_USER_ID,
        organization_id=_STUB_ORG_ID,
        email="dev@rustenwer.local",
        display_name="Phase-0 Dev User",
        role=UserRole.OWNER,
        created_at=datetime.now(UTC).isoformat(),
    )


async def get_current_user(request: Request) -> ApiUser:
    """FastAPI dependency: resolve the caller from the Bearer token.

    Raises 401 when the header is missing or malformed. In Phase 0 any
    non-empty token is accepted and maps to the fixed stub identity.
    """
    header = request.headers.get("authorization")
    if header is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed Authorization header: expected 'Bearer <token>'",
        )
    # PHASE-0 STUB: token is accepted without verification.
    return _stub_user()
