import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth_service.database import Base, SessionLocal, engine, get_db
from auth_service.models import User
from common.errors import add_bad_request_validation
from common.security import create_access_token, get_current_user, hash_password, verify_password


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def seed_users() -> None:
    if os.getenv("SEED_DEMO_DATA", "true").lower() != "true":
        return
    with SessionLocal() as session:
        for account_id in range(1, 6):
            email = f"cliente{account_id}@bancomnm.xyz"
            user = session.scalar(select(User).where(User.email == email))
            if user is None:
                session.add(
                    User(
                        email=email,
                        password_hash=hash_password("Cliente123!"),
                        role="cliente",
                        account_id=account_id,
                    )
                )
        for analyst_id in range(1, 3):
            email = f"analista{analyst_id}@bancomnm.xyz"
            user = session.scalar(select(User).where(User.email == email))
            if user is None:
                session.add(
                    User(
                        email=email,
                        password_hash=hash_password("Analista123!"),
                        role="analista",
                        account_id=None,
                    )
                )
        session.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    seed_users()
    yield


app = FastAPI(title="Banco MNM AUTH", version="1.0.0", lifespan=lifespan)
add_bad_request_validation(app)


@app.post("/api/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(user.id, user.role, user.account_id)
    return {"token": token, "rol": user.role, "id_cuenta": user.account_id}


@app.get("/api/auth/me")
def me(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.get(User, current_user["user_id"])
    if user is None:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return {"id": user.id, "email": user.email, "rol": user.role, "id_cuenta": user.account_id}


@app.get("/health")
def health():
    return {"service": "auth", "status": "ok"}