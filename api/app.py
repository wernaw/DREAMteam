from fastapi import FastAPI, Request 
from fastapi.responses import HTMLResponse 
from fastapi.staticfiles import StaticFiles 
from fastapi.templating import Jinja2Templates 
from pydantic import BaseModel 
from services.chatbot import candidate_chatbot
from services.team_recommendation_service import format_top_teams

app = FastAPI() 

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")



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
    
    return templates.TemplateResponse( 
        "login.html",
        {"request": request} 
    )


# rozmowa z kandydatem
@app.get("/candidate/chat.html", response_class=HTMLResponse) 
async def candidate_chat_page(request: Request): 
    
    return templates.TemplateResponse( 
        "/candidate/chat.html", 
        {"request": request} 
    )



@app.post("/api/chat.html")
async def chat(req: CandidateChatRequest):

    result = candidate_chatbot(
        history=req.history,
        candidate_answer=req.message
    )

    return result



# panel rekrutera

@app.get("/recruiter/dashboard.html", response_class=HTMLResponse)
async def recruiter_dashboard(request: Request):

    candidates = [
        {
            "name": "Anna",
            "role": "Frontend Developer"
        },
        {
            "name": "Jan",
            "role": "Backend Developer"
        }
    ]

    teams = [
        {
            "team_name": "Team Alpha",
            "score": 92
        }
    ]

    return templates.TemplateResponse(
        "/recruiter/dashboard.html",
        {
            "request": request,
            "candidates": candidates,
            "teams": teams
        }
    )


@app.get("/recruiter/generator.html", response_class=HTMLResponse)
async def generator_page(request: Request):

    return templates.TemplateResponse(
        "/recruiter/generator.html",
        {"request": request}
    )


@app.post("/recruiter/generator.html")
async def generator(data: TeamGenerationRequest):

    teams = format_top_teams(
        project_name=data.project_name,
        role=data.role
    )

    return {"teams": teams}


@app.get( "/recruiter/reports.html", response_class=HTMLResponse ) 
async def recruiter_reports(request: Request): 
    
    reports = [ 
        { 
            "team": "Team Alpha", 
            "compatibility": 92, 
            "summary": ( 
                "Very good communication " "and cooperation." 
            ) 
        }, 
        { 
            "team": "Team Beta", 
            "compatibility": 85, 
            "summary": (
                 "Strong technical skills." 
                 ) 
        } 
    ] 
    
    return templates.TemplateResponse( 
        "/recruiter/reports.html", 
        {"request": request, "reports": reports} 
    )

@app.get("/recruiter/reports.html")
async def reports_api():

    reports = [
        {
            "team": "Team Alpha",
            "score": 92
        },
        {
            "team": "Team Beta",
            "score": 85
        }
    ]

    return {
        "reports": reports
    }



if __name__ == "__main__":
    
    import uvicorn

    uvicorn.run(
        "api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
