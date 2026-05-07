import os
import datetime
import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pathlib import Path
from dotenv import load_dotenv

from password_utils import verify_password
import db

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")

JWT_SECRET = os.environ.get("JWT_SECRET", "aria-ai-super-secret-key-2024")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRATION_HOURS = 24

security = HTTPBearer()

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(hours=TOKEN_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def verify_token(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def authenticate_user(username: str, password: str) -> dict | None:
    user = db.get_user_by_username(username)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user


def get_current_user(auth: HTTPAuthorizationCredentials = Security(security)):
    payload = verify_token(auth.credentials)
    if not payload:
        raise HTTPException(status_code=403, detail="Unauthorized access for this role")
    return payload


def require_role(*allowed_roles: str):
    def dependency(auth: HTTPAuthorizationCredentials = Security(security)):
        payload = verify_token(auth.credentials)
        role = str(payload.get("role", "")).lower()
        allowed = {str(item).lower() for item in allowed_roles}
        if role not in allowed:
            raise HTTPException(status_code=403, detail="Unauthorized access for this role")
        return payload

    return dependency


def get_current_admin(auth: HTTPAuthorizationCredentials = Security(security)):
    payload = verify_token(auth.credentials)
    if not payload or str(payload.get("role", "")).lower() != "admin":
        raise HTTPException(status_code=403, detail="Unauthorized access for this role")
    return payload


def get_current_officer(auth: HTTPAuthorizationCredentials = Security(security)):
    payload = verify_token(auth.credentials)
    if not payload or str(payload.get("role", "")).lower() != "officer":
        raise HTTPException(status_code=403, detail="Unauthorized access for this role")
    return payload


def get_current_senior_officer(auth: HTTPAuthorizationCredentials = Security(security)):
    payload = verify_token(auth.credentials)
    if not payload or str(payload.get("role", "")).lower() != "senior_officer":
        raise HTTPException(status_code=403, detail="Unauthorized access for this role")
    return payload
