from fastapi import FastAPI
import uvicorn

from app.routers import packages, alias

app = FastAPI()
app.include_router(packages.router)
app.include_router(alias.router)


@app.get("/", tags=['home'])
async def home():
    return {"message": "This is the home-page of VPTAN. Try the endpoint /packages to get package-files"}

# Run application
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
