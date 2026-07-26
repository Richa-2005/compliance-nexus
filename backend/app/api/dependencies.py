from typing import Annotated, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.models import Roles, Users


oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/token")

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> Users:
    """FastAPI dependency that decodes the JWT bearer token from the HTTP Authorization header,

    validates the signature and expiration, and retrieves the matching active User from SQLite.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
       
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value()
            if hasattr(settings.JWT_SECRET_KEY, "get_secret_value")
            else str(settings.JWT_SECRET_KEY),
            algorithms=["HS256"],
        )

        email: Optional[str] = payload.get("sub")
        if email is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    
    user = db.query(Users).filter(Users.email == email).first()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return user


class RoleChecker:
    """Role-Based Access Control (RBAC) dependency wrapper.

    Enforces that the current authenticated user possesses one of the authorized roles.
    """

    def __init__(self, allowed_roles: list[Roles]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: Users = Depends(get_current_user)) -> Users:
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User role '{current_user.role.value}' lacks insufficient permissions to perform this action.",
            )
        return current_user