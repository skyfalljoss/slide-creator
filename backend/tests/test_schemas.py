import pytest
from pydantic import ValidationError

from app.models.schemas import ChartAudit, ChartRecommendation, SlideContent, SlideData


def test_slide_data_accepts_chart_data_and_preserves_json_shape():
    chart_data = {
        "type": "bar",
        "title": "Revenue",
        "categories": ["Q1", "Q2"],
        "series": [{"name": "revenue", "values": [100.0, 125.0]}],
    }

    slide = SlideData(
        index=1,
        title="Revenue overview",
        bullets=["Q2 increased"],
        notes="Speaker notes",
        layout="chart",
        chart_data=chart_data,
    )

    assert slide.model_dump()["chart_data"] == chart_data


def test_slide_data_rejects_invalid_chart_series_values_shape():
    with pytest.raises(ValidationError):
        SlideData(
            index=1,
            title="Revenue overview",
            bullets=["Q2 increased"],
            notes="Speaker notes",
            layout="chart",
            chart_data={
                "categories": ["Q1"],
                "series": [{"name": "revenue", "values": "125"}],
            },
        )


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


def test_slide_data_accepts_content_chapter_metadata():
    slide = SlideData(
        index=3,
        title="Market Opportunity",
        bullets=[],
        notes="",
        layout="content",
        chapter_number=1,
        chapter_title="Market Opportunity",
    )

    assert slide.chapter_number == 1
    assert slide.chapter_title == "Market Opportunity"


def test_slide_data_rejects_chapter_number_outside_agenda_range():
    with pytest.raises(ValidationError):
        SlideData(
            index=3,
            title="Market Opportunity",
            bullets=[],
            notes="",
            layout="content",
            chapter_number=5,
        )


def test_slide_data_rejects_chapter_number_below_agenda_range():
    with pytest.raises(ValidationError):
        SlideData(
            index=3,
            title="Market Opportunity",
            bullets=[],
            notes="",
            layout="content",
            chapter_number=0,
        )


def test_slide_data_rejects_chapter_title_over_80_characters():
    with pytest.raises(ValidationError):
        SlideData(
            index=3,
            title="Market Opportunity",
            bullets=[],
            notes="",
            layout="content",
            chapter_title="x" * 81,
        )


def test_slide_content_rejects_chapter_number_outside_agenda_range():
    with pytest.raises(ValidationError):
        SlideContent(
            index=3,
            title="Market Opportunity",
            bullets=[],
            notes="",
            layout="content",
            chapter_number=0,
        )


def test_slide_content_rejects_chapter_title_over_80_characters():
    with pytest.raises(ValidationError):
        SlideContent(
            index=3,
            title="Market Opportunity",
            bullets=[],
            notes="",
            layout="content",
            chapter_title="x" * 81,
        )
