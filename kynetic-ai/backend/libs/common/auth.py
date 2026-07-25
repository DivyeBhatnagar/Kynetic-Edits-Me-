"""
Shared Auth Dependency for Microservices.
"""

import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

bearer_scheme = HTTPBearer(auto_error=False)

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev_secret_key_change_in_prod")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """
    Validate the Bearer JWT across microservices.
    Returns the decoded payload dict (containing 'sub', 'role', etc.).
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
        payload["_raw_token"] = credentials.credentials
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )
