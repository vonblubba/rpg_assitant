from app.db import SessionLocal
from app.ingestion.chunker import chunk_elements
from app.ingestion.parser import parse_pdf
from app.models import Chunk, Document
from app.ollama_client import embed_text


async def ingest_document(document_id: int, file_path: str) -> None:
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            return

        document.status = "processing"
        db.commit()

        try:
            elements = parse_pdf(file_path)
            chunks = chunk_elements(elements)
            if not chunks:
                raise ValueError("No content could be extracted from this PDF")

            for chunk in chunks:
                embedding = await embed_text(chunk.content)
                db.add(
                    Chunk(
                        document_id=document.id,
                        game_system_id=document.game_system_id,
                        content=chunk.content,
                        page_number=chunk.page_number,
                        embedding=embedding,
                    )
                )
            document.status = "ready"
            db.commit()
        except Exception as exc:
            db.rollback()
            db.query(Chunk).filter(Chunk.document_id == document.id).delete()
            document.status = "failed"
            document.error_message = str(exc)
            db.commit()
    finally:
        db.close()
