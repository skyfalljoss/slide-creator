from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal
from datetime import datetime

SlideVariant = Literal[
    "cover",
    "big_statement",
    "three_points",
    "split_image",
    "big_stat",
    "before_after",
    "comparison_table",
    "process",
    "quote",
    "closing",
]


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=50000)
    deck_type: str | None = None
    source_type: Literal["brief", "script"] = "brief"
    target_audience: Literal["corporate", "casual", "academic"] = "corporate"
    theme: Literal["minimalist", "bold", "dark"] = "minimalist"
    aspect_ratio: Literal["16:9", "4:3"] = "16:9"
    file_id: str | None = None


class ChartSeries(BaseModel):
    name: str
    values: list[float]

    @field_validator("name", mode="before")
    @classmethod
    def coerce_name(cls, value: object) -> str:
        return str(value)


class ChartData(BaseModel):
    type: Literal["bar", "line", "waterfall"] = "bar"
    title: str = ""
    categories: list[str] = Field(default_factory=list)
    series: list[ChartSeries] = Field(default_factory=list)

    @field_validator("title", mode="before")
    @classmethod
    def coerce_title(cls, value: object) -> str:
        return str(value)

    @field_validator("categories", mode="before")
    @classmethod
    def coerce_categories(cls, value: object) -> object:
        if isinstance(value, list):
            return [str(item) for item in value]
        return value


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


class SlideContent(BaseModel):
    index: int
    title: str
    kicker: str | None = None
    subtitle: str | None = None
    chapter_number: int | None = Field(default=None, ge=1, le=4)
    chapter_title: str | None = Field(default=None, max_length=80)
    bullets: list[str]
    notes: str
    layout: str
    variant: SlideVariant | None = None
    blocks: list[dict] | None = None

    @field_validator("blocks", mode="before")
    @classmethod
    def coerce_single_block(cls, value: object) -> object:
        if isinstance(value, dict):
            return [value]
        return value


class SlideEnrichment(BaseModel):
    chart_data: ChartData | None = None
    visual_direction: str | None = None
    chart_recommendation: ChartRecommendation | None = None
    chart_audit: ChartAudit | None = None


class SlideAssets(BaseModel):
    image_b64: str | None = None
    image_prompt: str | None = None
    image_query: str | None = None


class SlideData(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    index: int
    title: str
    kicker: str | None = None
    subtitle: str | None = None
    chapter_number: int | None = Field(default=None, ge=1, le=4)
    chapter_title: str | None = Field(default=None, max_length=80)
    bullets: list[str]
    notes: str
    layout: str
    variant: SlideVariant | None = None
    blocks: list[dict] | None = None
    chart_data: ChartData | None = None
    visual_direction: str | None = None
    chart_recommendation: ChartRecommendation | None = None
    chart_audit: ChartAudit | None = None
    image_b64: str | None = None
    image_prompt: str | None = None
    image_query: str | None = None
    callout: str | None = None
    narrative_context: str | None = None
    content: SlideContent | None = None
    enrichment: SlideEnrichment | None = None
    assets: SlideAssets | None = None

    @field_validator("blocks", mode="before")
    @classmethod
    def coerce_single_block(cls, value: object) -> object:
        if isinstance(value, dict):
            return [value]
        return value

    @classmethod
    def from_legacy(cls, **data: object) -> "SlideData":
        content_fields = {k: data.pop(k) for k in list(data) if k in SlideContent.model_fields}
        enrichment_fields = {k: data.pop(k) for k in list(data) if k in SlideEnrichment.model_fields}
        assets_fields = {k: data.pop(k) for k in list(data) if k in SlideAssets.model_fields}
        slide = cls(**data)
        if any(v is not None for v in content_fields.values()):
            slide.content = SlideContent(**content_fields)
        if any(v is not None for v in enrichment_fields.values()):
            slide.enrichment = SlideEnrichment(**enrichment_fields)
        if any(v is not None for v in assets_fields.values()):
            slide.assets = SlideAssets(**assets_fields)
        return slide


class GenerateResponse(BaseModel):
    session_id: str
    deck_id: str
    editor_path: str
    slides: list[SlideData]


class OnlyOfficeEditorConfig(BaseModel):
    document_server_url: str
    config: dict[str, object]


class OnlyOfficeCallback(BaseModel):
    key: str
    status: int
    url: str | None = None
    users: list[str] = Field(default_factory=list)
    userdata: str | None = None


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    row_count: int
    columns: list[str]
    preview: str


class RefineRequest(BaseModel):
    session_id: str
    slide_index: int
    instruction: str = Field(min_length=1, max_length=1000)


class RefineResponse(BaseModel):
    slide: SlideData


class ExportRequest(BaseModel):
    session_id: str | None = None
    deck_id: str | None = None


class ExportResponse(BaseModel):
    download_url: str
    expires_at: datetime


class SlidePreviewResponse(BaseModel):
    deck_id: str
    slide_index: int
    image_b64: str
    width: int = 1920
    height: int = 1080
    updated_at: str | None = None


class DeckSummary(BaseModel):
    id: str
    name: str
    deck_type: str
    slide_count: int
    thumbnail_b64: str | None = None
    created_at: str
    updated_at: str


class DeckDetail(BaseModel):
    id: str
    name: str
    deck_type: str
    theme: str
    aspect_ratio: str
    slides: list[SlideData]
    thumbnail_b64: str | None = None
    created_at: str
    updated_at: str


class SaveDeckRequest(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    deck_type: str
    theme: str = "minimalist"
    aspect_ratio: str = "16:9"
    slides: list[SlideData]
    thumbnail_b64: str | None = None


class UpdateDeckRequest(BaseModel):
    name: str | None = Field(default=None, max_length=500)
    slides: list[SlideData] | None = None


class RenameDeckRequest(BaseModel):
    name: str = Field(min_length=1, max_length=500)


class SaveDeckResponse(BaseModel):
    id: str
    name: str
    created_at: str


class UpdateDeckResponse(BaseModel):
    updated_at: str


class DeleteDeckResponse(BaseModel):
    ok: bool


class ListDecksResponse(BaseModel):
    decks: list[DeckSummary]


class DeckVersionResponse(BaseModel):
    id: str
    version_number: int
    source: Literal["generated", "onlyoffice_save", "restore"]
    created_by: str
    size_bytes: int
    sha256: str
    created_at: datetime


class ListDeckVersionsResponse(BaseModel):
    versions: list[DeckVersionResponse]


class DeckStatusResponse(BaseModel):
    current_version_id: str
    current_version_number: int
    updated_at: datetime


class RestoreVersionResponse(DeckStatusResponse):
    pass
