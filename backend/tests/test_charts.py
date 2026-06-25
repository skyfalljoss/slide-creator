import pytest

from app.models.schemas import ChartRecommendation
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


@pytest.mark.parametrize("value", ["NaN", "inf", "-inf"])
def test_chart_planner_returns_none_for_non_finite_values(value: str):
    planner = ChartPlanner()

    chart = planner.from_rows(rows=[{"quarter": "Q1", "revenue": value}], title="Revenue")

    assert chart is None


def test_chart_planner_uses_later_numeric_column():
    planner = ChartPlanner()

    chart = planner.from_rows(
        rows=[
            {"quarter": "Q1", "status": "draft", "revenue": "100"},
            {"quarter": "Q2", "status": "final", "revenue": "125"},
        ],
        title="Revenue",
    )

    assert chart is not None
    assert chart["series"] == [{"name": "revenue", "values": [100.0, 125.0]}]


def test_chart_planner_returns_none_for_empty_rows():
    planner = ChartPlanner()

    chart = planner.from_rows(rows=[], title="Revenue")

    assert chart is None


def test_chart_planner_returns_none_for_one_column_rows():
    planner = ChartPlanner()

    chart = planner.from_rows(rows=[{"quarter": "Q1"}], title="Revenue")

    assert chart is None


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
    assert audit.category_column == "Quarter"
    assert audit.value_columns == ["Revenue"]


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


def test_chart_planner_rejects_non_numeric_recommended_values():
    rows = [{"Quarter": "Q1", "Revenue": "not available"}]
    recommendation = ChartRecommendation(
        chart_type="bar",
        category_column="Quarter",
        value_columns=["Revenue"],
        rationale="Revenue by quarter.",
    )

    chart_data, audit = ChartPlanner().from_recommendation(
        rows=rows,
        filename="metrics.csv",
        title="Revenue",
        recommendation=recommendation,
    )

    assert chart_data is None
    assert audit is not None
    assert audit.recommendation_status == "rejected"
    assert "numeric" in audit.rejection_reason.lower()
