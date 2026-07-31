from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import GameSystem

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
def systems_page(request: Request, db: Session = Depends(get_db)):
    systems = db.query(GameSystem).order_by(GameSystem.created_at).all()
    return templates.TemplateResponse(request, "systems.html", {"systems": systems})


@router.get("/systems/{system_id}")
def system_detail_page(system_id: int, request: Request, db: Session = Depends(get_db)):
    system = db.get(GameSystem, system_id)
    if system is None:
        raise HTTPException(status_code=404, detail="Game system not found")
    return templates.TemplateResponse(request, "system_detail.html", {"system": system})


@router.get("/systems/{system_id}/chat")
def chat_page(system_id: int, request: Request, db: Session = Depends(get_db)):
    system = db.get(GameSystem, system_id)
    if system is None:
        raise HTTPException(status_code=404, detail="Game system not found")
    return templates.TemplateResponse(request, "chat.html", {"system": system})
