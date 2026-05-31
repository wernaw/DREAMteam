from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from pathlib import Path
from pydantic import BaseModel
import json
import sqlite3
import uvicorn

from api.services.chatbot import candidate_chatbot
from api.services.team_recommendation_service import form_and_rank_teams


BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = BASE_DIR / "api" / "dreamteam"

app = FastAPI()

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
    history: list
    message: str | None = None


class TeamGenerationRequest(BaseModel):
    project_name: str
    role: str
    team_size: int


# logowanie
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")


# rozmowa z kandydatem
@app.get("/candidate/chat.html", response_class=HTMLResponse)
async def candidate_chat_page(request: Request):
    return templates.TemplateResponse(request=request, name="candidate/chat.html")


@app.post("/api/chat")
async def chat(req: CandidateChatRequest):
    result = candidate_chatbot(history=req.history, candidate_answer=req.message)

    return result


# panel rekrutera


@app.get("/recruiter/dashboard.html", response_class=HTMLResponse)
async def recruiter_dashboard(request: Request):
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
async def generator_page(request: Request):
    return templates.TemplateResponse(request=request, name="recruiter/generator.html")


@app.post("/recruiter/generator.html")
async def generator(data: TeamGenerationRequest):
    teams = form_and_rank_teams()

    return {"teams": teams}


@app.get("/recruiter/reports.html", response_class=HTMLResponse)
async def recruiter_reports(request: Request):
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
async def reports_api():
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
def get_results():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            first_name,
            surname,
            role,
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
                "personality": {
                    "openness": row[4],
                    "conscientiousness": row[5],
                    "extraversion": row[6],
                    "agreeableness": row[7],
                    "neuroticism": row[8],
                },
                "history": parse_conversation_history(row[9]),
            }
        )

    return JSONResponse(content=results)


if __name__ == "__main__":
    uvicorn.run("api.app:app", host="0.0.0.0", port=8000, reload=True)
