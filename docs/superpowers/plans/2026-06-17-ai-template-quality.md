# AI Template Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace mock-quality deck output with Gemini-powered structured content, deterministic uploaded-file charts, sample-deck-inspired PPTX rendering, and a slide-like frontend preview.

**Architecture:** Backend generation stays schema-first: providers return validated `SlideData`; chart values are built only by backend code from uploaded rows; PPTX rendering uses programmatic Citi/investment-banking layouts inspired by `backend/app/templates/Citi PPTW Format - Sample Investment Banking Presentation.pptx`. Frontend mirrors the schema and renders richer slide previews while keeping the existing route flow.

**Tech Stack:** FastAPI, Pydantic v2, `python-pptx`, Gemini Developer API over HTTPS, React 19, TypeScript, TanStack Query, Vitest, pytest, ruff.

**Repo Constraint:** Do not commit in this plan because the user has not explicitly requested a commit.

---

## File Structure

- Modify `.gitignore`: unignore backend template PPTX files and ignore `.superpowers/` brainstorming artifacts.
- Modify `.env.example`: document `AI_PROVIDER=local`, `GEMINI_API_KEY`, and `GEMINI_MODEL`.
- Modify `backend/app/config.py`: add `gemini_api_key` and `sample_template_path` settings.
- Modify `backend/app/models/schemas.py`: add `ChartRecommendation`, `ChartAudit`, `visual_direction`, `chart_recommendation`, and `chart_audit`.
- Modify `backend/app/services/charts.py`: validate AI chart recommendations against uploaded rows and return deterministic chart data plus audit metadata.
- Modify `backend/app/services/gemini.py`: keep deterministic local generation/refinement but emit the new metadata fields.
- Create `backend/app/services/gemini_api.py`: Gemini Developer API provider, prompt builder, response parser, and schema validation.
- Modify `backend/app/services/providers.py`: select local or Gemini provider from settings and fail clearly when configured incorrectly.
- Modify `backend/app/services/session.py`: keep current behavior; no new persisted upload data is needed because charts are attached during generation and refinement preserves existing chart data.
- Modify `backend/app/routers/generate.py`: pass upload summary and rows to the provider, attach deterministic chart data only after validation.
- Modify `backend/app/routers/refine.py`: use provider refinement and preserve chart metadata unless a valid uploaded-data-backed recommendation can be accepted.
- Modify `backend/app/services/pptx_engine.py`: replace raw bullet rendering with sample-sized, layout-aware banker-style rendering.
- Modify `frontend/src/types/index.ts`: mirror new slide metadata types.
- Modify `frontend/src/pages/PreviewPage.tsx`: render a slide-like preview, chart source metadata, and collapsed `Design direction` disclosure.
- Modify tests under `backend/tests/` and `frontend/src/pages/PreviewPage.test.tsx` to cover the new behavior.

---

### Task 1: Settings, Git Ignore, And Shared Schemas

**Files:**
- Modify: `.gitignore`
- Modify: `.env.example`
- Modify: `backend/app/config.py`
- Modify: `backend/app/models/schemas.py`
- Modify: `frontend/src/types/index.ts`
- Test: `backend/tests/test_schemas.py`

- [ ] **Step 1: Write failing schema/config tests**

Add tests that construct `SlideData` with the new metadata fields and verify defaults stay backward-compatible.

```python
from app.models.schemas import ChartAudit, ChartRecommendation, SlideData


def test_slide_data_supports_visual_direction_and_chart_metadata():
    recommendation = ChartRecommendation(
        chart_type="line",
        category_column="Quarter",
        value_columns=["Revenue"],
        rationale="Trend over time is best shown as a line chart.",
    )
    audit = ChartAudit(
        source_filename="metrics.xlsx",
        category_column="Quarter",
        value_columns=["Revenue"],
        row_count=4,
        chart_type="line",
        recommendation_status="accepted",
        rejection_reason=None,
    )
    slide = SlideData(
        index=2,
        title="Revenue Momentum",
        bullets=["Revenue grew across all reported quarters"],
        notes="Discuss uploaded revenue trend.",
        layout="chart",
        visual_direction="Use a right-side line chart with a left insight panel.",
        chart_recommendation=recommendation,
        chart_audit=audit,
    )

    assert slide.visual_direction.startswith("Use a right-side")
    assert slide.chart_recommendation.chart_type == "line"
    assert slide.chart_audit.source_filename == "metrics.xlsx"


def test_slide_data_metadata_defaults_are_none():
    slide = SlideData(index=1, title="Title", bullets=[], notes="", layout="title")

    assert slide.visual_direction is None
    assert slide.chart_recommendation is None
    assert slide.chart_audit is None
```

