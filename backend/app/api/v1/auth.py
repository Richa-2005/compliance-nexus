import datetime
from datetime import timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.models import Users

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/token")

auth_router = APIRouter(prefix="/auth", tags=["Auth"])


@auth_router.post("/token")
def authentication(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db),
):
    email = form_data.username

    query = select(Users).where(Users.email == email)
    user = db.scalar(query)

    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)

    payload = {
        "sub": email,
        "role": role_val,
        "exp": datetime.datetime.now(timezone.utc) + datetime.timedelta(hours=24),
    }

    encoded_jwt = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY.get_secret_value()
        if hasattr(settings.JWT_SECRET_KEY, "get_secret_value")
        else str(settings.JWT_SECRET_KEY),
        algorithm=settings.JWT_ALGORITHM,
    )

    return {
        "access_token": encoded_jwt,
        "token_type": "bearer",
        "role": role_val,
        "user_name": user.full_name,
    }


@auth_router.get("/me")
def validation(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        secret_str = (
            settings.JWT_SECRET_KEY.get_secret_value()
            if hasattr(settings.JWT_SECRET_KEY, "get_secret_value")
            else str(settings.JWT_SECRET_KEY)
        )
        payload = jwt.decode(
            token, secret_str, algorithms=[settings.JWT_ALGORITHM]
        )
        user_email: str = payload.get("sub")
        if user_email is None:
            raise credentials_exception

        query = select(Users).where(Users.email == user_email)
        user = db.scalar(query)

        if user is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)

    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": role_val,
    }