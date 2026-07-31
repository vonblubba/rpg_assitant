from app.ingestion.chunker import chunk_elements
from app.ingestion.parser import ParsedElement


def test_table_element_becomes_single_whole_chunk():
    elements = [
        ParsedElement(text="Intro text.", category="NarrativeText", page_number=1),
        ParsedElement(text="| Weapon | Damage |\n| Longsword | 1d8 |", category="Table", page_number=2),
        ParsedElement(text="More text.", category="NarrativeText", page_number=3),
    ]

    chunks = chunk_elements(elements, max_chars=1000, overlap_chars=50)

    table_chunks = [c for c in chunks if c.is_table]
    assert len(table_chunks) == 1
    assert table_chunks[0].content == elements[1].text
    assert table_chunks[0].page_number == 2


def test_large_table_is_never_split():
    huge_table_text = "| Col |\n" + "\n".join(f"| row{i} |" for i in range(500))
    elements = [ParsedElement(text=huge_table_text, category="Table", page_number=1)]

    chunks = chunk_elements(elements, max_chars=100, overlap_chars=20)

    assert len(chunks) == 1
    assert chunks[0].content == huge_table_text


def test_prose_splits_when_exceeding_max_chars_with_overlap():
    elements = [
        ParsedElement(text="A" * 60, category="NarrativeText", page_number=1),
        ParsedElement(text="B" * 60, category="NarrativeText", page_number=1),
        ParsedElement(text="C" * 60, category="NarrativeText", page_number=2),
    ]

    chunks = chunk_elements(elements, max_chars=100, overlap_chars=20)

    assert len(chunks) >= 2
    assert all(not c.is_table for c in chunks)
    assert chunks[0].content[-20:] in chunks[1].content
