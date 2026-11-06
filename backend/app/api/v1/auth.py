"""Auth endpoints (operator login first; passenger auth is added with the login work)."""
from fastapi import APIRouter, Depends

from app.config import get_settings
from app.errors import AppError
from app.schemas.contract import OpsLoginIn, TokenOut
from app.security import auth_limiter, create_ops_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/ops-login", response_model=TokenOut, dependencies=[Depends(auth_limiter)])
async def ops_login(body: OpsLoginIn) -> dict:
    import hmac
    if not hmac.compare_digest(body.password.encode(), get_settings().OPS_PASSWORD.encode()):
        raise AppError("INVALID_CREDENTIALS", "Wrong operator password")
    return {"token": create_ops_token()}