- [ ] **Step 2: Run tests to verify RED**

Run: `cd backend && uv run pytest tests/test_schemas.py -v`

Expected: FAIL because `ChartRecommendation`, `ChartAudit`, and the new `SlideData` fields do not exist.

- [ ] **Step 3: Implement schema/config changes**

Add Pydantic models:

```python
class ChartRecommendation(BaseModel):
    chart_type: Literal["bar", "line", "waterfall"] = "bar"
    category_column: str = ""
    value_columns: list[str] = Field(default_factory=list)
    rationale: str = ""


class ChartAudit(BaseModel):
    source_filename: str
    category_column: str
    value_columns: list[str]
    row_count: int
    chart_type: Literal["bar", "line", "waterfall"] = "bar"
    recommendation_status: Literal["accepted", "rejected", "not_requested"] = "not_requested"
    rejection_reason: str | None = None
```

Extend `SlideData`:

```python
visual_direction: str | None = None
chart_recommendation: ChartRecommendation | None = None
chart_audit: ChartAudit | None = None
```

Add settings:

```python
gemini_api_key: str = ""
sample_template_path: str = "app/templates/Citi PPTW Format - Sample Investment Banking Presentation.pptx"
```

Update `.gitignore`:

```gitignore
.superpowers/
!backend/app/templates/*.pptx
```

Update `.env.example`:

```dotenv
AI_PROVIDER=local
GEMINI_API_KEY=
GEMINI_MODEL=gemini-1.5-pro
```

Update frontend types with matching TypeScript interfaces for `ChartRecommendation`, `ChartAudit`, and optional `SlideData` fields.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `cd backend && uv run pytest tests/test_schemas.py -v`

Expected: PASS.

---

### Task 2: Deterministic Chart Recommendation Validation

**Files:**
- Modify: `backend/app/services/charts.py`
- Test: `backend/tests/test_charts.py`

- [ ] **Step 1: Write failing chart tests**

Add tests for accepted and rejected chart recommendations.

```python
from app.models.schemas import ChartRecommendation
from app.services.charts import ChartPlanner


def test_chart_planner_uses_recommended_uploaded_columns_only():
    rows = [
        {"Quarter": "Q1", "Revenue": "100", "Cost": "70"},
        {"Quarter": "Q2", "Revenue": "125", "Cost": "82"},
    ]
    recommendation = ChartRecommendation(
        chart_type="line",
        category_column="Quarter",
        value_columns=["Revenue"],
        rationale="Revenue trend over time.",
    )

    chart_data, audit = ChartPlanner().from_recommendation(
        rows=rows,
        filename="metrics.csv",
        title="Revenue Trend",
        recommendation=recommendation,
    )

    assert chart_data is not None
    assert audit is not None
    assert chart_data["type"] == "line"
    assert chart_data["categories"] == ["Q1", "Q2"]
    assert chart_data["series"] == [{"name": "Revenue", "values": [100.0, 125.0]}]
    assert audit.recommendation_status == "accepted"
    assert audit.source_filename == "metrics.csv"


def test_chart_planner_rejects_recommendation_for_missing_columns():
    rows = [{"Quarter": "Q1", "Revenue": "100"}]
    recommendation = ChartRecommendation(
        chart_type="bar",
        category_column="Month",
        value_columns=["Bookings"],
        rationale="Bookings by month.",
    )

    chart_data, audit = ChartPlanner().from_recommendation(
        rows=rows,
        filename="metrics.csv",
        title="Bookings",
        recommendation=recommendation,
    )

    assert chart_data is None
    assert audit is not None
    assert audit.recommendation_status == "rejected"
    assert "missing" in audit.rejection_reason.lower()
```

