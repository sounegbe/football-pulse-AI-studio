from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


app = FastAPI()


class GenerateRequest(BaseModel):
    news: str
    content_type: str

app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static"
)


@app.get("/", response_class=HTMLResponse)
def home():

    with open("app/templates/index.html") as file:
        html_content = file.read()

    return html_content


@app.post("/api/generate")
def generate_content(request: GenerateRequest):

    return {
        "content": "Test response from Football Pulse AI Studio.",
        "content_type": request.content_type
    }