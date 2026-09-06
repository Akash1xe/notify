import numpy as np

from app.services.screenshot_candidate_service import KeptCandidate, ScreenshotCandidateService


def service() -> ScreenshotCandidateService:
    return ScreenshotCandidateService(storage=None, prepared=None, states=None)  # type: ignore[arg-type]


def test_identical_frames_are_near_duplicates() -> None:
    candidates = service()
    frame = np.full((120, 200, 3), 240, dtype=np.uint8)
    frame[30:80, 50:55] = 20

    first = candidates.fingerprint(frame)
    second = candidates.fingerprint(frame.copy())
    match, hash_distance, mean_difference = candidates.find_duplicate(
        second,
        [KeptCandidate(candidate_index=7, fingerprint=first)],
    )

    assert match == 7
    assert hash_distance == 0
    assert mean_difference == 0.0


def test_small_encoding_noise_can_still_match() -> None:
    candidates = service()
    frame = np.full((120, 200, 3), 220, dtype=np.uint8)
    frame[25:85, 75:80] = 10
    noisy = frame.copy()
    noisy[0:10, 0:10] = 221

    first = candidates.fingerprint(frame)
    second = candidates.fingerprint(noisy)
    match, _, mean_difference = candidates.find_duplicate(
        second,
        [KeptCandidate(candidate_index=2, fingerprint=first)],
    )

    assert match == 2
    assert mean_difference is not None
    assert mean_difference <= candidates.config.max_mean_abs_difference


def test_new_written_content_is_not_removed_as_duplicate() -> None:
    candidates = service()
    before = np.full((180, 320, 3), 245, dtype=np.uint8)
    before[40:120, 60:66] = 15

    after = before.copy()
    # A meaningful new line of writing occupies enough pixels to survive the
    # thumbnail comparison even though most of the board remains unchanged.
    after[95:102, 70:250] = 15
    after[110:117, 90:270] = 15

    previous = candidates.fingerprint(before)
    current = candidates.fingerprint(after)
    match, _, _ = candidates.find_duplicate(
        current,
        [KeptCandidate(candidate_index=0, fingerprint=previous)],
    )

    assert match is None


def test_recent_window_can_find_repeated_slide() -> None:
    candidates = service()
    slide_a = np.full((100, 180, 3), 250, dtype=np.uint8)
    slide_a[20:70, 20:25] = 0
    slide_b = np.full((100, 180, 3), 180, dtype=np.uint8)
    slide_b[30:35, 30:150] = 0

    recent = [
        KeptCandidate(candidate_index=3, fingerprint=candidates.fingerprint(slide_a)),
        KeptCandidate(candidate_index=4, fingerprint=candidates.fingerprint(slide_b)),
    ]
    match, _, _ = candidates.find_duplicate(candidates.fingerprint(slide_a.copy()), recent)

    assert match == 3