- [ ] **Step 2: Run tests to verify RED**

Run: `cd backend && uv run pytest tests/test_charts.py -v`

Expected: FAIL because `from_recommendation` does not exist.

- [ ] **Step 3: Implement deterministic chart planner**

Add `from_recommendation()` that:

- accepts rows, filename, title, and optional `ChartRecommendation`
- rejects missing category/value columns
- rejects non-numeric value columns
- supports `bar`, `line`, and `waterfall` data types in returned metadata
- never creates chart values outside uploaded rows
- returns `(chart_data, chart_audit)`

Keep `from_rows()` as a backward-compatible helper that calls the new deterministic path with the first column and first numeric column.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `cd backend && uv run pytest tests/test_charts.py -v`

Expected: PASS.

---

### Task 3: Gemini Developer API Provider

**Files:**
- Create: `backend/app/services/gemini_api.py`
- Modify: `backend/app/services/providers.py`
- Modify: `backend/app/services/gemini.py`
- Test: `backend/tests/test_gemini_api.py`
- Test: `backend/tests/test_providers.py`
- Test: `backend/tests/test_gemini.py`

- [ ] **Step 1: Write failing provider tests**

Add tests that verify missing API key behavior, prompt rules, JSON parsing, and provider selection.

```python
import pytest

from app.config import settings
from app.models.schemas import GenerateRequest
from app.services.gemini_api import GeminiApiService, GeminiConfigurationError


def test_gemini_api_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")

    with pytest.raises(GeminiConfigurationError, match="GEMINI_API_KEY"):
        GeminiApiService()


def test_gemini_prompt_forbids_invented_chart_data(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    service = GeminiApiService()
    prompt = service.build_generation_prompt(
        GenerateRequest(prompt="Create a revenue deck", deck_type="sales_9"),
        upload_summary={"filename": "metrics.csv", "columns": ["Quarter", "Revenue"], "row_count": 2},
    )

    assert "Do not invent chart values" in prompt
    assert "Uploaded CSV/XLSX is the only allowed chart data source" in prompt
    assert "Return JSON only" in prompt
```

- [ ] **Step 2: Run tests to verify RED**

Run: `cd backend && uv run pytest tests/test_gemini_api.py tests/test_providers.py tests/test_gemini.py -v`

Expected: FAIL because `gemini_api.py` does not exist and providers do not support `AI_PROVIDER=gemini`.

- [ ] **Step 3: Implement Gemini API service**

Create `GeminiConfigurationError`, `GeminiResponseError`, and `GeminiApiService`.

Implementation requirements:

- use `settings.gemini_api_key`
- call `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}`
- request `responseMimeType: application/json`
- parse `candidates[0].content.parts[0].text`
- validate with Pydantic `SlideData`
- enforce slide count: 9 for `sales_9`, 6 for `internal_6`
- expose `build_generation_prompt()` for tests
- expose `generate()` and `refine()` with the same async API as local service

Use stdlib HTTP via `urllib.request` inside `asyncio.to_thread()` to avoid adding runtime dependencies.

- [ ] **Step 4: Update provider selection**

Change `get_generator_service()`:

```python
def get_generator_service():
    if settings.ai_provider == "local":
        return GeminiService()
    if settings.ai_provider == "gemini":
        return GeminiApiService()
    raise NotImplementedError(f"{settings.ai_provider} provider is not implemented")
```

- [ ] **Step 5: Update local mock output**

Keep local output deterministic, but add `visual_direction` and layout names that match the new renderer, such as `title`, `executive_summary`, `content`, `chart`, `section_divider`, and `next_steps`.

- [ ] **Step 6: Run tests to verify GREEN**

Run: `cd backend && uv run pytest tests/test_gemini_api.py tests/test_providers.py tests/test_gemini.py -v`

Expected: PASS.

---

### Task 4: Generation And Refinement Integration

