import shutil

import cv2
import numpy as np
import pytest

from app.services.ocr_service import OcrService


def test_real_tesseract_reads_generated_lecture_text(tmp_path) -> None:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        pytest.skip("Tesseract is not installed in this environment")

    image = np.full((180, 900, 3), 255, dtype=np.uint8)
    cv2.putText(
        image,
        "BINARY SEARCH",
        (35, 110),
        cv2.FONT_HERSHEY_SIMPLEX,
        2.0,
        (0, 0, 0),
        4,
        cv2.LINE_AA,
    )
    source = tmp_path / "lecture-slide.png"
    assert cv2.imwrite(str(source), image)

    service = OcrService(
        storage=None,  # type: ignore[arg-type]
        review=None,  # type: ignore[arg-type]
        topics=None,  # type: ignore[arg-type]
        tesseract_cmd=tesseract,
        language="eng",
        psm=11,
    )
    result = service._run_tesseract(source)

    assert result["has_text"] is True
    assert result["word_count"] >= 1
    normalized = result["text"].upper()
    assert "BINARY" in normalized or "SEARCH" in normalized
