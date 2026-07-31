from dataclasses import dataclass

from app.ingestion.parser import ParsedElement


@dataclass
class Chunk:
    content: str
    page_number: int | None
    is_table: bool


def chunk_elements(
    elements: list[ParsedElement], max_chars: int = 1500, overlap_chars: int = 200
) -> list[Chunk]:
    chunks: list[Chunk] = []
    buffer_texts: list[str] = []
    buffer_page: int | None = None
    buffer_len = 0

    def flush() -> None:
        nonlocal buffer_texts, buffer_page, buffer_len
        if not buffer_texts:
            return
        chunks.append(Chunk(content="\n\n".join(buffer_texts), page_number=buffer_page, is_table=False))
        buffer_texts = []
        buffer_page = None
        buffer_len = 0

    for element in elements:
        if element.category == "Table":
            flush()
            chunks.append(Chunk(content=element.text, page_number=element.page_number, is_table=True))
            continue

        if buffer_len + len(element.text) > max_chars and buffer_texts:
            previous_content = "\n\n".join(buffer_texts)
            flush()
            overlap_text = previous_content[-overlap_chars:]
            buffer_texts.append(overlap_text)
            buffer_page = element.page_number
            buffer_len = len(overlap_text)

        if buffer_page is None:
            buffer_page = element.page_number
        buffer_texts.append(element.text)
        buffer_len += len(element.text)

    flush()
    return chunks
