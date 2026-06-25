# PRD Backend Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the backend gaps between `PRD.html` and the current FastAPI implementation while keeping local development deterministic and cloud-provider adapters optional.

**Architecture:** Keep the existing API contract stable for the frontend and add missing backend capabilities behind focused services. Implement local-first file parsing, chart planning, PPTX chart/notes/branding, cleanup, audit metadata, and provider interfaces, then leave real Vertex/DLP/GCS/Splunk/SSO integration behind explicit config gates.

**Tech Stack:** FastAPI, Pydantic 2, pytest, httpx ASGITransport, python-pptx, python-multipart, uv, ruff, optional `openpyxl` for `.xlsx` parsing.

---

## PRD Gap Audit

Covered or mostly covered in current backend:

- `FR-001` prompt max length: `GenerateRequest.prompt` enforces max length.
- `FR-002` deck type selector: `deck_type` is constrained to `sales_9` and `internal_6`.
- `FR-003` structured slide JSON: current local generator returns `SlideData` JSON with title, bullets, notes, layout.
- `FR-005` PPTX export: backend generates PPTX bytes and returns a local download URL.
- `FR-008` refine slide: endpoint exists and updates one slide.
- `FR-009` basic compliance filter: local lexicon scan runs pre/post generation and refinement.
- `US-07` no prompt content in audit logs: current audit service stores metadata only.

Missing or incomplete backend requirements:

- `US-02` / `FR-006`: no CSV/XLSX upload endpoint, no file parsing, no `file_id` resolution.
- `FR-007`: `chart_data` exists but there is no chart data schema, chart planner, or python-pptx chart rendering.
- `US-03` / `FR-004`: PPTX branding is minimal; no fixed Citi logo, no consistent header band, no enforced Arial/Calibri font styling across generated shapes.
- `US-04`: final disclaimer exists, but there is no standard risk disclosure text model and no test asserting it appears in the generated PPTX.
- `US-08`: notes exist in JSON, but they are not written into PPTX speaker notes.
- `US-09`: no logo lockup/header asset handling.
- `US-10` / `FR-010`: audit events do not include user, model, token counts, retention-target semantics, or a Splunk adapter boundary.
- `PRD Security`: no Cloud DLP adapter seam for PII/account-like patterns; local scanner only covers prohibited phrases.
- `PRD Privacy`: generated local export files are not auto-deleted after expiry.
- `PRD Architecture`: provider seams are only partial; no explicit Vertex/GCS/DLP/Splunk adapter factory.
- `US-06`: no SSO enforcement or mock-auth middleware; should remain local mock unless Citi SAML details are provided.

Inputs needed from the user before production fidelity:

- Citi PowerPoint master `.potx` file.
- Citi logo asset for PPTX lockup, preferably `.png` with transparent background.
- Approved standard risk disclosure text.
- GCP project, region, service account strategy, bucket name, and whether Vertex should use `gemini-1.5-pro` or a newer approved model.
- Splunk HEC endpoint/token or an agreed local file sink for audit testing.
- SSO details only if implementing real SAML/OIDC instead of local mock auth.

## File Structure

- Create: `backend/app/routers/uploads.py` for `POST /api/v1/uploads`.
- Create: `backend/app/services/uploads.py` for local CSV/XLSX persistence and parsing.
- Create: `backend/app/services/charts.py` for chart data normalization and chart type selection.
- Create: `backend/app/services/providers.py` for local/cloud provider factories.
- Create: `backend/app/services/auth.py` for local mock user extraction and future SSO seam.
- Modify: `backend/app/models/schemas.py` for upload, chart, and audit metadata schemas.
- Modify: `backend/app/config.py` for upload limits, allowed file types, temp file TTL, and adapter settings.
- Modify: `backend/app/main.py` to include the upload route.
- Modify: `backend/app/services/gemini.py` to consume parsed upload summaries and produce chart-ready slides.
- Modify: `backend/app/services/dlp.py` to add local account/PII-like pattern detection and a Cloud DLP adapter seam.
- Modify: `backend/app/services/pptx_engine.py` to render charts, speaker notes, header/logo, fonts, and tested disclaimer text.
- Modify: `backend/app/services/storage.py` to track expiry and delete expired local exports.
- Modify: `backend/app/services/audit.py` to include user/model/token metadata without content.
- Modify: `backend/app/routers/generate.py`, `backend/app/routers/refine.py`, and `backend/app/routers/export.py` to pass user/audit/file/chart context.
- Add/modify tests in `backend/tests/` for every new behavior.

