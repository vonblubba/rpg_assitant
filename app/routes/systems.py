from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import GameSystem
from app.schemas import GameSystemCreate, GameSystemOut

router = APIRouter(prefix="/systems", tags=["systems"])


@router.post("", response_model=GameSystemOut, status_code=201)
def create_system(payload: GameSystemCreate, db: Session = Depends(get_db)) -> GameSystem:
    system = GameSystem(name=payload.name)
    db.add(system)
    db.commit()
    db.refresh(system)
    return system


@router.get("", response_model=list[GameSystemOut])
def list_systems(db: Session = Depends(get_db)) -> list[GameSystem]:
    return db.query(GameSystem).order_by(GameSystem.created_at).all()


@router.delete("/{system_id}", status_code=204)
def delete_system(system_id: int, db: Session = Depends(get_db)) -> None:
    system = db.get(GameSystem, system_id)
    if system is None:
        raise HTTPException(status_code=404, detail="Game system not found")
    db.delete(system)
    db.commit()
