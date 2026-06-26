import re

from app.models.schemas import SlideData, GenerateRequest, RefineRequest

MAX_BULLETS = 5
MAX_SCRIPT_SLIDES = 20


class GeminiService:
    async def generate(
        self,
        req: GenerateRequest,
        chart_data: dict | None = None,
        upload_summary: dict | None = None,
    ) -> list[SlideData]:
        del upload_summary
        if getattr(req, "source_type", "brief") == "script":
            return _script_mock_slides(req.prompt)
        slides = _mock_slides(req.deck_type)
        if chart_data:
            chart_slide_index = 4 if req.deck_type and req.deck_type == "internal_6" else 6
            slides[chart_slide_index - 1].chart_data = chart_data
        return slides

    async def refine(self, req: RefineRequest, current_slide: SlideData) -> SlideData:
        return SlideData(
            index=current_slide.index,
            title=f"Refined: {current_slide.title}",
            kicker=current_slide.kicker,
            subtitle=current_slide.subtitle,
            bullets=[f"{b} (refined)" for b in current_slide.bullets],
            notes=current_slide.notes,
            layout=current_slide.layout,
            variant=current_slide.variant,
            blocks=current_slide.blocks,
            chart_data=current_slide.chart_data,
            visual_direction=current_slide.visual_direction or "Use a cleaner Citi-style layout with stronger hierarchy.",
            chart_recommendation=current_slide.chart_recommendation,
            chart_audit=current_slide.chart_audit,
            image_b64=current_slide.image_b64,
            image_prompt=current_slide.image_prompt,
            image_query=current_slide.image_query,
        )