## Tasks

### Task 1: Upload Schema and Local Upload Service

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/models/schemas.py`
- Create: `backend/app/services/uploads.py`
- Create: `backend/tests/test_uploads.py`

- [ ] **Step 1: Write failing tests for CSV upload parsing**

Add this to `backend/tests/test_uploads.py`:

```python
from app.services.uploads import UploadService


def test_save_csv_returns_file_id_and_summary(tmp_path):
    service = UploadService(upload_dir=tmp_path)
    content = b"quarter,revenue\nQ1,100\nQ2,125\n"

    result = service.save_upload(filename="revenue.csv", content=content)

    assert result.file_id.endswith(".csv")
    assert result.filename == "revenue.csv"
    assert result.row_count == 2
    assert result.columns == ["quarter", "revenue"]
    assert "Q1" in result.preview
    assert service.get_summary(result.file_id).row_count == 2
```

- [ ] **Step 2: Run the failing upload test**

Run from `backend/`:

```bash
uv run pytest tests/test_uploads.py::test_save_csv_returns_file_id_and_summary -v
```

Expected: fail with `ModuleNotFoundError: No module named 'app.services.uploads'`.

- [ ] **Step 3: Add upload settings and schemas**

In `backend/app/config.py`, add:

```python
    local_upload_dir: str = ".uploads"
    max_upload_bytes: int = 5_000_000
    allowed_upload_extensions: list[str] = [".csv", ".xlsx"]
```

In `backend/app/models/schemas.py`, add:

```python
class UploadResponse(BaseModel):
    file_id: str
    filename: str
    row_count: int
    columns: list[str]
    preview: str
```

- [ ] **Step 4: Implement local CSV parsing**

Create `backend/app/services/uploads.py`:

```python
import csv
import io
import uuid
from pathlib import Path

from app.config import settings
from app.models.schemas import UploadResponse


