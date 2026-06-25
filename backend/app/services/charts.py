import math

from app.models.schemas import ChartAudit, ChartRecommendation


class ChartPlanner:
    def from_rows(self, *, rows: list[dict[str, str]], title: str) -> dict | None:
        chart_data, _audit = self.from_rows_with_audit(rows=rows, filename="uploaded data", title=title)
        return chart_data

    def from_rows_with_audit(
        self,
        *,
        rows: list[dict[str, str]],
        filename: str,
        title: str,
    ) -> tuple[dict | None, ChartAudit | None]:
        recommendation = self.infer_recommendation(rows)
        if recommendation is None:
            return None, None
        return self.from_recommendation(rows=rows, filename=filename, title=title, recommendation=recommendation)

    def infer_recommendation(self, rows: list[dict[str, str]]) -> ChartRecommendation | None:
        if not rows:
            return None
        columns = list(rows[0].keys())
        if len(columns) < 2:
            return None
        category_column = columns[0]
        numeric_column = ""
        for column in columns[1:]:
            column_values: list[float] = []
            for row in rows:
                try:
                    value = float(row[column])
                except (KeyError, TypeError, ValueError):
                    break
                if not math.isfinite(value):
                    break
                column_values.append(value)
            else:
                numeric_column = column
                break
        if not numeric_column:
            return None
        return ChartRecommendation(
            chart_type="bar",
            category_column=category_column,
            value_columns=[numeric_column],
            rationale="First numeric uploaded column selected for chart rendering.",
        )

    def from_recommendation(
        self,
        *,
        rows: list[dict[str, str]],
        filename: str,
        title: str,
        recommendation: ChartRecommendation,
    ) -> tuple[dict | None, ChartAudit]:
        row_count = len(rows)
        base_audit = {
            "source_filename": filename,
            "category_column": recommendation.category_column,
            "value_columns": recommendation.value_columns,
            "row_count": row_count,
            "chart_type": recommendation.chart_type,
        }

        if not rows:
            return None, ChartAudit(
                **base_audit,
                recommendation_status="rejected",
                rejection_reason="No uploaded rows available for chart rendering",
            )

        available_columns = set(rows[0].keys())
        requested_columns = [recommendation.category_column, *recommendation.value_columns]
        missing_columns = [column for column in requested_columns if column not in available_columns]
        if missing_columns:
            return None, ChartAudit(
                **base_audit,
                recommendation_status="rejected",
                rejection_reason=f"Missing uploaded columns: {', '.join(missing_columns)}",
            )

        if not recommendation.value_columns:
            return None, ChartAudit(
                **base_audit,
                recommendation_status="rejected",
                rejection_reason="At least one uploaded numeric value column is required",
            )

        series_items: list[dict[str, object]] = []
        for column in recommendation.value_columns:
            values: list[float] = []
            for row in rows:
                try:
                    value = float(row[column])
                except (KeyError, TypeError, ValueError):
                    return None, ChartAudit(
                        **base_audit,
                        recommendation_status="rejected",
                        rejection_reason=f"Column '{column}' contains non-numeric values",
                    )
                if not math.isfinite(value):
                    return None, ChartAudit(
                        **base_audit,
                        recommendation_status="rejected",
                        rejection_reason=f"Column '{column}' contains non-finite numeric values",
                    )
                values.append(value)
            series_items.append({"name": column, "values": values})

        categories = [row.get(recommendation.category_column, "") for row in rows]
        return {
            "type": recommendation.chart_type,
            "title": title,
            "categories": categories,
            "series": series_items,
        }, ChartAudit(**base_audit, recommendation_status="accepted", rejection_reason=None)
