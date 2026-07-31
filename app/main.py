from fastapi import FastAPI

from app.routes.chat import router as chat_router
from app.routes.documents import router as documents_router
from app.routes.systems import router as systems_router

app = FastAPI(title="TTRPG Rules Assistant")
app.include_router(systems_router)
app.include_router(documents_router)
app.include_router(chat_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
