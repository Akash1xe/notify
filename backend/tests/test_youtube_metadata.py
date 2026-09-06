from app.schemas.video import VideoMetadata
from app.services.youtube_service import YoutubeInspection, YoutubeService


def test_metadata_mapping(monkeypatch) -> None:
    raw = {
        "id": "dQw4w9WgXcQ",
        "title": "Binary Search",
        "duration": 3661,
        "channel": "Teacher",
        "thumbnail": "https://i.ytimg.com/vi/test/hqdefault.jpg",
        "height": 1080,
        "is_live": False,
    }
    service = YoutubeService()
    monkeypatch.setattr(
        service,
        "_extract",
        lambda _: YoutubeInspection("dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", raw),
    )
    metadata = service.metadata("ignored")
    assert isinstance(metadata, VideoMetadata)
    assert metadata.title == "Binary Search"
    assert metadata.duration_formatted == "1:01:01"
    assert metadata.resolution == "1080p"
