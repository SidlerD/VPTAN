from fastapi import FastAPI

from .routers import packages

app = FastAPI()
app.include_router(packages.router)


@app.get("/")
async def root():
    return {"message": "This is the home-page of VPTAN. Try the endpoint /packages to get package-files"}