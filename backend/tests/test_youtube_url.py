import pytest

from app.core.errors import AppError
from app.utils.youtube_url import canonical_youtube_url, extract_video_id, normalize_youtube_url

VIDEO_ID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtube.com/watch?v={VIDEO_ID}",
        f"https://m.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube.com/watch?v={VIDEO_ID}&t=200&feature=share",
        f"https://youtu.be/{VIDEO_ID}?si=test",
    ],
)
def test_extract_supported_urls(url: str) -> None:
    assert extract_video_id(url) == VIDEO_ID


@pytest.mark.parametrize(
    "url",
    [
        "",
        "hello",
        "https://google.com",
        "https://youtube.com/",
        "https://youtube.com/watch?v=123",
        "ftp://youtube.com/watch?v=dQw4w9WgXcQ",
    ],
)
def test_reject_invalid_urls(url: str) -> None:
    with pytest.raises(AppError):
        extract_video_id(url)


def test_normalized_url() -> None:
    video_id, normalized = normalize_youtube_url(f"https://youtu.be/{VIDEO_ID}?si=test")
    assert video_id == VIDEO_ID
    assert normalized == canonical_youtube_url(VIDEO_ID)
