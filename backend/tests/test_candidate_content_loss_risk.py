from app.services.screenshot_candidate_service import ScreenshotCandidateService


def service() -> ScreenshotCandidateService:
    return ScreenshotCandidateService(storage=None, prepared=None, states=None)  # type: ignore[arg-type]


def test_scene_replacement_protects_previous_candidate() -> None:
    records = [
        {"edge_density": 0.04, "contrast_std": 0.2, "source_change_kind": "LOCAL"},
        {"edge_density": 0.04, "contrast_std": 0.2, "source_change_kind": "SCENE"},
    ]
    count = service().mark_content_loss_risks(records)
    assert count == 1
    assert records[0]["content_loss_risk"] is True
    assert records[0]["content_loss_reason"] == "SCENE_REPLACEMENT"


def test_sharp_detail_drop_protects_previous_candidate() -> None:
    records = [
        {"edge_density": 0.05, "contrast_std": 0.25, "source_change_kind": "LOCAL"},
        {"edge_density": 0.01, "contrast_std": 0.10, "source_change_kind": "LOCAL"},
    ]
    count = service().mark_content_loss_risks(records)
    assert count == 1
    assert records[0]["content_loss_risk"] is True
    assert records[0]["content_loss_reason"] == "DETAIL_DROP"
