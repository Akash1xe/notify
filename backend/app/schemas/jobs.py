from __future__ import annotations

from pydantic import BaseModel
from app.models.job import JobStatus


class JobErrorResponse(BaseModel):
    code: str
    message: str


class JobResponse(BaseModel):
    job_id: str
    video_id: str
    status: JobStatus
    progress: float
    message: str
    error: JobErrorResponse | None = None
