from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel
from models.database import get_db, User
from auth import (
    verify_password, create_access_token, require_user,
    client_ip, check_login_rate_limit, record_login_failure, record_login_success
)

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    check_login_rate_limit(ip)

    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        record_login_failure(ip)
        raise HTTPException(401, "Invalid username or password.")

    record_login_success(ip)
    user.last_login = datetime.utcnow()
    db.commit()

    token = create_access_token(user.id, user.username)
    return {"access_token": token, "token_type": "bearer", "username": user.username}


@router.get("/me")
def me(current_user: dict = Depends(require_user)):
    return current_user
