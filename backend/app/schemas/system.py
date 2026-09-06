from pydantic import BaseModel


class SystemStatusResponse(BaseModel):
    backend: bool = True
    ffmpeg_available: bool
    ffprobe_available: bool
    download_directory_writable: bool
    temp_directory_writable: bool
