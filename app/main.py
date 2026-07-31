from fastapi import FastAPI

from app.routes.systems import router as systems_router

app = FastAPI(title="TTRPG Rules Assistant")
app.include_router(systems_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
