from app.ingestion.parser import parse_pdf


def test_parse_pdf_extracts_prose_text(plain_pdf_path):
    elements = parse_pdf(plain_pdf_path)

    assert len(elements) > 0
    assert any("master of martial combat" in el.text for el in elements)
    assert all(el.page_number == 1 for el in elements)


def test_parse_pdf_extracts_table_as_table_category(table_pdf_path):
    elements = parse_pdf(table_pdf_path)

    table_elements = [el for el in elements if el.category == "Table"]
    assert len(table_elements) == 1
    assert "Longsword" in table_elements[0].text