class UploadService:
    def __init__(self, upload_dir: str | Path | None = None):
        self.upload_dir = Path(upload_dir or settings.local_upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(self, *, filename: str, content: bytes) -> UploadResponse:
        suffix = Path(filename).suffix.lower()
        if suffix not in settings.allowed_upload_extensions:
            raise ValueError(f"Unsupported file type: {suffix}")
        if len(content) > settings.max_upload_bytes:
            raise ValueError("Upload exceeds maximum size")

        file_id = f"{uuid.uuid4()}{suffix}"
        path = self.upload_dir / file_id
        path.write_bytes(content)
        return self._summarize(file_id=file_id, filename=filename, content=content)

    def get_summary(self, file_id: str) -> UploadResponse:
        if Path(file_id).name != file_id:
            raise ValueError("Invalid file id")
        path = self.upload_dir / file_id
        if not path.exists():
            raise FileNotFoundError(file_id)
        return self._summarize(file_id=file_id, filename=file_id, content=path.read_bytes())

    def _summarize(self, *, file_id: str, filename: str, content: bytes) -> UploadResponse:
        suffix = Path(file_id).suffix.lower()
        if suffix == ".csv":
            text = content.decode("utf-8-sig")
            rows = list(csv.DictReader(io.StringIO(text)))
            columns = list(rows[0].keys()) if rows else []
            preview = "\n".join(text.splitlines()[:4])
            return UploadResponse(file_id=file_id, filename=filename, row_count=len(rows), columns=columns, preview=preview)
        raise ValueError(f"Unsupported file type: {suffix}")
```

- [ ] **Step 5: Verify upload service test passes**

Run from `backend/`:

```bash
uv run pytest tests/test_uploads.py::test_save_csv_returns_file_id_and_summary -v
```

Expected: pass.

### Task 2: Upload API Endpoint

**Files:**
- Create: `backend/app/routers/uploads.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing API test for file upload**

Add to `backend/tests/test_api.py`:

```python
@pytest.mark.asyncio
async def test_upload_csv(client: AsyncClient):
    resp = await client.post(
        "/api/v1/uploads",
        files={"file": ("revenue.csv", b"quarter,revenue\nQ1,100\n", "text/csv")},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["file_id"].endswith(".csv")
    assert data["row_count"] == 1
    assert data["columns"] == ["quarter", "revenue"]
```

- [ ] **Step 2: Run the failing API test**

Run from `backend/`:

```bash
uv run pytest tests/test_api.py::test_upload_csv -v
```

Expected: fail with `404 Not Found`.

- [ ] **Step 3: Implement upload router**

Create `backend/app/routers/uploads.py`:

```python
from fastapi import APIRouter, HTTPException, UploadFile

from app.models.schemas import UploadResponse
from app.services.uploads import UploadService


router = APIRouter()
uploads = UploadService()


@router.post("/uploads")
async def upload_file(file: UploadFile) -> UploadResponse:
    try:
        content = await file.read()
        return uploads.save_upload(filename=file.filename or "upload", content=content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 4: Include router in app**

In `backend/app/main.py`, change imports and router setup:

```python
from app.routers import generate, refine, export, uploads

app.include_router(uploads.router, prefix="/api/v1", tags=["uploads"])
```

- [ ] **Step 5: Verify upload endpoint passes**

Run from `backend/`:

```bash
uv run pytest tests/test_api.py::test_upload_csv -v
```

Expected: pass.

### Task 3: Chart Data Schema and Planner

**Files:**
- Modify: `backend/app/models/schemas.py`
- Create: `backend/app/services/charts.py`
- Create: `backend/tests/test_charts.py`

- [ ] **Step 1: Write failing chart planner test**

Create `backend/tests/test_charts.py`:

```python
from app.services.charts import ChartPlanner


def test_chart_planner_builds_bar_chart_from_numeric_csv_summary():
    planner = ChartPlanner()

    chart = planner.from_rows(
        rows=[{"quarter": "Q1", "revenue": "100"}, {"quarter": "Q2", "revenue": "125"}],
        title="Revenue by Quarter",
    )

    assert chart["type"] == "bar"
    assert chart["title"] == "Revenue by Quarter"
    assert chart["categories"] == ["Q1", "Q2"]
    assert chart["series"] == [{"name": "revenue", "values": [100.0, 125.0]}]
```

- [ ] **Step 2: Run the failing chart test**

Run from `backend/`:

```bash
uv run pytest tests/test_charts.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'app.services.charts'`.

- [ ] **Step 3: Add a chart planner**

Create `backend/app/services/charts.py`:

```python
class ChartPlanner:
    def from_rows(self, *, rows: list[dict[str, str]], title: str) -> dict | None:
        if not rows:
            return None
        columns = list(rows[0].keys())
        if len(columns) < 2:
            return None
        category_column = columns[0]
        numeric_column = columns[1]
        values: list[float] = []
        categories: list[str] = []
        for row in rows:
            try:
                values.append(float(row[numeric_column]))
            except (KeyError, TypeError, ValueError):
                return None
            categories.append(row.get(category_column, ""))
        return {
            "type": "bar",
            "title": title,
            "categories": categories,
            "series": [{"name": numeric_column, "values": values}],
        }
```

- [ ] **Step 4: Verify chart planner passes**

Run from `backend/`:

```bash
uv run pytest tests/test_charts.py -v
```

Expected: pass.

### Task 4: Wire Uploaded Data into Generation

**Files:**
- Modify: `backend/app/services/uploads.py`
- Modify: `backend/app/services/gemini.py`
- Modify: `backend/app/routers/generate.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing generate-with-file test**

Add to `backend/tests/test_api.py`:

```python
@pytest.mark.asyncio
async def test_generate_with_uploaded_csv_adds_chart_data(client: AsyncClient):
    upload = await client.post(
        "/api/v1/uploads",
        files={"file": ("revenue.csv", b"quarter,revenue\nQ1,100\nQ2,125\n", "text/csv")},
    )
    file_id = upload.json()["file_id"]

    resp = await client.post(
        "/api/v1/generate",
        json={"prompt": "Internal revenue analysis", "deck_type": "internal_6", "file_id": file_id},
    )

    assert resp.status_code == 200
    chart_slides = [slide for slide in resp.json()["slides"] if slide["chart_data"]]
    assert chart_slides
    assert chart_slides[0]["chart_data"]["categories"] == ["Q1", "Q2"]
```

- [ ] **Step 2: Run failing generate-with-file test**

Run from `backend/`:

```bash
uv run pytest tests/test_api.py::test_generate_with_uploaded_csv_adds_chart_data -v
```

Expected: fail because `file_id` is ignored.

- [ ] **Step 3: Add row parsing to upload service**

In `backend/app/services/uploads.py`, add:

```python
    def get_rows(self, file_id: str) -> list[dict[str, str]]:
        if Path(file_id).name != file_id:
            raise ValueError("Invalid file id")
        path = self.upload_dir / file_id
        if not path.exists():
            raise FileNotFoundError(file_id)
        suffix = path.suffix.lower()
        if suffix == ".csv":
            text = path.read_text(encoding="utf-8-sig")
            return list(csv.DictReader(io.StringIO(text)))
        raise ValueError(f"Unsupported file type: {suffix}")
```

- [ ] **Step 4: Let generator accept chart context**

In `backend/app/services/gemini.py`, change `generate` signature:

```python
    async def generate(self, req: GenerateRequest, chart_data: dict | None = None) -> list[SlideData]:
        slides = _mock_slides(req.deck_type)
        if chart_data:
            target_index = 4 if req.deck_type == "internal_6" else 6
            for slide in slides:
                if slide.index == target_index:
                    slide.chart_data = chart_data
                    break
        return slides
```

- [ ] **Step 5: Resolve `file_id` in generate router**

In `backend/app/routers/generate.py`, instantiate upload/chart services and pass `chart_data`:

```python
from app.services.charts import ChartPlanner
from app.services.uploads import UploadService

uploads = UploadService()
charts = ChartPlanner()

chart_data = None
if req.file_id:
    try:
        rows = uploads.get_rows(req.file_id)
        chart_data = charts.from_rows(rows=rows, title="Uploaded Data")
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

slides = await gemini.generate(req, chart_data=chart_data)
```

- [ ] **Step 6: Verify generate-with-file passes**

Run from `backend/`:

```bash
uv run pytest tests/test_api.py::test_generate_with_uploaded_csv_adds_chart_data -v
```

Expected: pass.

### Task 5: Render Charts in PPTX

**Files:**
- Modify: `backend/app/services/pptx_engine.py`
- Modify: `backend/tests/test_pptx_engine.py`

- [ ] **Step 1: Write failing chart-rendering test**

Add to `backend/tests/test_pptx_engine.py`:

```python
from io import BytesIO
from pptx import Presentation


def test_render_adds_chart_when_chart_data_present():
    slides = [
        SlideData(index=1, title="Title", bullets=[], notes="", layout="title"),
        SlideData(
            index=2,
            title="Revenue",
            bullets=["Revenue increased quarter over quarter"],
            notes="Discuss drivers.",
            layout="content",
            chart_data={
                "type": "bar",
                "title": "Revenue by Quarter",
                "categories": ["Q1", "Q2"],
                "series": [{"name": "revenue", "values": [100.0, 125.0]}],
            },
        ),
    ]

    prs = Presentation(BytesIO(PptxEngine().render(slides)))

    assert any(shape.has_chart for shape in prs.slides[1].shapes)
```

- [ ] **Step 2: Run the failing chart-rendering test**

Run from `backend/`:

```bash
uv run pytest tests/test_pptx_engine.py::test_render_adds_chart_when_chart_data_present -v
```

Expected: fail because no chart is rendered.

- [ ] **Step 3: Implement bar chart rendering**

In `backend/app/services/pptx_engine.py`, add imports:

```python
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
```

Add method:

```python
    def _add_chart(self, slide, chart_data: dict) -> None:
        data = CategoryChartData()
        data.categories = chart_data.get("categories", [])
        for series in chart_data.get("series", []):
            data.add_series(series.get("name", "Series"), series.get("values", []))
        slide.shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED,
            Inches(6.9),
            Inches(1.7),
            Inches(5.8),
            Inches(3.8),
            data,
        )
```

Call it from `_apply_content_slide`:

```python
        if data.chart_data:
            self._add_chart(slide, data.chart_data)
```

- [ ] **Step 4: Verify chart rendering passes**

Run from `backend/`:

```bash
uv run pytest tests/test_pptx_engine.py::test_render_adds_chart_when_chart_data_present -v
```

Expected: pass.

### Task 6: Speaker Notes in PPTX

**Files:**
- Modify: `backend/app/services/pptx_engine.py`
- Modify: `backend/tests/test_pptx_engine.py`

- [ ] **Step 1: Write failing speaker notes test**

Add to `backend/tests/test_pptx_engine.py`:

```python
def test_render_writes_speaker_notes():
    slides = [SlideData(index=1, title="Title", bullets=[], notes="Opening speaker note.", layout="title")]

    prs = Presentation(BytesIO(PptxEngine().render(slides)))
    notes_text = prs.slides[0].notes_slide.notes_text_frame.text

    assert "Opening speaker note." in notes_text
```

- [ ] **Step 2: Run the failing speaker notes test**

Run from `backend/`:

```bash
uv run pytest tests/test_pptx_engine.py::test_render_writes_speaker_notes -v
```

Expected: fail because notes are not written.

- [ ] **Step 3: Add speaker notes writer**

In `backend/app/services/pptx_engine.py`, add:

```python
    def _add_speaker_notes(self, slide, notes: str) -> None:
        if not notes:
            return
        notes_frame = slide.notes_slide.notes_text_frame
        notes_frame.text = notes
```

Call it from `render` after slide content is applied:

```python
            self._add_speaker_notes(slide, slide_data.notes)
```

- [ ] **Step 4: Verify speaker notes pass**

Run from `backend/`:

```bash
uv run pytest tests/test_pptx_engine.py::test_render_writes_speaker_notes -v
```

Expected: pass.

### Task 7: Citi Branding, Logo Lockup, and Disclaimer Text

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/pptx_engine.py`
- Modify: `backend/tests/test_pptx_engine.py`

- [ ] **Step 1: Write failing branding test**

Add to `backend/tests/test_pptx_engine.py`:

```python
def test_render_adds_citi_header_and_final_disclaimer_text():
    slides = [
        SlideData(index=1, title="Title", bullets=[], notes="", layout="title"),
        SlideData(index=2, title="Next Steps", bullets=["Review"], notes="", layout="content"),
    ]

    prs = Presentation(BytesIO(PptxEngine().render(slides)))
    first_slide_text = "\n".join(shape.text for shape in prs.slides[0].shapes if hasattr(shape, "text"))
    final_slide_text = "\n".join(shape.text for shape in prs.slides[-1].shapes if hasattr(shape, "text"))

    assert "citi" in first_slide_text.lower()
    assert "Confidential" in final_slide_text
    assert "not a guarantee" in final_slide_text
```

- [ ] **Step 2: Run failing branding test**

Run from `backend/`:

```bash
uv run pytest tests/test_pptx_engine.py::test_render_adds_citi_header_and_final_disclaimer_text -v
```

Expected: fail because there is no Citi header text and no standard risk disclosure.

- [ ] **Step 3: Add local default disclaimer setting**

In `backend/app/config.py`, add:

```python
    risk_disclosure: str = "Confidential. This material is for discussion purposes only and is not a guarantee of future results."
    citi_logo_path: str | None = None
```

- [ ] **Step 4: Add header/logo/disclaimer implementation**

In `backend/app/services/pptx_engine.py`, import settings:

```python
from app.config import settings
```

Add method:

```python
    def _add_brand_header(self, slide) -> None:
        header = slide.shapes.add_textbox(Inches(11.6), Inches(0.15), Inches(1.2), Inches(0.35))
        p = header.text_frame.paragraphs[0]
        p.text = "citi"
        p.font.name = "Arial"
        p.font.size = Pt(16)
        p.font.bold = True
        p.font.color.rgb = CITI_BLUE
```

Update `_add_footer`:

```python
        footer = slide.shapes.add_textbox(Inches(0.5), Inches(6.9), Inches(12), Inches(0.35))
        p = footer.text_frame.paragraphs[0]
        p.text = settings.risk_disclosure if index == total else "Confidential"
        p.font.name = "Calibri"
        p.font.size = Pt(8)
        p.font.color.rgb = CITI_RED if index == total else CITI_DARK
```

Call `_add_brand_header(slide)` for every slide in `render` before `_add_footer`.

- [ ] **Step 5: Verify branding test passes**

Run from `backend/`:

```bash
uv run pytest tests/test_pptx_engine.py::test_render_adds_citi_header_and_final_disclaimer_text -v
```

Expected: pass.

### Task 8: Export and Upload Expiry Cleanup

**Files:**
- Modify: `backend/app/services/storage.py`
- Modify: `backend/app/services/uploads.py`
- Create: `backend/tests/test_cleanup.py`

- [ ] **Step 1: Write failing cleanup tests**

Create `backend/tests/test_cleanup.py`:

```python
import time

from app.services.storage import StorageService
from app.services.uploads import UploadService


def test_storage_purge_expired_exports(tmp_path):
    service = StorageService(export_dir=tmp_path)
    path = tmp_path / "old.pptx"
    path.write_bytes(b"old")
    old = time.time() - 3600
    path.touch(times=(old, old))

    assert service.purge_expired(max_age_seconds=1) == 1
    assert not path.exists()


def test_uploads_purge_expired_files(tmp_path):
    service = UploadService(upload_dir=tmp_path)
    path = tmp_path / "old.csv"
    path.write_text("a,b\n1,2\n")
    old = time.time() - 3600
    path.touch(times=(old, old))

    assert service.purge_expired(max_age_seconds=1) == 1
    assert not path.exists()
```

- [ ] **Step 2: Run failing cleanup tests**

Run from `backend/`:

```bash
uv run pytest tests/test_cleanup.py -v
```

Expected: fail because `purge_expired` methods do not exist.

- [ ] **Step 3: Implement purge methods**

Add to `StorageService` and `UploadService`:

```python
    def purge_expired(self, max_age_seconds: int) -> int:
        now = time.time()
        count = 0
        for path in self.export_dir.glob("*"):
            if path.is_file() and now - path.stat().st_mtime > max_age_seconds:
                path.unlink()
                count += 1
        return count
```

For `UploadService`, use `self.upload_dir.glob("*")` instead of `self.export_dir.glob("*")`.

Also import `time` in both files.

- [ ] **Step 4: Verify cleanup tests pass**

Run from `backend/`:

```bash
uv run pytest tests/test_cleanup.py -v
```

Expected: pass.

### Task 9: Local DLP Pattern Expansion and Cloud Adapter Seam

**Files:**
- Modify: `backend/app/services/dlp.py`
- Modify: `backend/tests/test_dlp.py`

- [ ] **Step 1: Write failing tests for account-like and email-like detection**

Add to `backend/tests/test_dlp.py`:

```python
def test_scan_prompt_blocks_account_like_numbers():
    dlp = DlpService()

    result = dlp.scan_prompt("Client account 123456789012 needs review")

    assert "account-like number" in result


def test_scan_prompt_blocks_email_addresses():
    dlp = DlpService()

    result = dlp.scan_prompt("Contact jane.client@example.com")

    assert "email address" in result
```

- [ ] **Step 2: Run failing DLP tests**

Run from `backend/`:

```bash
uv run pytest tests/test_dlp.py::test_scan_prompt_blocks_account_like_numbers tests/test_dlp.py::test_scan_prompt_blocks_email_addresses -v
```

Expected: fail because local pattern detection is missing.

- [ ] **Step 3: Add local pattern detection**

In `backend/app/services/dlp.py`, import `re` and add constants:

```python
import re

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
ACCOUNT_RE = re.compile(r"\b\d{10,16}\b")
```

Update `scan_text` after prohibited term checks:

```python
        if EMAIL_RE.search(text):
            violations.append("email address")
        if ACCOUNT_RE.search(text):
            violations.append("account-like number")
```

- [ ] **Step 4: Verify DLP tests pass**

Run from `backend/`:

```bash
uv run pytest tests/test_dlp.py -v
```

Expected: pass.

### Task 10: Audit Metadata Expansion

**Files:**
- Modify: `backend/app/services/audit.py`
- Create: `backend/app/services/auth.py`
- Modify: `backend/app/routers/generate.py`
- Modify: `backend/app/routers/refine.py`
- Modify: `backend/app/routers/export.py`
- Modify: `backend/tests/test_audit.py`

- [ ] **Step 1: Write failing audit metadata test**

Add to `backend/tests/test_audit.py`:

```python
def test_audit_records_user_model_and_token_metadata():
    audit = AuditService()

    event = audit.record(
        action="generate",
        session_id="session-123",
        deck_type="sales_9",
        slide_count=9,
        user_id="local-user",
        model="gemini-1.5-pro",
        input_tokens=120,
        output_tokens=500,
    )

    assert event.user_id == "local-user"
    assert event.model == "gemini-1.5-pro"
    assert event.input_tokens == 120
    assert event.output_tokens == 500
```

- [ ] **Step 2: Run failing audit test**

Run from `backend/`:

```bash
uv run pytest tests/test_audit.py::test_audit_records_user_model_and_token_metadata -v
```

Expected: fail because the fields are not supported.

- [ ] **Step 3: Expand audit event metadata**

In `backend/app/services/audit.py`, add fields to `AuditEvent`:

```python
    user_id: str = "local-user"
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
```

Add matching keyword args to `record` with the same defaults and pass them into `AuditEvent`.

- [ ] **Step 4: Add local auth helper**

Create `backend/app/services/auth.py`:

```python
from fastapi import Request


def get_user_id(request: Request) -> str:
    return request.headers.get("x-user-id", "local-user")
```

In each router, accept `request: Request`, call `get_user_id(request)`, and pass `user_id` plus `settings.gemini_model` into `audit.record(...)`.

- [ ] **Step 5: Verify audit tests pass**

Run from `backend/`:

```bash
uv run pytest tests/test_audit.py tests/test_api.py -v
```

Expected: pass.

### Task 11: Provider Factories for Future Vertex, Cloud DLP, GCS, and Splunk

**Files:**
- Create: `backend/app/services/providers.py`
- Modify: `backend/app/routers/generate.py`
- Modify: `backend/app/routers/refine.py`
- Modify: `backend/app/routers/export.py`
- Create: `backend/tests/test_providers.py`

- [ ] **Step 1: Write failing provider factory tests**

Create `backend/tests/test_providers.py`:

```python
from app.services.providers import get_audit_service, get_dlp_service, get_generator_service, get_storage_service


def test_provider_factories_return_local_defaults():
    assert get_generator_service().__class__.__name__ == "GeminiService"
    assert get_dlp_service().__class__.__name__ == "DlpService"
    assert get_storage_service().__class__.__name__ == "StorageService"
    assert get_audit_service().__class__.__name__ == "AuditService"
```

- [ ] **Step 2: Run failing provider tests**

Run from `backend/`:

```bash
uv run pytest tests/test_providers.py -v
```

Expected: fail because provider factory module is missing.

- [ ] **Step 3: Implement provider factory module**

Create `backend/app/services/providers.py`:

```python
from app.services.audit import AuditService
from app.services.dlp import DlpService
from app.services.gemini import GeminiService
from app.services.storage import StorageService


def get_generator_service() -> GeminiService:
    return GeminiService()


def get_dlp_service() -> DlpService:
    return DlpService()


def get_storage_service() -> StorageService:
    return StorageService()


def get_audit_service() -> AuditService:
    return AuditService()
```

- [ ] **Step 4: Replace direct service construction in routers**

In routers, replace direct constructors with provider functions:

```python
from app.services.providers import get_audit_service, get_dlp_service, get_generator_service

gemini = get_generator_service()
dlp = get_dlp_service()
audit = get_audit_service()
```

For export router, use `get_storage_service()` too.

- [ ] **Step 5: Verify provider tests and API tests pass**

Run from `backend/`:

```bash
uv run pytest tests/test_providers.py tests/test_api.py -v
```

Expected: pass.

### Task 12: XLSX Upload Parsing

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/services/uploads.py`
- Modify: `backend/tests/test_uploads.py`

- [ ] **Step 1: Write failing XLSX parsing test**

Add this to `backend/tests/test_uploads.py`:

```python
from io import BytesIO

from openpyxl import Workbook


def test_save_xlsx_returns_file_id_and_summary(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["quarter", "revenue"])
    sheet.append(["Q1", 100])
    sheet.append(["Q2", 125])
    buffer = BytesIO()
    workbook.save(buffer)

    service = UploadService(upload_dir=tmp_path)
    result = service.save_upload(filename="revenue.xlsx", content=buffer.getvalue())

    assert result.file_id.endswith(".xlsx")
    assert result.filename == "revenue.xlsx"
    assert result.row_count == 2
    assert result.columns == ["quarter", "revenue"]
    assert "Q1" in result.preview
```

- [ ] **Step 2: Run the failing XLSX test**

Run from `backend/`:

```bash
uv run pytest tests/test_uploads.py::test_save_xlsx_returns_file_id_and_summary -v
```

Expected: fail because `.xlsx` parsing is not implemented, or because `openpyxl` is not installed.

- [ ] **Step 3: Add `openpyxl` dependency**

Run from `backend/`:

```bash
uv add openpyxl
```

Expected: `pyproject.toml` and `uv.lock` update with `openpyxl`.

- [ ] **Step 4: Implement XLSX parsing**

In `backend/app/services/uploads.py`, add import:

```python
from openpyxl import load_workbook
```

Add this helper:

```python
    def _rows_from_xlsx(self, content: bytes) -> list[dict[str, str]]:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(value) for value in rows[0]]
        parsed: list[dict[str, str]] = []
        for row in rows[1:]:
            parsed.append({headers[i]: "" if value is None else str(value) for i, value in enumerate(row) if i < len(headers)})
        return parsed
```

Update `_summarize` to support `.xlsx`:

```python
        if suffix == ".xlsx":
            rows = self._rows_from_xlsx(content)
            columns = list(rows[0].keys()) if rows else []
            preview_lines = [",".join(columns)]
            preview_lines.extend(",".join(row.get(column, "") for column in columns) for row in rows[:3])
            return UploadResponse(file_id=file_id, filename=filename, row_count=len(rows), columns=columns, preview="\n".join(preview_lines))
```

Update `get_rows` to support `.xlsx`:

```python
        if suffix == ".xlsx":
            return self._rows_from_xlsx(path.read_bytes())
```

- [ ] **Step 5: Verify XLSX parsing passes**

Run from `backend/`:

```bash
uv run pytest tests/test_uploads.py::test_save_xlsx_returns_file_id_and_summary -v
```

Expected: pass.

### Task 13: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run backend lint**

Run from `backend/`:

```bash
uv run ruff check app/ tests/
```

Expected: `All checks passed!`

- [ ] **Step 2: Run full backend tests**

Run from `backend/`:

```bash
uv run pytest
```

Expected: all tests pass.

- [ ] **Step 3: Review PRD coverage**

Check these backend PRD items are now covered by tests or explicitly deferred due missing external inputs:

- CSV upload and `file_id` generation path.
- Chart planning and PPTX chart rendering.
- Speaker notes in PPTX.
- Citi header/logo placeholder and final risk disclosure.
- Expanded local DLP checks.
- Audit user/model/token metadata.
- Local export/upload cleanup.
- Provider factory seams for cloud adapters.

## Deferred Until User Provides Inputs

- Real Citi `.potx` master template support requires the actual template file.
- Fixed Citi logo lockup should use the official logo asset when supplied; until then use text fallback.
- Production risk disclosure should replace the local default once Legal supplies approved text.
- Real Vertex AI, Cloud DLP, GCS signed URLs, Secret Manager, Splunk, and SSO require infrastructure credentials/config.
