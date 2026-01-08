from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import User
from .auth import decode_token

bearer = HTTPBearer()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    try:
        user_id = decode_token(creds.credentials)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
