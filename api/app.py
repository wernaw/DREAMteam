from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from pathlib import Path
import sqlite3
import json
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = BASE_DIR / "dreamteam.db"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/api/static", StaticFiles(directory="api/static"), name="static")

templates = Jinja2Templates(directory="api/templates")


class ChatRequest(BaseModel):
    history: list
    message: str | None = None


def process_candidate_chat(history: list, message: str | None):
    # do podpięcia

    return {
        "reply": f"Message: {message}",
        "history_length": len(history)
    }


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )

@app.post("/")
async def login(role: str = Form(...)):
    if role == "candidate":
        return RedirectResponse(
            url="/candidate/chat.html",
            status_code=303
        )
    elif role == "recruiter":
        return RedirectResponse(
            url="/recruiter/dashboard.html",
            status_code=303
        )

    return RedirectResponse(url="/", status_code=303)


@app.get("/candidate/chat.html", response_class=HTMLResponse)
async def candidate_chat(request: Request):
    return templates.TemplateResponse(
        "candidate/chat.html",
        {"request": request}
    )


@app.get("/recruiter/dashboard.html", response_class=HTMLResponse)
async def recruiter_dashboard(request: Request):
    return templates.TemplateResponse(
        "recruiter/dashboard.html",
        {"request": request}
    )


@app.get("/recruiter/generator.html", response_class=HTMLResponse)
async def recruiter_generator(request: Request):
    return templates.TemplateResponse(
        "recruiter/generator.html",
        {"request": request}
    )


@app.get("/recruiter/reports.html", response_class=HTMLResponse)
async def recruiter_reports(request: Request):
    return templates.TemplateResponse(
        "recruiter/reports.html",
        {"request": request}
    )


@app.post("/api/chat")
def chat(req: ChatRequest):
    result = process_candidate_chat(
        history=req.history,
        message=req.message
    )

    return JSONResponse(content=result)


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
        ORDER BY id DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    results = []

    for row in rows:
        results.append({
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
            "history": json.loads(row[9]) if row[9] else []
        })

    return JSONResponse(content=results)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
