from app.services.platform.dlp import DlpService
from app.models.schemas import SlideData


def test_scan_prompt_clean():
    dlp = DlpService()
    result = dlp.scan_prompt("Standard financing proposal with competitive terms")
    assert result == []


def test_scan_prompt_blocked():
    dlp = DlpService()
    result = dlp.scan_prompt("We guarantee returns of 15% with no risk")
    assert "guarantee returns" in result
    assert "no risk" in result


def test_scan_prompt_case_insensitive():
    dlp = DlpService()
    result = dlp.scan_prompt("Guaranteed Profit on this investment")
    assert "guaranteed profit" in result


def test_scan_prompt_blocks_account_like_numbers():
    dlp = DlpService()

    result = dlp.scan_prompt("Client account 123456789012 needs review")

    assert "account-like number" in result


def test_scan_prompt_blocks_email_addresses():
    dlp = DlpService()

    result = dlp.scan_prompt("Contact jane.client@example.com")

    assert "email address" in result


def test_scan_prompt_does_not_flag_uncertain_return():
    dlp = DlpService()

    result = dlp.scan_prompt("An uncertain return environment")

    assert "certain return" not in result


def test_scan_prompt_blocks_risk_free_variant():
    dlp = DlpService()

    result = dlp.scan_prompt("This is risk free")

    assert "risk-free" in result


def test_scan_slides():
    dlp = DlpService()
    slides = [
        "Standard content",
        "We guarantee returns if you invest",
    ]
    flagged = dlp.scan_slides(slides)
    assert len(flagged) == 1
    assert flagged[0]["slide_index"] == 2


def test_scan_slide_includes_title_bullets_and_notes():
    dlp = DlpService()
    slide = SlideData(
        index=4,
        title="Risk-free opportunity",
        bullets=["Standard bullet"],
        notes="No extra context",
        layout="content",
    )

    result = dlp.scan_slide(slide)

    assert "risk-free" in result


def test_scan_slide_blocks_integer_like_numeric_chart_values_for_account_detection():
    dlp = DlpService()
    slide = SlideData(
        index=5,
        title="Revenue overview",
        bullets=["Standard bullet"],
        notes="No extra context",
        layout="chart",
        chart_data={"categories": ["Q1"], "series": [{"name": "revenue", "values": [123456789012.0]}]},
    )

    result = dlp.scan_slide(slide)

    assert "account-like number" in result


def test_scan_slide_does_not_flag_ordinary_numeric_chart_values():
    dlp = DlpService()
    slide = SlideData(
        index=5,
        title="Revenue overview",
        bullets=["Standard bullet"],
        notes="No extra context",
        layout="chart",
        chart_data={"categories": ["Q1"], "series": [{"name": "revenue", "values": [125.0]}]},
    )

    result = dlp.scan_slide(slide)

    assert "account-like number" not in result


def test_scan_slide_blocks_chart_label_account_like_numbers():
    dlp = DlpService()
    slide = SlideData(
        index=6,
        title="Account overview",
        bullets=["Standard bullet"],
        notes="No extra context",
        layout="chart",
        chart_data={"categories": ["Account 123456789012"], "series": [{"name": "revenue", "values": [1.0]}]},
    )

    result = dlp.scan_slide(slide)

    assert "account-like number" in result


def test_scan_slide_includes_subtitle_blocks_and_image_prompts():
    dlp = DlpService()
    slide = SlideData(
        index=7,
        title="Clean title",
        kicker="SAFE",
        subtitle="Contact jane.client@example.com",
        bullets=["Standard bullet"],
        notes="No extra context",
        layout="content",
        blocks=[{"type": "cards", "items": [{"title": "Offer", "body": "Guaranteed profit claim"}]}],
        image_prompt="Executive meeting with account 123456789012 on screen",
        image_b64="guarantee returns inside binary-like field should be ignored",
    )

    result = dlp.scan_slide(slide)

    assert "email address" in result
    assert "guaranteed profit" in result
    assert "account-like number" in result
    assert "guarantee returns" not in result