**Files:**
- Modify: `backend/app/routers/generate.py`
- Modify: `backend/app/routers/refine.py`
- Modify: `backend/app/services/uploads.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

Add tests that prove generated chart data comes only from uploaded files and invalid chart recommendations are rejected without failing the deck.

```python
from app.models.schemas import ChartRecommendation, SlideData


class RecommendedChartService:
    async def generate(self, req, chart_data=None, upload_summary=None):
        return [
            SlideData(index=1, title="Title", bullets=[], notes="", layout="title"),
            SlideData(
                index=2,
                title="Revenue Trend",
                bullets=["Revenue increased across uploaded quarters"],
                notes="Discuss uploaded data only.",
                layout="chart",
                visual_direction="Line chart on the right with source note.",
                chart_recommendation=ChartRecommendation(
                    chart_type="line",
                    category_column="Quarter",
                    value_columns=["Revenue"],
                    rationale="Trend over time.",
                ),
            ),
        ]
```

Patch `providers.get_generator_service()` to return this service and assert the response includes deterministic `chart_data` and `chart_audit` derived from uploaded rows.

- [ ] **Step 2: Run tests to verify RED**

Run: `cd backend && uv run pytest tests/test_api.py -v`

Expected: FAIL because routers do not attach chart audit metadata from recommendations.

- [ ] **Step 3: Add upload summary helper**

In `UploadService`, add a helper that returns a compact summary for Gemini:

```python
def get_ai_summary(self, file_id: str) -> dict[str, object]:
    summary = self.get_summary(file_id)
    return {
        "filename": summary.filename,
        "columns": summary.columns,
        "row_count": summary.row_count,
        "preview": summary.preview,
    }
```

- [ ] **Step 4: Update `/generate`**

Generate flow:

- parse rows when `file_id` exists
- create upload summary
- call `service.generate(req, upload_summary=upload_summary)`
- for each slide with `chart_recommendation`, call `ChartPlanner.from_recommendation()`
- attach `chart_data` and `chart_audit`
- if no upload exists, store a rejected `chart_audit` with reason `No uploaded CSV/XLSX data available for chart rendering`
- DLP scan final slides

- [ ] **Step 5: Update `/refine`**

Refinement flow:

- pass current slide to provider
- preserve existing `chart_data` and `chart_audit` unless the provider returns a valid chart update path supported by available data
- keep DLP scan after refinement

- [ ] **Step 6: Run tests to verify GREEN**

Run: `cd backend && uv run pytest tests/test_api.py -v`

Expected: PASS.

---

### Task 5: Banker-Style PPTX Rendering

**Files:**
- Modify: `backend/app/services/pptx_engine.py`
- Test: `backend/tests/test_pptx_engine.py`

- [ ] **Step 1: Write failing PPTX tests**

Add tests for sample-sized canvas, source notes, and styled regions.

```python
from io import BytesIO

from pptx import Presentation
from pptx.util import Inches

from app.models.schemas import ChartAudit, SlideData
from app.services.pptx_engine import PptxEngine


def test_render_uses_sample_deck_canvas_size():
    slides = [SlideData(index=1, title="Title", bullets=[], notes="", layout="title")]

    prs = Presentation(BytesIO(PptxEngine().render(slides)))

    assert round(prs.slide_width / 914400, 2) == 17.78
    assert round(prs.slide_height / 914400, 2) == 10.0


def test_render_chart_slide_includes_source_note_from_audit():
    slides = [
        SlideData(index=1, title="Title", bullets=[], notes="", layout="title"),
        SlideData(
            index=2,
            title="Revenue Trend",
            bullets=["Revenue increased"],
            notes="Discuss trend.",
            layout="chart",
            chart_data={
                "type": "line",
                "title": "Revenue Trend",
                "categories": ["Q1", "Q2"],
                "series": [{"name": "Revenue", "values": [100.0, 125.0]}],
            },
            chart_audit=ChartAudit(
                source_filename="metrics.csv",
                category_column="Quarter",
                value_columns=["Revenue"],
                row_count=2,
                chart_type="line",
                recommendation_status="accepted",
            ),
        ),
    ]

    prs = Presentation(BytesIO(PptxEngine().render(slides)))
    slide_text = "\n".join(shape.text for shape in prs.slides[1].shapes if hasattr(shape, "text"))

    assert "Source: metrics.csv" in slide_text
    assert "Quarter, Revenue" in slide_text
