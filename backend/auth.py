import os
import datetime
import hashlib
import hmac
import logging
import secrets
import smtplib
import ssl
import string
import pyotp
import jwt
from email.message import EmailMessage
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pathlib import Path
from dotenv import load_dotenv

from password_utils import verify_password
import db

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")

JWT_SECRET = os.environ.get("JWT_SECRET", "aria-ai-super-secret-key-2024")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRATION_HOURS = 24
OTP_LENGTH = int(os.environ.get("OTP_LENGTH", "6"))
OTP_EXPIRATION_MINUTES = int(os.environ.get("OTP_EXPIRATION_MINUTES", "10"))
OTP_HASH_SECRET = os.environ.get("OTP_HASH_SECRET", JWT_SECRET)
TOTP_ISSUER = os.environ.get("TOTP_ISSUER", "ARIA AI")
TOTP_INTERVAL_SECONDS = int(os.environ.get("TOTP_INTERVAL_SECONDS", "30"))
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", SMTP_USERNAME or "no-reply@aria.ai")
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "on"}

security = HTTPBearer()


def generate_otp_code(length: int = OTP_LENGTH) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def hash_otp_code(code: str) -> str:
    return hmac.new(OTP_HASH_SECRET.encode("utf-8"), code.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_otp_code(code: str, expected_hash: str) -> bool:
    if not code or not expected_hash:
        return False
    computed_hash = hash_otp_code(code)
    return hmac.compare_digest(computed_hash, expected_hash)


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def build_totp_uri(username: str, secret: str) -> str:
    totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL_SECONDS)
    return totp.provisioning_uri(name=username, issuer_name=TOTP_ISSUER)


def verify_totp_code(code: str, secret: str) -> bool:
    if not code or not secret:
        return False
    totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL_SECONDS)
    return bool(totp.verify(code, valid_window=1))


def send_otp_email(recipient: str, code: str, purpose: str) -> bool:
    subject_map = {
        "signup": "Verify your new ARIA AI account",
        "login": "Your ARIA AI login verification code",
        "password_reset": "Reset your ARIA AI password",
        "first_login_reset": "Verify your identity for first login",
    }
    subject = subject_map.get(purpose, "Your ARIA AI verification code")
    message = EmailMessage()
    message["From"] = SMTP_FROM_EMAIL
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(
        f"Your verification code is {code}. It expires in {OTP_EXPIRATION_MINUTES} minutes.\n\nIf you did not request this code, you can ignore this email."
    )

    if not SMTP_HOST:
        logger.warning("SMTP_HOST is not configured; OTP email for %s was not sent. Code=%s", recipient, code)
        return True

    try:
        if SMTP_USE_TLS:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                if SMTP_USERNAME:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(message)
        else:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context(), timeout=15) as server:
                if SMTP_USERNAME:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(message)
        return True
    except Exception as exc:
        logger.exception("Failed to send OTP email to %s: %s", recipient, exc)
        return False

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


def is_user_verified(user: dict | None) -> bool:
    if not user:
        return False
    return bool(user.get("is_verified", True))


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
