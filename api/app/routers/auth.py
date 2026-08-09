import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Connection

from app import queries
from app.db import get_db
from app.schemas import UserLoginIn, UserOut, UserRegisterIn

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut)
def register(payload: UserRegisterIn, conn: Connection = Depends(get_db)):
    if queries.get_user_by_email(conn, payload.email) is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    password_hash = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode()
    user = queries.create_user(conn, payload.email, password_hash)
    return UserOut(**user)


@router.post("/login", response_model=UserOut)
def login(payload: UserLoginIn, conn: Connection = Depends(get_db)):
    user = queries.get_user_by_email(conn, payload.email)
    if user is None or not bcrypt.checkpw(payload.password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return UserOut(id=user["id"], email=user["email"])
