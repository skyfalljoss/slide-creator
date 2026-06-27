from io import BytesIO
from zipfile import BadZipFile, ZipFile

from pptx import Presentation

# ZIP expansion bounds: scale larger uploads while keeping practical floors for
# normal image-heavy presentations produced by SlideForge.
MAX_ZIP_MEMBERS = 10_000
ZIP_MEMBER_SIZE_FLOOR = 10_000_000
ZIP_TOTAL_SIZE_FLOOR = 50_000_000
ZIP_TOTAL_SIZE_MULTIPLIER = 5
MAX_ZIP_COMPRESSION_RATIO = 100


class InvalidPptxError(ValueError):
    pass


def _validate_zip_resources(package: ZipFile, max_bytes: int) -> None:
    members = package.infolist()
    if len(members) > MAX_ZIP_MEMBERS:
        raise InvalidPptxError("PPTX has too many ZIP members")

    max_member_bytes = max(max_bytes, ZIP_MEMBER_SIZE_FLOOR)
    max_total_bytes = max(max_bytes * ZIP_TOTAL_SIZE_MULTIPLIER, ZIP_TOTAL_SIZE_FLOOR)
    total_bytes = 0
    for member in members:
        if member.file_size > max_member_bytes:
            raise InvalidPptxError("PPTX ZIP member exceeds size limit")
        total_bytes += member.file_size
        if total_bytes > max_total_bytes:
            raise InvalidPptxError("PPTX ZIP expands beyond size limit")
        if member.file_size > 0 and (
            member.compress_size == 0
            or member.file_size > member.compress_size * MAX_ZIP_COMPRESSION_RATIO
        ):
            raise InvalidPptxError("PPTX ZIP member compression ratio exceeds limit")


def validate_pptx(content: bytes, max_bytes: int) -> None:
    if len(content) > max_bytes:
        raise InvalidPptxError("PPTX exceeds maximum size")
    if not content.startswith(b"PK"):
        raise InvalidPptxError("PPTX is not a ZIP/OpenXML package")

    try:
        with ZipFile(BytesIO(content)) as package:
            _validate_zip_resources(package, max_bytes)
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
        presentation = Presentation(BytesIO(content))
    except Exception as exc:
        raise InvalidPptxError("PPTX cannot be opened as a presentation") from exc
    if len(presentation.slides) == 0:
        raise InvalidPptxError("PPTX contains no presentation slides")
