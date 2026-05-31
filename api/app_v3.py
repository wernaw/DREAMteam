from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from api.services.auth_service import decode_access_token, login_user


app = FastAPI()
security = HTTPBearer()


class LoginRequest(BaseModel):
    username: str
    password: str


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    return payload


def require_role(required_role: str):
    def checker(user=Depends(get_current_user)):
        if user.get("role") != required_role:
            raise HTTPException(status_code=403, detail="Access forbidden.")

        return user

    return checker


@app.get("/")
def welcome_root():
    return {"message": "Welcome to the DREAMteam!"}


@app.post("/login")
def login(payload: LoginRequest):
    result = login_user(payload.username, payload.password)

    if not result["success"]:
        raise HTTPException(status_code=401, detail=result["message"])

    return result


@app.get("/candidate")
def candidate_page_data(user=Depends(require_role("candidate"))):
    return {
        "message": "Candidate area",
        "user": user,
    }


@app.get("/recruiter")
def recruiter_page_data(user=Depends(require_role("recruiter"))):
    return {
        "message": "Recruiter area",
        "user": user,
    }