def _mock_slides(deck_type: str | None) -> list[SlideData]:
    if deck_type == "internal_6":
        return [
            SlideData(index=1, title="Project Alpha", subtitle="Q2 2026 internal review", bullets=["Q2 2026 Initiative", "Owner: J. Smith", "Launch target: July 2026"], notes="Opening slide for internal review.", layout="title", variant="cover", visual_direction="Framework cover slide with large title and Citi accent."),
            SlideData(index=2, title="Automation unlocks faster reporting with stronger controls", bullets=["Reduce report generation time by 60%", "Automate compliance checks"], notes="State the core problem.", layout="content", variant="big_statement", visual_direction="Big statement slide with one forceful takeaway."),
            SlideData(index=3, title="Current process creates measurable drag", bullets=["Current process takes 4 hours per report", "80% of errors are manual data entry", "Automation saves $200K/year"], notes="Data-driven findings.", layout="content", variant="big_stat", blocks=[{"type": "stat", "value": "60%", "label": "Target reduction in report generation time"}], visual_direction="Oversized metric with concise supporting label."),
            SlideData(index=4, title="Analysis", bullets=["Volume growth of 25% YoY", "Cost per report: $120 manual vs $45 automated"], notes="Show the math.", layout="chart", variant="comparison_table", visual_direction="Left insight bullets with right chart area and source note."),
            SlideData(index=5, title="Recommendation", bullets=["Implement automated pipeline by August", "Owner: Operations Team", "Budget: $150K one-time"], notes="Clear next steps.", layout="next_steps", variant="process", blocks=[{"type": "process", "steps": [{"title": "Approve", "body": "Confirm funding and accountable owner."}, {"title": "Build", "body": "Implement core automation pipeline."}, {"title": "Roll out", "body": "Deploy by report family."}]}], visual_direction="Three-step process timeline with owner and timing emphasis."),
            SlideData(index=6, title="Thank You", subtitle="Questions and open discussion.", bullets=["Questions and open discussion."], notes="Close the discussion.", layout="content", variant="closing", visual_direction="Dedicated final thank-you slide with dark Citi-style background."),
        ]

    return [
        SlideData(index=1, title="Client Name Proposal", subtitle="Strategic financing proposal", bullets=["Prepared for Client Name", "June 2026"], notes="Title slide with client info.", layout="title", variant="cover", visual_direction="Framework cover slide with large title, subtitle, and Citi accent."),
        SlideData(index=2, title="Citi can unlock flexible growth capital while preserving strategic options", bullets=["$500M financing opportunity", "Tailored solution with flexible terms", "Citi's global network advantage"], notes="Outcome-focused summary.", layout="content", variant="big_statement", visual_direction="Big statement slide with one executive takeaway."),
        SlideData(index=3, title="Situation", subtitle="Client context and market backdrop", bullets=["Client seeking growth capital", "Strong market position", "Existing banking relationship since 2022"], notes="Client context from prompt only.", layout="content", variant="split_image", visual_direction="Two-column slide with left narrative and right visual."),
        SlideData(index=4, title="Citi Solution", bullets=["Senior secured credit facility", "Competitive pricing with green financing option", "Dedicated relationship team"], notes="Product fit, avoid guarantees.", layout="content", variant="three_points", blocks=[{"type": "cards", "columns": 3, "items": [{"title": "Flexible Facility", "body": "Senior secured credit facility aligned to growth needs.", "icon": "financial"}, {"title": "Sustainable Option", "body": "Green financing structure where eligible.", "icon": "growth"}, {"title": "Dedicated Team", "body": "Coordinated coverage across product and relationship teams.", "icon": "client"}]}], visual_direction="Three framework cards for solution pillars."),
        SlideData(index=5, title="Market Overview", subtitle="Industry landscape", bullets=["Market growing at 12% CAGR", "Regulatory environment remains favorable"], notes="Deep dive into market.", layout="section_divider", variant="split_image", visual_direction="Full-bleed image divider with centered section title."),
        SlideData(index=6, title="Financial Analysis", bullets=["Revenue: $2.1B (FY2025)", "EBITDA margin: 34%", "Debt/Equity: 0.8x"], notes="Chart data recommended.", layout="chart", variant="big_stat", blocks=[{"type": "stat", "value": "34%", "label": "FY2025 EBITDA margin"}], visual_direction="Left metric callouts with right chart region and source note."),
        SlideData(index=7, title="Platform Capabilities", bullets=["Global distribution network in 95+ countries", "#1 in syndicated loans by volume", "24/7 client support"], notes="Differentiators only.", layout="content", variant="comparison_table", blocks=[{"type": "table", "headers": ["Capability", "Client Impact"], "rows": [["Global network", "Distribution in 95+ countries"], ["Loan franchise", "Leading syndicated loan execution"], ["Support model", "Always-on relationship coverage"]]}], visual_direction="Framework comparison table with Citi advantages."),
        SlideData(index=8, title="Next Steps", bullets=["Term sheet review by June 30", "Credit committee approval Q3", "Target close: September 2026"], notes="3 action items before the final thank-you slide.", layout="next_steps", variant="process", blocks=[{"type": "process", "steps": [{"title": "Review", "body": "Term sheet by June 30."}, {"title": "Approve", "body": "Credit committee in Q3."}, {"title": "Close", "body": "Target September 2026."}]}], visual_direction="Framework process slide with concrete next actions."),
        SlideData(index=9, title="Thank You", subtitle="Questions and open discussion.", bullets=["Questions and open discussion."], notes="Close the discussion.", layout="content", variant="closing", visual_direction="Dedicated final thank-you slide with dark Citi-style background."),
    ]


def _chunk_text(text: str) -> list[str]:
    """Split a source document into chunks on blank-line paragraph boundaries."""
    parts = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if not parts:
        parts = [text.strip() or "Untitled"]
    return parts[:MAX_SCRIPT_SLIDES]


def _script_mock_slides(text: str) -> list[SlideData]:
    """Offline approximation of the script-summarization 'brain'.

    Chunks the source into slides, derives a punchy-ish title and up to 5
    bullets per chunk, and preserves the original chunk text as speaker notes.
    """
    slides: list[SlideData] = []
    for i, chunk in enumerate(_chunk_text(text), 1):
        lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
        title = (lines[0] if lines else f"Section {i}")[:80]
        body = " ".join(lines[1:]) if len(lines) > 1 else (lines[0] if lines else "")
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body) if s.strip()]
        bullets = [s[:160] for s in sentences[:MAX_BULLETS]] or [title]
        slides.append(
            SlideData(
                index=i,
                title=title,
                bullets=bullets,
                notes=chunk.strip(),
                layout="title" if i == 1 else "content",
                variant="cover" if i == 1 else "closing" if "next step" in title.lower() else "split_image",
                visual_direction="Auto-generated from source chunk.",
            )
        )
    return slides
