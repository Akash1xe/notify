from fastapi import APIRouter

from app.api import analysis, jobs, storage, system, video

api_router = APIRouter()
api_router.include_router(video.router)
api_router.include_router(analysis.router)
api_router.include_router(jobs.router)
api_router.include_router(storage.router)
api_router.include_router(system.router)
