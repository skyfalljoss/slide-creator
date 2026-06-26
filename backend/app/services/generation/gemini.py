import re

from app.models.schemas import SlideData, GenerateRequest, RefineRequest

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
            SlideData(
                index=1, title="Project Alpha", subtitle="Q2 2026 internal review",
                bullets=[
                    "Project Alpha is the firm's flagship digital transformation initiative, targeting a 40% reduction in operating costs across three business units by Q4 2026. The program has secured $12M in seed funding with an additional $8M contingent on Q2 milestones.",
                    "The initiative is sponsored by the COO and CIO, with dedicated workstreams in finance, compliance, and operations. Executive oversight is provided through a biweekly steering committee chaired by the Chief Digital Officer.",
                    "A cross-functional team of 45 full-time equivalents has been assembled, spanning engineering, product, data science, and change management. External consultants from two major firms are supplementing the core team through Q3 2026.",
                    "The initial discovery phase completed in March 2026 identified 23 distinct automation opportunities across the reporting value chain, with an aggregate net present value of $14.2M. Prioritization is underway using a weighted scoring framework.",
                    "Legacy system dependencies represent the primary execution risk, with three mainframe systems requiring API modernization before automation workflows can be deployed. A parallel remediation track has been established to address this dependency.",
                    "Key performance indicators have been defined across four dimensions: cost reduction, cycle time improvement, error rate reduction, and employee satisfaction. Baseline measurements were collected in Q1 2026 and will be tracked monthly.",
                ],
                notes="Opening slide for internal review.",
                layout="title", variant="cover",
                visual_direction="Framework cover slide with large title and Citi accent.",
                callout="Project Alpha is on track to deliver $14.2M in NPV across 23 automation opportunities by Q4 2026.",
                narrative_context="Project Alpha was initiated in January 2026 following a six-month strategic review that identified manual reporting processes as the single largest source of operational inefficiency across the organization. The program is structured into three phases: discovery (completed), implementation (Q2-Q3 2026), and scale (Q4 2026 onward). Initial cost-benefit analysis projected a 3.2x return on investment over a three-year horizon, with the majority of benefits realized in years two and three.",
            ),
            SlideData(
                index=2,
                title="Automation unlocks faster reporting with stronger controls",
                bullets=[
                    "Current month-end close processes require an average of 4.2 hours per report across 15 business units, consuming approximately 6,300 person-hours annually. Automation is projected to reduce this to under 1.5 hours per report, representing a 64% reduction in labor costs and enabling same-day close capability.",
                    "Manual data entry and spreadsheet-based consolidation introduce an average of 12 errors per reporting cycle, with 80% of these errors traced to manual rekeying between source systems and presentation templates. Automated pipelines eliminate this vector entirely through direct system-to-system integration.",
                    "Automated compliance validation can embed 47 regulatory checkpoints directly into the reporting workflow, reducing the need for manual controls and post-report audits. This addresses three recent audit findings related to data integrity in regulatory submissions.",
                    "The proposed automation framework leverages existing investments in Snowflake data warehouse and Power BI infrastructure, requiring no new platform acquisitions. The incremental cost of implementation is estimated at $450K, with a payback period of 7.2 months based on current operational expenditure.",
                    "Real-time dashboards will replace static PDF reports for 85% of routine management reporting, providing stakeholders with drill-down capability and reducing ad hoc data requests by an estimated 60%. This aligns with the firm's broader self-service analytics strategy.",
                    "Control enhancements include automated reconciliation, audit trail generation, and role-based access controls that exceed SOX compliance requirements. The new control framework has been reviewed by internal audit and deemed fit for purpose in a pre-implementation assessment.",
                ],
                notes="State the core problem.",
                layout="content", variant="big_statement",
                visual_direction="Big statement slide with one forceful takeaway.",
                callout="Automating the reporting workflow will eliminate 6,300 person-hours annually and reduce error rates by 80% across 15 business units.",
                narrative_context="The current reporting process has remained largely unchanged for seven years, relying on a combination of Excel-based data aggregation, manual reconciliation, and email-based distribution. A 2025 process mining study revealed that 68% of the total cycle time is consumed by waiting periods between handoffs, with only 32% representing value-added work. Competing firms in the peer group have already deployed automated reporting solutions, achieving 50-70% cycle time reductions and positioning automation as a competitive necessity rather than a discretionary investment.",
            ),
            SlideData(
                index=3,
                title="Current process creates measurable drag",
                bullets=[
                    "The current reporting process requires an average of 4.2 hours per report across a portfolio of 28 recurring management reports, consuming 117 person-hours per week. This translates to an annual operational cost of $1.8M in analyst time that could be redirected to higher-value analytical work.",
                    "Error rates average 12 discrepancies per reporting cycle, with manual data entry accounting for 80% of all defects. Each error requires an average of 45 minutes to investigate and remediate, adding $43K annually in non-value-added rework costs.",
                    "Report distribution relies on email-based PDF delivery, with an average of 35 recipients per report and a 22% open rate within the first 48 hours. This outdated distribution model limits accessibility and creates version control issues when updates are needed mid-cycle.",
                    "Post-report ad hoc requests consume an additional 22 hours per week as stakeholders seek clarification or deeper analysis that static reports cannot provide. These requests have grown 34% year-over-year, indicating a structural gap between report content and stakeholder needs.",
                    "The month-end close calendar currently has 14 distinct handoffs between five departments, with an average latency of 2.3 hours per handoff. Consolidating these handoffs through automated workflows could compress the close timeline from 5 business days to 2 business days.",
                    "Compliance reviews consume 8 hours per reporting cycle as teams manually validate data against 47 regulatory checkpoints. Automated validation could reduce this to under 30 minutes while improving coverage and audit trail completeness.",
                    "Dependence on three key individuals with institutional knowledge of the reporting macros and spreadsheet logic creates a single point of failure risk. Two of these individuals are eligible for retirement within 18 months, creating urgency for process standardization.",
                ],
                notes="Data-driven findings.",
                layout="content", variant="big_stat",
                blocks=[{"type": "stat", "value": "60%", "label": "Target reduction in report generation time"}],
                visual_direction="Oversized metric with concise supporting label.",
                callout="The current reporting process costs $1.8M annually in analyst time, with 80% of errors stemming from manual data entry that automation would eliminate.",
                narrative_context="A comprehensive process audit conducted in Q4 2025 mapped the end-to-end reporting workflow across all 15 business units, identifying 47 discrete process steps with measurable cycle times and error rates. The audit revealed that the organization spends 3.8x more hours per report than the top-quartile peer benchmark, placing it in the bottom 20% of financial services firms for reporting efficiency. This gap has been flagged by the CFO as a priority area for operational improvement in the 2026 strategic plan.",
            ),
            SlideData(
                index=4,
                title="Analysis",
                bullets=[
                    "Transaction volume has grown at a compound annual rate of 25% over the past three fiscal years, driven by expansion into two new product lines and a 40% increase in active client accounts. This growth trajectory is expected to continue at 20-22% annually through 2028 based on the current pipeline.",
                    "Unit cost analysis reveals a widening gap between automated and manual processing: each manual report costs $120.00 in analyst time, while automated reports (piloted in Q1 2026) cost just $45.00 per report. At current volumes, this differential represents $750K in annual savings at 50% automation penetration, scaling to $1.5M at full deployment.",
                    "Break-even analysis indicates that the $450K automation investment will achieve payback at 55% automation penetration, projected to occur in month seven of deployment based on the current adoption curve. Internal rate of return is calculated at 187% over a three-year horizon with a net present value of $2.1M.",
                    "Peer benchmarking against five comparable financial institutions shows that automation leaders achieve average cost reductions of 58% in reporting functions, with top-quartile performers reporting 72% reduction. Our current automation maturity ranks in the third quartile, indicating significant catch-up opportunity.",
                    "Risk-adjusted analysis incorporating execution delays, adoption friction, and technology integration challenges yields an expected NPV of $1.6M with a 92% probability of positive return. The primary risk factor is mainframe API compatibility, with a 15% probability of material delay.",
                    "Sensitivity analysis on key variables shows that the business case remains robust under conservative assumptions: even with a 30% longer implementation timeline and 20% lower cost savings, the project still delivers a positive NPV. This resilience supports proceeding with full funding approval.",
                ],
                notes="Show the math.",
                layout="chart", variant="comparison_table",
                visual_direction="Left insight bullets with right chart area and source note.",
                callout="The automation investment delivers a 187% IRR and $2.1M NPV over three years, with break-even achieved in month seven of deployment.",
                narrative_context="The financial analysis presented in this slide is based on a bottom-up cost model developed jointly by Finance, Operations, and the PMO over a six-week period. Data inputs were validated against actuals from the past 12 months, with conservative growth assumptions applied to future projections. The peer benchmark data was sourced from a 2025 industry survey conducted by a major consulting firm, adjusted for firm size and business mix to ensure comparability.",
            ),
            SlideData(
                index=5,
                title="Recommendation",
                bullets=[
                    "Approve the $450K automation investment and proceed with the 26-week implementation plan targeting a go-live date of August 15, 2026. The recommended approach follows an agile delivery methodology with four two-week sprints for each of the three major workstreams, enabling early value capture starting in week 12.",
                    "Establish the Operations Team as the accountable owner with executive sponsorship from the COO, supported by a dedicated steering committee meeting biweekly. A full-time program manager should be assigned with authority over scope, schedule, and budget decisions within the approved funding envelope.",
                    "Deploy the automation solution in three waves by report family to manage risk and enable learning: wave one (finance and regulatory reports, weeks 1-10), wave two (management and operational reports, weeks 11-18), and wave three (ad hoc and executive reports, weeks 19-26). Wave one targets 6 of the 28 reports representing 35% of total volume.",
                    "Establish measurable success criteria with quarterly checkpoints: Q3 2026 target of 30% automation penetration and 20% cost reduction, Q4 2026 target of 60% automation penetration and 40% cost reduction, and full deployment by Q1 2027 with a target of 85% automation penetration. Monthly scorecards will track progress against these milestones.",
                    "Allocate a $75K contingency reserve (17% of total budget) for the mainframe API integration workstream, which carries the highest technical risk. This reserve is separately tracked and requires steering committee approval for release, ensuring transparent cost governance.",
                    "Initiate a parallel change management workstream led by HR and Communications to prepare the 28 affected analysts for role evolution from report production to data analysis and insight generation. A reskilling budget of $50K has been allocated for training programs commencing in Q3 2026.",
                ],
                notes="Clear next steps.",
                layout="next_steps", variant="process",
                blocks=[{"type": "process", "steps": [{"title": "Approve", "body": "Confirm funding and accountable owner."}, {"title": "Build", "body": "Implement core automation pipeline."}, {"title": "Roll out", "body": "Deploy by report family."}]}],
                visual_direction="Three-step process timeline with owner and timing emphasis.",
                callout="Approve $450K investment for a 26-week agile implementation targeting 60% automation penetration and 40% cost reduction by Q4 2026.",
                narrative_context="This recommendation reflects the consensus view of a cross-functional working group that met weekly over a 10-week period from January to March 2026. The group included representatives from Finance, Operations, IT, Compliance, and Internal Audit. Three alternative approaches were evaluated and rejected: a buy-versus-build assessment favored build (lower long-term TCO), a big-bang deployment was rejected in favor of phased rollout (lower risk), and a do-nothing option was rejected due to increasing error rates and growing stakeholder dissatisfaction with the current process.",
            ),
            SlideData(
                index=6, title="Thank You", subtitle="Questions and open discussion.",
                bullets=[
                    "The project team is available for a detailed walkthrough of the implementation plan, technical architecture, and financial model in a follow-up session scheduled for next week. Additional materials are available upon request.",
                    "Stakeholder feedback on the proposed approach is welcome and will be incorporated into the final implementation plan. A feedback form has been distributed and responses will be reviewed by the steering committee.",
                    "Questions and open discussion.",
                ],
                notes="Close the discussion.",
                layout="content", variant="closing",
                visual_direction="Dedicated final thank-you slide with dark Citi-style background.",
                callout="The team welcomes feedback and is available for detailed follow-up sessions on implementation, architecture, and financial modeling.",
                narrative_context="This concludes the proposal presentation for Project Alpha. The steering committee will reconvene in two weeks to review the feedback collected during this session and issue a formal decision on project funding and initiation.",
            ),
        ]

    return [
        SlideData(
            index=1, title="Client Name Proposal", subtitle="Strategic financing proposal",
            bullets=[
                "This strategic financing proposal is prepared for Client Name, reflecting a comprehensive analysis of their capital structure, growth trajectory, and funding requirements through 2028. The recommendation leverages Citi's full balance sheet capabilities and industry expertise.",
                "The proposal is dated June 2026 and is based on the client's most recent financial statements, management projections, and strategic plan as shared during the March 2026 pitch meeting. All assumptions have been validated against publicly available peer benchmarks.",
                "Client Name operates across 12 countries with $4.2B in annual revenue and has maintained an investment-grade credit rating of BBB+ with stable outlook from both major rating agencies. Their existing banking relationship with Citi spans three years across treasury and trade services.",
                "The proposed financing structure includes a $500M senior secured credit facility with accordion features, supported by Citi's industry-leading syndication capabilities across 95+ markets. The facility carries an initial tenor of five years with two one-year extension options.",
                "This engagement represents a strategic opportunity to deepen the relationship with a high-quality client in a priority sector, with significant cross-sell potential in M&A advisory, FX hedging, and working capital solutions. Estimated first-year relationship revenue is $4.2M.",
                "Execution timeline targets term sheet delivery within two weeks, credit committee approval within six weeks, and financial close within ten weeks of mandate. A dedicated six-person team has been pre-assigned to ensure rapid execution.",
            ],
            notes="Title slide with client info.",
            layout="title", variant="cover",
            visual_direction="Framework cover slide with large title, subtitle, and Citi accent.",
            callout="A $500M strategic financing proposal leveraging Citi's global syndication network and full relationship capabilities for a BBB+ rated client.",
            narrative_context="Client Name engaged Citi in March 2026 to evaluate strategic financing options to support their next phase of growth, including potential M&A activity and capital expenditure programs. The client currently maintains relationships with three other relationship banks and has indicated a preference to consolidate banking relationships. Citi's proposal is designed to demonstrate superior execution capability, competitive pricing, and relationship depth to win lead arranger status.",
        ),
        SlideData(
            index=2,
            title="Citi can unlock flexible growth capital while preserving strategic options",
            bullets=[
                "The proposed $500M senior secured credit facility is structured with maximum flexibility, including an accordion feature that can expand the facility to $750M without requiring new lender syndication. This headroom supports both organic growth initiatives and bolt-on acquisition opportunities identified in the client's strategic plan.",
                "Pricing is competitive at SOFR + 175bps for the drawn portion with a 35% undrawn commitment fee, incorporating a sustainability-linked margin ratchet that adjusts pricing by +/- 5bps based on achievement of two ESG metrics. This green financing option differentiates Citi from competing proposals.",
                "Citi's global network spans 95+ countries with on-the-ground presence in all 12 markets where the client currently operates, enabling seamless cross-border execution and local currency capabilities. This geographic alignment reduces execution risk and accelerates drawdown timelines.",
                "The dedicated relationship team includes senior coverage bankers, industry specialists from the Technology sector team, product experts from Leveraged Finance and Syndications, and local market coverage in each operating jurisdiction. The proposed team averages 15 years of sector experience.",
                "Citi's capital markets franchise, ranked #1 in syndicated loans by volume for five consecutive years, provides certainty of execution and access to the deepest institutional investor base. The 2025 league table position was $125B in syndicated loan volume across 340 transactions.",
                "A detailed term sheet has been prepared alongside commitment letters from two anchor investors, providing the client with a high degree of certainty on both pricing and capacity. The anchor commitments total $250M and are subject to credit committee approval only.",
            ],
            notes="Outcome-focused summary.",
            layout="content", variant="big_statement",
            visual_direction="Big statement slide with one executive takeaway.",
            callout="A $500M flexible facility with accordion capacity, sustainability-linked pricing, and Citi's #1 ranked syndication platform delivers unmatched execution certainty.",
            narrative_context="The financing landscape for investment-grade corporates has evolved significantly in 2026, with increased lender appetite for sustainability-linked structures and accordion features. Citi's syndication platform has executed 12 comparable transactions in the past 18 months, all achieving or exceeding the target size. The proposed structure reflects lessons learned from those transactions, including refinements to covenant packages and pricing grids that have improved execution outcomes.",
        ),
        SlideData(
            index=3, title="Situation", subtitle="Client context and market backdrop",
            bullets=[
                "Client Name is seeking $500M in growth capital to fund a three-year strategic plan that includes organic expansion into two new geographic markets, development of a next-generation technology platform, and opportunistic bolt-on acquisitions. The plan targets $700M in incremental revenue by fiscal 2028.",
                "The client holds a strong market position as the #3 player in a $45B addressable market that is growing at 12.4% CAGR, with particular strength in the mid-market segment where they command 18% market share. Recent market share gains of 230 basis points over the past two years demonstrate competitive momentum.",
                "An existing banking relationship with Citi since 2022 includes treasury management, trade finance, and a $100M revolving credit facility that has been fully utilized for the past eight months. The relationship has generated $1.8M in annual revenue with a return on equity of 14.2%. Client satisfaction scores rank Citi second among their relationship banks.",
                "The client's leverage profile has improved from 3.2x net debt/EBITDA in FY2024 to 2.8x in FY2025, driven by strong free cash flow generation of $340M and disciplined working capital management. Pro forma leverage post-financing would be 3.5x, within the BBB+ peer median range of 2.5x-3.5x.",
                "Three competitor banks have already submitted preliminary proposals, with pricing ranging from SOFR + 165bps to SOFR + 195bps and facility sizes from $400M to $600M. Citi's proposal must differentiate on structure flexibility, execution certainty, and relationship value to win the mandate.",
                "The regulatory environment remains favorable for financial sponsor and corporate lending, with no material changes anticipated in capital adequacy requirements for investment-grade facilities. The proposed structure has been reviewed for regulatory compliance across all applicable jurisdictions.",
            ],
            notes="Client context from prompt only.",
            layout="content", variant="split_image",
            visual_direction="Two-column slide with left narrative and right visual.",
            callout="Client Name seeks $500M to fund a strategic plan targeting $700M incremental revenue by 2028, with Citi facing competition from three incumbent banks.",
            narrative_context="This engagement comes at a pivotal time for Client Name, which has completed a two-year operational restructuring that improved EBITDA margins from 28% to 34%. The success of the restructuring has positioned the company for an aggressive growth phase, and management has indicated that the selected financing partner will have the opportunity to lead a potential IPO within 18-24 months. This makes the current mandate strategically important beyond the immediate financing need.",
        ),
        SlideData(
            index=4,
            title="Citi Solution",
            bullets=[
                "The recommended solution is a $500M senior secured credit facility with a five-year tenor, featuring an accordion expansion option to $750M and two one-year extension options at the client's discretion. The facility is structured as a term loan A with a 3-year drawn period followed by 2-year amortization.",
                "Competitive pricing of SOFR + 175bps with a sustainability-linked margin ratchet of +/- 5bps tied to two ESG metrics: greenhouse gas emission reduction (scope 1 and 2) and diversity spend percentage. This structure positions Citi as a leader in sustainable finance while offering tangible pricing benefits for the client.",
                "The dedicated relationship team comprises six senior bankers including the Managing Director of Technology Coverage, the Head of Syndicated Finance, dedicated sustainable finance advisors, and local market coverage in all 12 client markets. The team brings combined experience of 90+ years across 30 comparable transactions.",
                "The green financing option is supported by Citi's Sustainable Finance Framework, which has been reviewed by a second-party opinion provider and aligns with ICMA Green Bond Principles. Eligible use cases include renewable energy investments, energy efficiency improvements, and sustainable supply chain initiatives.",
                "A comprehensive ancillary services package is included, covering FX hedging across 18 currency pairs at preferential rates, enhanced treasury management with API-based integration, and dedicated trade finance capabilities with reduced pricing on LC issuance.",
                "Execution roadmap includes commitment letter within 5 business days of mandate, definitive documentation within 21 days, credit committee approval in week 6, and financial close in week 10. A dedicated execution team of 12 professionals has been pre-assigned to ensure timeline certainty.",
            ],
            notes="Product fit, avoid guarantees.",
            layout="content", variant="three_points",
            blocks=[{"type": "cards", "columns": 3, "items": [{"title": "Flexible Facility", "body": "Senior secured credit facility aligned to growth needs.", "icon": "financial"}, {"title": "Sustainable Option", "body": "Green financing structure where eligible.", "icon": "growth"}, {"title": "Dedicated Team", "body": "Coordinated coverage across product and relationship teams.", "icon": "client"}]}],
            visual_direction="Three framework cards for solution pillars.",
            callout="A $500M sustainability-linked facility with accordion capacity, competitive pricing, and a dedicated six-person team differentiates Citi from competing proposals.",
            narrative_context="Citi's proposed solution builds on successful execution of 15 comparable financings in the past 18 months, averaging 110% of target size across all mandates. The sustainability-linked structure has been particularly well received by institutional investors, with 80% of recent syndications attracting oversubscription. The ancillary services package is designed to increase wallet share from the current 18% to a target of 35% within 12 months of close.",
        ),
        SlideData(
            index=5, title="Market Overview", subtitle="Industry landscape",
            bullets=[
                "The addressable market for the client's products and services is valued at $45B and is projected to grow at a CAGR of 12.4% through 2030, driven by digital transformation, regulatory complexity, and increasing demand for integrated solutions. The highest growth segments are projected to expand at 18-22% CAGR.",
                "The competitive landscape includes five major players and numerous niche specialists, with the top three players (including Client Name) commanding 47% combined market share. Industry concentration has increased over the past three years due to two significant mergers and the exit of three regional players.",
                "Regulatory developments in the client's primary markets remain broadly favorable, with no material compliance cost increases anticipated in the near term. However, proposed data localization requirements in two operating jurisdictions could increase infrastructure costs by an estimated $8M annually if enacted.",
                "Technology disruption is creating both opportunity and risk: AI-powered solutions are expected to reduce operating costs by 20-30% industry-wide by 2028, but firms that fail to invest may lose 15-20% market share to more agile competitors. The client's technology investment plans directly address this risk.",
                "Cross-border activity in the sector has increased 34% year-over-year, with $12B in announced M&A transactions in the first five months of 2026. This trend favors well-capitalized players with global reach and creates financing opportunities for relationship banks with cross-border execution capabilities.",
                "Environmental and social considerations are increasingly influencing purchasing decisions, with 67% of corporate clients in a recent survey indicating they would pay a premium of up to 5% for products from providers with strong ESG credentials. This trend supports the client's sustainability investments.",
            ],
            notes="Deep dive into market.",
            layout="section_divider", variant="split_image",
            visual_direction="Full-bleed image divider with centered section title.",
            callout="A $45B market growing at 12.4% CAGR with technology disruption creating both opportunity and consolidation risk for incumbent players.",
            narrative_context="The market overview reflects analysis conducted by Citi's industry research team, incorporating data from five independent sources including the industry trade association, two consulting firm studies, government statistics, and Citi's proprietary transaction database. The team has a strong track record of accurate market forecasting, with a mean absolute error of approximately 2.5% on CAGR projections over the past three years.",
        ),
        SlideData(
            index=6,
            title="Financial Analysis",
            bullets=[
                "Client Name generated $2.1B in revenue in FY2025, representing 16.7% year-over-year growth, driven by strong organic performance (11.2%) and the contribution of two small acquisitions completed in Q3 2025. Revenue growth is expected to accelerate to 18-20% in FY2026 based on current pipeline visibility and signed contracts.",
                "EBITDA margin of 34% reflects sustained improvement from 28% in FY2023, driven by operational restructuring, procurement optimization, and mix shift toward higher-margin service lines. The 600bps margin expansion over two years exceeds the peer average of 380bps and demonstrates management execution capability.",
                "Debt-to-equity ratio of 0.8x is conservative for the sector, providing significant debt capacity headroom. Pro forma leverage of 3.5x net debt/EBITDA (including the proposed financing) remains within the BBB+ rating guidelines and is supported by strong interest coverage of 8.2x based on FY2025 EBITDA.",
                "Free cash flow generation of $340M in FY2025 represented a 16.2% free cash flow margin, with conversion from EBITDA of 68%. FCF is projected to grow to $420M in FY2026 and $510M in FY2027, providing comfortable debt service coverage even under stressed scenarios.",
                "Working capital efficiency has improved significantly, with days sales outstanding decreasing from 52 days in FY2023 to 41 days in FY2025, driven by implementation of an automated invoicing and collections system. Inventory turnover has also improved from 4.8x to 6.1x over the same period.",
                "Capital expenditure of $180M in FY2025 (8.6% of revenue) is expected to increase to $250M in FY2026 as the technology platform investment program ramps up. Capex is projected to moderate to approximately 9% of revenue from FY2027 onward as the platform reaches steady state.",
                "Revenue composition by segment shows healthy diversification: 42% from the core mid-market segment, 28% from enterprise clients, 18% from government contracts, and 12% from international operations. No single client accounts for more than 5% of total revenue, reducing concentration risk.",
            ],
            notes="Chart data recommended.",
            layout="chart", variant="big_stat",
            blocks=[{"type": "stat", "value": "34%", "label": "FY2025 EBITDA margin"}],
            visual_direction="Left metric callouts with right chart region and source note.",
            callout="Revenue growth of 16.7% to $2.1B with 34% EBITDA margin and 0.8x debt/equity demonstrates strong credit quality and debt capacity for the proposed financing.",
            narrative_context="All financial data presented in this slide is sourced from the client's audited annual financial statements for FY2025 and management-prepared internal financial reports for FY2026 projections. Citi's Financial Analysis team has independently verified key metrics against supporting documentation and industry benchmarks. The analysis follows Citi's standard credit underwriting framework and has been reviewed by the industry credit officer.",
        ),
        SlideData(
            index=7,
            title="Platform Capabilities",
            bullets=[
                "Citi's global distribution network spans 95+ countries, providing on-the-ground presence in all 12 markets where the client currently operates and all three expansion markets identified in their strategic plan. This geographic alignment eliminates the need for the client to manage multiple banking relationships across jurisdictions.",
                "Citi has ranked #1 in syndicated loans by volume for five consecutive years, executing $125B in loan volume across 340 transactions in 2025. The 2026 league table position through June shows $72B in executed volume, maintaining the top position with a 12.8% market share.",
                "The 24/7 client support model provides dedicated coverage through a single point of contact during business hours and a rotating on-call structure for after-hours needs. The service level agreement guarantees response times of 2 hours for standard inquiries and 30 minutes for urgent matters.",
                "Citi's sustainable finance franchise has arranged $22B in green and sustainability-linked loans across 60 transactions since 2022, including five transactions in the client's industry sector. Two dedicated sustainable finance advisors are available to support the structuring and reporting requirements.",
                "The firm's technology platform supports real-time cash position visibility, automated reconciliation, and API-based integration with the client's existing ERP systems. This connectivity reduces manual intervention and accelerates transaction processing times by approximately 40% compared to industry benchmarks.",
                "Citi's M&A advisory team has completed 35 transactions in the client's sector totaling $18B in aggregate value over the past three years, providing deep industry knowledge that can be leveraged for strategic advice beyond the financing mandate. Five senior M&A bankers are available for cross-referral opportunities.",
            ],
            notes="Differentiators only.",
            layout="content", variant="comparison_table",
            blocks=[{"type": "table", "headers": ["Capability", "Client Impact"], "rows": [["Global network", "Distribution in 95+ countries"], ["Loan franchise", "Leading syndicated loan execution"], ["Support model", "Always-on relationship coverage"]]}],
            visual_direction="Framework comparison table with Citi advantages.",
            callout="#1 in syndicated loans for five consecutive years, 95+ country network, and $22B in sustainable finance transactions demonstrate unmatched platform capabilities.",
            narrative_context="Citi's platform capabilities have been recognized through multiple industry awards in 2025, including Best Investment Bank in Sustainable Finance and Best Syndicated Loan Arranger. The platform's scale and reach are the primary differentiators versus competitor banks, with the global network being particularly valued by clients with international operations. The capabilities presented reflect live, current-state data as of the proposal date and are not aspirational projections.",
        ),
        SlideData(
            index=8,
            title="Next Steps",
            bullets=[
                "Term sheet review and negotiation to be completed by June 30, 2026, with Citi's credit-approved term sheet already prepared and available for client review. A dedicated documentation team with 15 years of leveraged finance experience will lead the negotiation process.",
                "Credit committee approval process is scheduled for Q3 2026, with the formal submission package to be submitted by July 15. The credit officer has provided preliminary feedback indicating strong support for the transaction structure, subject to the completion of due diligence.",
                "Financial close is targeted for September 30, 2026, allowing for an 8-week execution window that includes documentation, due diligence, syndication, and conditions precedent satisfaction. A pre-close readiness checklist has been prepared with 47 milestones tracked weekly.",
                "Syndication strategy targets a club deal structure with 5-7 relationship lenders, allowing Client Name to diversify its banking relationships while maintaining Citi as administrative agent. A detailed syndication memorandum is being prepared with support from the industry research team.",
                "Conditions precedent include customary legal opinions, corporate authorizations, security perfection, and delivery of audited FY2026 interim financial statements. A dedicated conditions precedent tracker will be established and shared weekly to ensure transparency on readiness.",
                "Post-close relationship management plan includes quarterly business reviews, annual relationship surveys, and a dedicated client service plan that maps Citi services to 18 identified client needs across treasury, lending, markets, and advisory.",
            ],
            notes="3 action items before the final thank-you slide.",
            layout="next_steps", variant="process",
            blocks=[{"type": "process", "steps": [{"title": "Review", "body": "Term sheet by June 30."}, {"title": "Approve", "body": "Credit committee in Q3."}, {"title": "Close", "body": "Target September 2026."}]}],
            visual_direction="Framework process slide with concrete next actions.",
            callout="Target financial close by September 30, 2026, with term sheet review by June 30 and credit committee approval in Q3.",
            narrative_context="The execution timeline reflects Citi's standard process for investment-grade credit facilities of this size and complexity. The timeline has been stress-tested against 12 comparable transactions executed in the past 12 months, all of which closed within their planned windows. Contingency buffers have been built into each phase to accommodate unforeseen delays, and a rapid escalation protocol is in place for any issues requiring senior management attention.",
        ),
        SlideData(
            index=9, title="Thank You", subtitle="Questions and open discussion.",
            bullets=[
                "The deal team is available for a detailed Q&A session on the proposed structure, financial analysis, and execution plan. Additional materials including the full credit memorandum and financial model are available in the virtual data room.",
                "Citi looks forward to the opportunity to serve as lead arranger for this important transaction and is committed to delivering best-in-class execution and ongoing relationship coverage. The team's compensation is performance-based, ensuring full alignment with the client's objectives.",
                "Questions and open discussion.",
            ],
            notes="Close the discussion.",
            layout="content", variant="closing",
            visual_direction="Dedicated final thank-you slide with dark Citi-style background.",
            callout="Citi's team is fully aligned with the client's objectives and committed to delivering best-in-class execution across financing, advisory, and ongoing relationship coverage.",
            narrative_context="This proposal represents the culmination of a 10-week preparation effort involving 25 professionals across six Citi product groups. The team is confident that the proposed structure, pricing, and execution plan offer a compelling value proposition that differentiates Citi from the competing proposals. A formal response is requested by June 30, 2026, to proceed with term sheet finalization.",
        ),
    ]


