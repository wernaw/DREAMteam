from fastapi import Depends, FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from pathlib import Path
from pydantic import BaseModel, Field
import json
import sqlite3
import uvicorn

from api.services.chatbot import candidate_chatbot
from api.services.team_performance_simulator_openai import form_and_rank_teams
from api.services.project_service import get_candidate_project_names, get_project_names
from api.services.auth_service import decode_access_token, login_user


BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = BASE_DIR / "api" / "dreamteam"

app = FastAPI()
security = HTTPBearer(auto_error=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/api/static", StaticFiles(directory=BASE_DIR / "ui" / "static"), name="static"
)

templates = Jinja2Templates(directory=BASE_DIR / "ui" / "templates")


class CandidateChatRequest(BaseModel):
    history: list[dict[str, str]] = Field(default_factory=list)
    message: str | None = None


class TeamGenerationRequest(BaseModel):
    project_name: str
    role: str
    team_size: int


class LoginRequest(BaseModel):
    username: str
    password: str


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    token = (
        credentials.credentials if credentials else request.cookies.get("access_token")
    )

    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token.")

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


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")


@app.post("/login")
def login(payload: LoginRequest):
    result = login_user(payload.username, payload.password)

    if not result["success"]:
        raise HTTPException(status_code=401, detail=result["message"])

    response = JSONResponse(content=result)
    response.set_cookie(
        key="access_token",
        value=result["access_token"],
        httponly=True,
        samesite="lax",
        path="/",
    )

    return response


@app.get("/candidate/chat.html", response_class=HTMLResponse)
async def candidate_chat_page(
    request: Request, _user=Depends(require_role("candidate"))
):
    return templates.TemplateResponse(
        request=request,
        name="candidate/chat.html",
        context={"project_options": get_project_names()},
    )


@app.post("/api/chat")
async def chat(req: CandidateChatRequest, _user=Depends(require_role("candidate"))):
    try:
        result = candidate_chatbot(history=req.history, candidate_answer=req.message)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return result


@app.get("/recruiter/dashboard.html", response_class=HTMLResponse)
async def recruiter_dashboard(
    request: Request, _user=Depends(require_role("recruiter"))
):
    candidates = [
        {"name": "Anna", "role": "Frontend Developer"},
        {"name": "Jan", "role": "Backend Developer"},
    ]

    teams = [{"team_name": "Team Alpha", "score": 92}]

    return templates.TemplateResponse(
        request=request,
        name="recruiter/dashboard.html",
        context={"candidates": candidates, "teams": teams},
    )


@app.get("/recruiter/generator.html", response_class=HTMLResponse)
async def generator_page(request: Request, _user=Depends(require_role("recruiter"))):
    return templates.TemplateResponse(
        request=request,
        name="recruiter/generator.html",
        context={"project_options": get_candidate_project_names()},
    )


@app.post("/recruiter/generator.html")
async def generator(
    data: TeamGenerationRequest,
    _user=Depends(require_role("recruiter")),
):
    try:
        teams = await run_in_threadpool(
            form_and_rank_teams,
            max_candidates_per_role=2,
            save_to_database=True,
            benchmark_limit=10,
            simulation_runs=5,
            project_name=data.project_name,
            include_team_map=True,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return teams


@app.get("/recruiter/reports.html", response_class=HTMLResponse)
async def recruiter_reports(request: Request, _user=Depends(require_role("recruiter"))):
    reports = [
        {
            "team": "Team Alpha",
            "compatibility": 92,
            "summary": ("Very good communication and cooperation."),
        },
        {
            "team": "Team Beta",
            "compatibility": 85,
            "summary": ("Strong technical skills."),
        },
    ]

    return templates.TemplateResponse(
        request=request,
        name="recruiter/reports.html",
        context={"reports": reports},
    )


@app.get("/api/reports")
async def reports_api(_user=Depends(require_role("recruiter"))):
    reports = [{"team": "Team Alpha", "score": 92}, {"team": "Team Beta", "score": 85}]

    return {"reports": reports}


def parse_conversation_history(value):
    if not value:
        return []

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return []


@app.get("/api/results")
def get_results(_user=Depends(require_role("recruiter"))):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            first_name,
            surname,
            role,
            project_name,
            openness,
            conscientiousness,
            extraversion,
            agreeableness,
            neuroticism,
            conversation_history
        FROM candidate_personality_scores
        ORDER BY id ASC
    """)

    rows = cursor.fetchall()
    conn.close()

    results = []

    for row in rows:
        results.append(
            {
                "id": row[0],
                "name": f"{row[1]} {row[2]}",
                "role": row[3],
                "project_name": row[4],
                "personality": {
                    "openness": row[5],
                    "conscientiousness": row[6],
                    "extraversion": row[7],
                    "agreeableness": row[8],
                    "neuroticism": row[9],
                },
                "history": parse_conversation_history(row[10]),
            }
        )

    return JSONResponse(content=results)


if __name__ == "__main__":
    uvicorn.run("api.app:app", host="0.0.0.0", port=8000, reload=True)
