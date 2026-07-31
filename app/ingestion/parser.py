from dataclasses import dataclass

from markdownify import markdownify
from unstructured.partition.pdf import partition_pdf


@dataclass
class ParsedElement:
    text: str
    category: str
    page_number: int | None


def parse_pdf(path: str) -> list[ParsedElement]:
    elements = partition_pdf(filename=path, strategy="hi_res", infer_table_structure=True)
    parsed: list[ParsedElement] = []
    for element in elements:
        if element.category == "Table" and getattr(element.metadata, "text_as_html", None):
            text = markdownify(element.metadata.text_as_html).strip()
        else:
            text = str(element).strip()
        if not text:
            continue
        parsed.append(
            ParsedElement(
                text=text,
                category=element.category,
                page_number=element.metadata.page_number,
            )
        )
    return parsed
