from fastapi import FastAPI


app = FastAPI()


@app.get("/")
def welcome_root():
    return {"message": "Welcome to the DREAMteam!"}
