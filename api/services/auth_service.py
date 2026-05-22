import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from jose import JWTError, jwt
from passlib.context import CryptContext


load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))


USERS = {
    os.getenv("CANDIDATE_USERNAME"): {
        "password_hash": os.getenv("CANDIDATE_PASSWORD_HASH"),
        "role": "candidate",
        "redirect_to": "/candidate",
    },
    os.getenv("RECRUITER_USERNAME"): {
        "password_hash": os.getenv("RECRUITER_PASSWORD_HASH"),
        "role": "recruiter",
        "redirect_to": "/recruiter",
    },
}


def verify_password(password, password_hash):
    return pwd_context.verify(password, password_hash)


def create_access_token(data):
    if not JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is not set.")

    payload = data.copy()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)

    payload.update({"exp": expires_at})

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token):
    if not JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is not set.")

    try:
        return jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
    except JWTError:
        return None


def login_user(username, password):
    user = USERS.get(username)

    if user is None or not user["password_hash"]:
        return {
            "success": False,
            "message": "Invalid username or password.",
        }

    if not verify_password(password, user["password_hash"]):
        return {
            "success": False,
            "message": "Invalid username or password.",
        }

    token = create_access_token(
        {
            "sub": username,
            "role": user["role"],
        }
    )

    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
        "redirect_to": user["redirect_to"],
    }
