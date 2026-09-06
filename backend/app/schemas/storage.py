from pydantic import BaseModel


class StorageStatusResponse(BaseModel):
    prepared_video_count: int
    downloads_size_bytes: int
    temp_size_bytes: int
    output_size_bytes: int
    free_space_bytes: int


class CleanupResponse(BaseModel):
    status: str = "completed"
    removed_temp_directories: int
    freed_bytes: int


class DeleteLocalResponse(BaseModel):
    status: str = "deleted"
    video_id: str
