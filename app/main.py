from fastapi import FastAPI

app = FastAPI(title="TTRPG Rules Assistant")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
