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
from api.services.team_performance_simulator_openai import (
    ensure_team_score_extra_columns,
    form_and_rank_teams,
    save_team_score_to_database,
)
from api.services.database import DATABASE_PATH
from api.services.project_service import get_candidate_project_names, get_project_names
from api.services.auth_service import decode_access_token, login_user


BASE_DIR = Path(__file__).resolve().parent.parent

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


class SaveTeamsRequest(BaseModel):
    teams: list


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


@app.post("/logout")
def logout():
    response = JSONResponse(content={"success": True})
    response.delete_cookie(
        key="access_token",
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
    return templates.TemplateResponse(
        request=request,
        name="recruiter/dashboard.html",
    )


def parse_team_member_ids(value):
    try:
        member_ids = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []

    return member_ids if isinstance(member_ids, list) else []


def get_latest_teams_from_database(limit):
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        cursor = connection.cursor()
        ensure_team_score_extra_columns(cursor)
        connection.commit()
        cursor.execute(
            """
            SELECT generation_id
            FROM team_score
            WHERE generation_id IS NOT NULL
              AND generation_id != ''
            ORDER BY id DESC
            LIMIT 1
            """
        )
        latest_generation = cursor.fetchone()

        if latest_generation is None:
            return []

        cursor.execute(
            """
            SELECT
                id,
                team_member_ids,
                performance_score,
                project_name,
                rank_position,
                generation_id,
                generation_created_at
            FROM team_score
            WHERE generation_id = ?
            ORDER BY rank_position ASC, performance_score DESC, id ASC
            LIMIT ?
            """,
            (latest_generation["generation_id"], limit),
        )
        team_rows = cursor.fetchall()
        member_ids = [
            member_id
            for row in team_rows
            for member_id in parse_team_member_ids(row["team_member_ids"])
        ]

        candidates_by_id = {}

        if member_ids:
            placeholders = ", ".join("?" for _ in member_ids)
            cursor.execute(
                f"""
                SELECT id, first_name, surname, role, project_name
                FROM candidate_personality_scores
                WHERE id IN ({placeholders})
                """,
                member_ids,
            )
            candidates_by_id = {
                row["id"]: {
                    "id": row["id"],
                    "name": f"{row['first_name']} {row['surname']}",
                    "role": row["role"],
                    "project_name": row["project_name"],
                }
                for row in cursor.fetchall()
            }

        return [
            {
                "team_score_id": row["id"],
                "project_name": row["project_name"],
                "generation_id": row["generation_id"],
                "generation_created_at": row["generation_created_at"],
                "performance_score": row["performance_score"],
                "rank_position": row["rank_position"],
                "team_members": [
                    candidates_by_id[member_id]
                    for member_id in parse_team_member_ids(row["team_member_ids"])
                    if member_id in candidates_by_id
                ],
            }
            for row in team_rows
        ]
    finally:
        connection.close()


@app.get("/api/teams")
def get_teams(
    limit: int = 1,
    _user=Depends(require_role("recruiter")),
):
    if limit not in (1, 3):
        raise HTTPException(status_code=400, detail="Limit must be 1 or 3.")

    return get_latest_teams_from_database(limit)


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
            save_to_database=False,
            benchmark_limit=10,
            simulation_runs=5,
            project_name=data.project_name,
            include_team_map=True,
        )

        print("GENERATED TEAMS")
        print(type(teams))
        print(teams)

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return teams


@app.post("/api/save-teams")
async def save_teams(
    payload: SaveTeamsRequest, _user=Depends(require_role("recruiter"))
):
    if not payload.teams:
        raise HTTPException(status_code=400, detail="No teams to save.")

    saved_team_ids = []

    try:
        for team in payload.teams:
            team_result = {
                **team,
                "team": team.get("team") or team.get("team_members", []),
            }
            saved_team_ids.append(save_team_score_to_database(team_result))
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail="Invalid team data.") from error

    return {"success": True, "team_score_ids": saved_team_ids}


@app.get("/recruiter/reports.html", response_class=HTMLResponse)
async def recruiter_reports(request: Request, _user=Depends(require_role("recruiter"))):
    return templates.TemplateResponse(
        request=request,
        name="recruiter/reports.html",
    )


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


@app.get("/api/candidates")
def get_candidates(_user=Depends(require_role("recruiter"))):

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            first_name,
            surname,
            role,
            openness,
            conscientiousness,
            extraversion,
            agreeableness,
            neuroticism
        FROM candidate_personality_scores
    """)

    rows = cursor.fetchall()
    conn.close()

    candidates = []

    for row in rows:
        candidates.append(
            {
                "name": f"{row[0]} {row[1]}",
                "role": row[2],
                "personality": {
                    "openness": row[3],
                    "conscientiousness": row[4],
                    "extraversion": row[5],
                    "agreeableness": row[6],
                    "neuroticism": row[7],
                },
            }
        )

    return candidates


if __name__ == "__main__":
    uvicorn.run("api.app:app", host="0.0.0.0", port=8000, reload=True)
