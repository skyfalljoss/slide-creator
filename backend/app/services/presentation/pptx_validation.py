from io import BytesIO
from zipfile import BadZipFile, ZipFile

from pptx import Presentation


class InvalidPptxError(ValueError):
    pass


def validate_pptx(content: bytes, max_bytes: int) -> None:
    if len(content) > max_bytes:
        raise InvalidPptxError("PPTX exceeds maximum size")
    if not content.startswith(b"PK"):
        raise InvalidPptxError("PPTX is not a ZIP/OpenXML package")

    try:
        with ZipFile(BytesIO(content)) as package:
            names = set(package.namelist())
    except (BadZipFile, OSError) as exc:
        raise InvalidPptxError("PPTX is not readable") from exc

    if "[Content_Types].xml" not in names:
        raise InvalidPptxError("PPTX is missing [Content_Types].xml")
    if "ppt/presentation.xml" not in names:
        raise InvalidPptxError("PPTX is missing ppt/presentation.xml")
    if not any(name.startswith("ppt/slides/slide") and name.endswith(".xml") for name in names):
        raise InvalidPptxError("PPTX contains no slide XML parts")

    try:
        Presentation(BytesIO(content))
    except Exception as exc:
        raise InvalidPptxError("PPTX cannot be opened as a presentation") from exc
