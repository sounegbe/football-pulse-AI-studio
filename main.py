from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles


app = FastAPI()


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