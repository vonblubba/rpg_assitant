import asyncio

from app.db import SessionLocal
from app.ingestion.chunker import chunk_elements
from app.ingestion.parser import parse_pdf
from app.models import Chunk, Document
from app.ollama_client import embed_text


async def ingest_document(document_id: int, file_path: str) -> None:
    db = SessionLocal()
    try:
        document = await asyncio.to_thread(db.get, Document, document_id)
        if document is None:
            return

        document.status = "processing"
        # Capture attributes needed after the commit below, since the default
        # session config (expire_on_commit=True) expires ALL mapped attributes
        # on commit -- including primary keys, not just non-PK columns.
        # Re-reading document.game_system_id or document.id afterward would
        # trigger an implicit, synchronous SELECT on the event-loop thread.
        game_system_id = document.game_system_id
        document_id_val = document.id
        await asyncio.to_thread(db.commit)

        try:
            elements = await asyncio.to_thread(parse_pdf, file_path)
            chunks = await asyncio.to_thread(chunk_elements, elements)
            if not chunks:
                raise ValueError("No content could be extracted from this PDF")

            for chunk in chunks:
                embedding = await embed_text(chunk.content)
                db.add(
                    Chunk(
                        document_id=document_id_val,
                        game_system_id=game_system_id,
                        content=chunk.content,
                        page_number=chunk.page_number,
                        embedding=embedding,
                    )
                )
            document.status = "ready"
            await asyncio.to_thread(db.commit)
        except Exception as exc:
            await asyncio.to_thread(db.rollback)
            await asyncio.to_thread(
                lambda: db.query(Chunk).filter(Chunk.document_id == document_id_val).delete()
            )
            document.status = "failed"
            document.error_message = str(exc)
            await asyncio.to_thread(db.commit)
    finally:
        db.close()
