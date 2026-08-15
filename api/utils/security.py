import os
from fastapi import Request, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.security.api_key import APIKeyHeader
import jwt
from jwt import PyJWKClient
import hmac
import hashlib
from slowapi import Limiter
from slowapi.util import get_remote_address


SUPABASE_URL = os.environ.get("SUPABASE_URL")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")

jwks_url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
jwks_client = PyJWKClient(jwks_url)

security_bearer = HTTPBearer()
limiter = Limiter(key_func=get_remote_address)


async def verify_jwt(
    credentials: HTTPAuthorizationCredentials = Security(security_bearer),
):
    """Validates Supabase asymmetric token using its public keys."""
    token = credentials.credentials
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["HS256", "ES256", "RS256"],
            options={"verify_aud": False},
        )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=401, detail="Invalid token: missing subject"
            )

        return payload

    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail="Error validating token.")


async def verify_webhook_signature(request: Request):
    """Valida que el webhook venga realmente de la pasarela de pagos."""
    signature_header = request.headers.get("Stripe-Signature")

    if not signature_header:
        raise HTTPException(status_code=401, detail="Webhook signature missing")

    raw_body = await request.body()

    expected_sig = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, signature_header):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    return True


API_KEY_NAME = "X-API-Key"
MASTER_API_KEY = os.getenv("API_KEY")

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)):
    """Valida que la petición incluya la API Key correcta en los headers."""
    if api_key == MASTER_API_KEY:
        return api_key

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key.",
    )
