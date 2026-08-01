import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5433/rpg_assistant_test")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")

# The db_session fixture below calls Base.metadata.drop_all() after every test.
# setdefault() above is a no-op if DATABASE_URL is already set in the environment
# (e.g. inherited from docker-compose's app service, which points at the real dev
# database) -- in that case tests would silently drop_all() production data. Refuse
# to proceed unless the configured database is clearly a test database.
_database_url = os.environ["DATABASE_URL"]
_database_name = _database_url.rsplit("/", 1)[-1]
if "test" not in _database_name.lower():
    raise RuntimeError(
        f"Refusing to run tests against DATABASE_URL={_database_url!r}: the database "
        f"name {_database_name!r} does not look like a test database (no 'test' in "
        "the name). The db_session fixture destroys all data in this database. If "
        "you're running tests inside the app container via `docker exec`, the "
        "container's DATABASE_URL env var is overriding the test default -- run "
        "tests against a dedicated test database instead."
    )

import pytest
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

from app.db import Base, engine


@pytest.fixture
def db_session():
    from app.db import SessionLocal
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def plain_pdf_path(tmp_path):
    path = tmp_path / "plain.pdf"
    doc = SimpleDocTemplate(str(path))
    styles = getSampleStyleSheet()
    doc.build(
        [
            Paragraph(
                "A fighter is a master of martial combat, skilled with a variety "
                "of weapons and armor. Fighters learn the basics of all combat "
                "styles.",
                styles["Normal"],
            )
        ]
    )
    return str(path)


@pytest.fixture
def table_pdf_path(tmp_path):
    path = tmp_path / "table.pdf"
    doc = SimpleDocTemplate(str(path))
    data = [
        ["Weapon", "Damage", "Weight"],
        ["Longsword", "1d8", "3 lb"],
        ["Dagger", "1d4", "1 lb"],
    ]
    # Sized generously (wide columns, tall rows, large font) so that
    # unstructured's hi-res table-structure OCR model reliably recognizes
    # cell text; a tightly-packed default-sized table is prone to OCR
    # misreads on this synthetic single-table page.
    table = Table(data, colWidths=[3 * inch, 2.5 * inch, 2.5 * inch], rowHeights=[0.6 * inch] * 3)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("FONTSIZE", (0, 0), (-1, -1), 18),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    doc.build([table])
    return str(path)
