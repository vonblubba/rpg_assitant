import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.ingestion.pipeline import ingest_document
from app.models import Document, GameSystem
from app.schemas import DocumentOut

router = APIRouter(prefix="/systems/{system_id}/documents", tags=["documents"])

UPLOAD_DIR = Path(tempfile.gettempdir()) / "rpg-assistant-uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("", response_model=DocumentOut, status_code=201)
def upload_document(
    system_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile,
    db: Session = Depends(get_db),
) -> Document:
    system = db.get(GameSystem, system_id)
    if system is None:
        raise HTTPException(status_code=404, detail="Game system not found")

    document = Document(game_system_id=system_id, filename=file.filename, status="pending")
    db.add(document)
    db.commit()
    db.refresh(document)

    dest_path = UPLOAD_DIR / f"{document.id}_{file.filename}"
    with dest_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    background_tasks.add_task(ingest_document, document.id, str(dest_path))

    return document


@router.get("", response_model=list[DocumentOut])
def list_documents(system_id: int, db: Session = Depends(get_db)) -> list[Document]:
    return (
        db.query(Document)
        .filter(Document.game_system_id == system_id)
        .order_by(Document.uploaded_at)
        .all()
    )


@router.delete("/{document_id}", status_code=204)
def delete_document(system_id: int, document_id: int, db: Session = Depends(get_db)) -> None:
    document = db.get(Document, document_id)
    if document is None or document.game_system_id != system_id:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(document)
    db.commit()
