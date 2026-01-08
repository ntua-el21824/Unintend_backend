from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext

SECRET_KEY = "CHANGE_ME_FOR_PROD__but_ok_for_class"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")



def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject_user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": str(subject_user_id), "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> int:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise ValueError("Invalid token")