def _chunk_text(text: str) -> list[str]:
    """Split a source document into chunks on blank-line paragraph boundaries."""
    parts = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if not parts:
        parts = [text.strip() or "Untitled"]
    return parts[:MAX_SCRIPT_SLIDES]


def _script_mock_slides(text: str) -> list[SlideData]:
    """Offline approximation of the script-summarization 'brain'.

    Chunks the source into slides, derives a punchy-ish title and up to 6
    bullets per chunk, and preserves the original chunk text as speaker notes.
    """
    slides: list[SlideData] = []
    for i, chunk in enumerate(_chunk_text(text), 1):
        lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
        title = (lines[0] if lines else f"Section {i}")[:80]
        body = " ".join(lines[1:]) if len(lines) > 1 else (lines[0] if lines else "")
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body) if s.strip()]
        bullets = [s[:160] for s in sentences[:6]] or [title]
        slides.append(
            SlideData(
                index=i,
                title=title,
                bullets=bullets,
                notes=chunk.strip(),
                layout="title" if i == 1 else "content",
                variant="cover" if i == 1 else "closing" if "next step" in title.lower() else "split_image",
                visual_direction="Auto-generated from source chunk.",
                callout=bullets[0] if bullets else None,
                narrative_context=f"This slide was auto-generated from the source document section {i}. The content has been summarized to retain the key points and preserve the original meaning for presentation purposes.",
            )
        )
    return slides