```

- [ ] **Step 2: Run tests to verify RED**

Run: `cd backend && uv run pytest tests/test_pptx_engine.py -v`

Expected: FAIL because current renderer uses the smaller canvas and does not render audit source notes.

- [ ] **Step 3: Implement layout-aware renderer**

Update renderer to:

- set `prs.slide_width = Inches(17.7778)` and `prs.slide_height = Inches(10)` when no direct template is used
- use blank layouts and custom shapes/text boxes for predictable rendering
- add helpers for title, section divider, content, chart, and next steps layouts
- support chart type mapping: line to `XL_CHART_TYPE.LINE_MARKERS`, bar to `XL_CHART_TYPE.COLUMN_CLUSTERED`, waterfall fallback to column chart
- add source note when `chart_audit` exists
- keep speaker notes, logo fallback, and final disclosure

- [ ] **Step 4: Run tests to verify GREEN**

Run: `cd backend && uv run pytest tests/test_pptx_engine.py -v`

Expected: PASS.

---

### Task 6: Frontend Slide Preview

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/PreviewPage.tsx`
- Test: `frontend/src/pages/PreviewPage.test.tsx`

- [ ] **Step 1: Write failing frontend tests**

Add tests that verify the design direction panel starts collapsed and chart audit/source metadata renders.

```tsx
it('shows design direction only after expanding the panel', async () => {
  renderPreviewWithDeck({
    slides: [{
      index: 1,
      title: 'Revenue Trend',
      bullets: ['Revenue increased'],
      notes: 'Discuss trend.',
      layout: 'chart',
      chart_data: null,
      visual_direction: 'Use a right-side trend visual with Citi blue accents.',
      chart_recommendation: null,
      chart_audit: null,
    }],
  })

  expect(screen.queryByText(/right-side trend visual/i)).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: /design direction/i }))
  expect(screen.getByText(/right-side trend visual/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run tests to verify RED**

Run: `cd frontend && pnpm test -- PreviewPage.test.tsx`

Expected: FAIL because preview has no collapsible design direction panel.

- [ ] **Step 3: Implement preview UI**

Update preview to:

- render a 16:9 slide-like panel inside the card
- show a confidentiality label, title, slide count, bullets, notes, and footer styling
- show chart audit/source metadata when present
- show non-chart visual treatment based on `visual_direction` when no chart exists
- add a collapsed `Design direction` disclosure using a button with `aria-expanded`

- [ ] **Step 4: Run tests to verify GREEN**

Run: `cd frontend && pnpm test -- PreviewPage.test.tsx`

Expected: PASS.

---

### Task 7: Full Verification

**Files:**
- No new implementation files.

- [ ] **Step 1: Backend lint**

Run: `cd backend && uv run ruff check app/ tests/`

Expected: PASS with no lint errors.

- [ ] **Step 2: Backend tests**

Run: `cd backend && uv run pytest`

Expected: PASS with all backend tests passing.

- [ ] **Step 3: Frontend lint**

Run: `cd frontend && pnpm lint`

Expected: PASS with no lint errors.

- [ ] **Step 4: Frontend tests**

Run: `cd frontend && pnpm test`

Expected: PASS with all frontend tests passing.

- [ ] **Step 5: Frontend build**

Run: `cd frontend && pnpm build`

Expected: PASS with TypeScript and Vite build succeeding.

---

## Self-Review Checklist

- Spec coverage: Gemini API-key provider, deterministic chart data, chart audit metadata, sample-deck-inspired PPTX, frontend preview, and `.gitignore` handling are all assigned to tasks.
- Placeholder scan: no unfinished work markers are intended in this plan.
- Type consistency: backend and frontend use the same names: `visual_direction`, `chart_recommendation`, `chart_audit`, `ChartRecommendation`, and `ChartAudit`.
