from fastapi import FastAPI

from .routers import packages

app = FastAPI()
app.include_router(packages.router)


@app.get("/", tags=['Home'])
async def home():
    return {"message": "This is the home-page of VPTAN. Try the endpoint /packages to get package-files"}