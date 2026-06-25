from app.models.schemas import ChartAudit, SlideData
from app.services.charts import ChartPlanner


class SlideChartResolver:
    """Attach uploaded-data charts to AI-selected chart slides."""

    def __init__(self, chart_planner: ChartPlanner | None = None) -> None:
        self.chart_planner = chart_planner or ChartPlanner()

    def attach(
        self,
        *,
        slides: list[SlideData],
        rows: list[dict[str, str]] | None,
        upload_summary: dict[str, object] | None,
    ) -> None:
        filename = str((upload_summary or {}).get("filename") or "uploaded data")
        if rows:
            self._attach_from_rows(slides=slides, rows=rows, filename=filename)
            return

        for slide in slides:
            if slide.chart_recommendation is None:
                continue
            slide.chart_audit = ChartAudit(
                source_filename="",
                category_column=slide.chart_recommendation.category_column,
                value_columns=slide.chart_recommendation.value_columns,
                row_count=0,
                chart_type=slide.chart_recommendation.chart_type,
                recommendation_status="rejected",
                rejection_reason="No uploaded CSV/XLSX data available for chart rendering",
            )

    def _attach_from_rows(self, *, slides: list[SlideData], rows: list[dict[str, str]], filename: str) -> None:
        had_recommendation = any(slide.chart_recommendation is not None for slide in slides)
        for slide in slides:
            if slide.chart_recommendation is None:
                continue
            chart_data, audit = self.chart_planner.from_recommendation(
                rows=rows,
                filename=filename,
                title=slide.title,
                recommendation=slide.chart_recommendation,
            )
            slide.chart_data = chart_data
            slide.chart_audit = audit

        if any(slide.chart_data for slide in slides) or had_recommendation:
            return

        chart_data, audit = self.chart_planner.from_rows_with_audit(
            rows=rows,
            filename=filename,
            title="Uploaded Data",
        )
        if chart_data is None:
            return
        target = next((slide for slide in slides if slide.layout == "chart"), None)
        if target is None:
            target = next((slide for slide in slides if slide.index != 1), slides[-1])
        target.chart_data = chart_data
        target.chart_audit = audit
