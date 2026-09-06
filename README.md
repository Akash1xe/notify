# Notify — Lecture to PDF

Notify is a local-first lecture processing application. In Phase 1 it accepts a YouTube lecture URL, validates the video, previews metadata, downloads a processing-friendly local copy, verifies that media with FFmpeg/ffprobe, and keeps a recoverable local workspace ready for the frame-analysis engine that begins in Phase 2.

> Current milestone: **Phase 1 complete — verified local lecture preparation**.

## What Phase 1 supports

- YouTube URL input and client-side validation
- Authoritative backend URL parsing and video-ID normalization
- yt-dlp accessibility checks without downloading during metadata lookup
- Video metadata preview (title, channel, duration, thumbnail, resolution)
- Live-video rejection
- Local video preparation with a 720p-first policy
- Background preparation jobs and progress polling
- FFmpeg/ffprobe detection and media verification
- Predictable local storage (`downloads/<video_id>/lecture.mp4`)
- Prepared-video manifests and restart-safe reuse
- Interrupted-job recovery and stale temp cleanup
- Duplicate preparation protection for the same video
- Storage status, temporary-data cleanup, and local-copy deletion
- Final `READY` state for Phase 2

## Not implemented yet

Phase 1 deliberately does **not** include:

- frame extraction or OpenCV analysis
- screenshot selection
- SSIM/perceptual hashing
- stable-writing/erase detection
- OCR
- Whisper/transcripts
- topic detection
- PDF generation

Those begin in Phase 2 and later phases.

## Stack

### Frontend
- Next.js (App Router)
- TypeScript
- Tailwind CSS

### Backend
- Python
- FastAPI
- Uvicorn
- yt-dlp
- FFmpeg / ffprobe (system tools)

## Repository layout

```text
notify/
├── frontend/               Next.js UI
├── backend/                FastAPI local processing service
├── downloads/              Verified prepared videos (ignored by Git)
├── temp/                   Temporary job workspaces (ignored by Git)
├── output/                 Future generated PDFs (ignored by Git)
├── .gitignore
└── README.md
```

### Runtime storage

A successfully prepared lecture is retained as:

```text
downloads/<video_id>/
├── lecture.mp4
└── metadata.json
```

Preparation work happens in an isolated job workspace under `temp/<job_id>/`. The final media is only moved into `downloads/` after verification succeeds.

## Requirements

Install these locally:

- Node.js 20+ recommended
- Python 3.11+ recommended
- FFmpeg (must include both `ffmpeg` and `ffprobe`)

### Windows FFmpeg

Install FFmpeg using your preferred package manager, for example with winget if available:

```powershell
winget install Gyan.FFmpeg
```

Open a new terminal afterwards and verify:

```powershell
ffmpeg -version
ffprobe -version
```

The backend can still start and fetch YouTube metadata when FFmpeg is unavailable; only video preparation is blocked.

## Backend setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend URL:

```text
http://localhost:8000
```

Health endpoint:

```text
GET http://localhost:8000/health
```

Optional backend environment variables are documented in `backend/.env.example`. The application does not require secrets in Phase 1.

## Frontend setup

```powershell
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

Frontend URL:

```text
http://localhost:3000
```

Default frontend environment:

```text
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Phase 1 user flow

```text
Paste YouTube URL
        ↓
Validate and fetch metadata
        ↓
Preview title / thumbnail / duration
        ↓
Prepare Video
        ↓
Background download (720p-first)
        ↓
Merge / normalize media if needed
        ↓
Verify with ffprobe
        ↓
Finalize atomically
        ↓
READY FOR FRAME ANALYSIS
```

If the same valid video is submitted later, the backend checks the retained manifest and media file and reuses it instead of downloading it again.

## Main API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Backend connectivity |
| POST | `/api/video/validate` | Validate and normalize a YouTube URL |
| POST | `/api/video/metadata` | Validate and return normalized metadata |
| POST | `/api/video/prepare` | Create/reuse a local preparation job |
| GET | `/api/video/{video_id}/status` | Check whether local media is prepared |
| DELETE | `/api/video/{video_id}/local` | Remove a retained local copy |
| GET | `/api/jobs/{job_id}` | Poll preparation state |
| GET | `/api/storage/status` | Local storage usage |
| POST | `/api/storage/cleanup` | Remove stale temporary data |
| GET | `/api/system/status` | FFmpeg/filesystem capability check |

## Processing states

Phase 1 uses a centralized lifecycle:

```text
QUEUED
DOWNLOADING
MERGING
VERIFYING
FINALIZING
READY
FAILED
INTERRUPTED
CANCELLED
```

The frontend additionally has its own UI workflow states for input, metadata loading, preparation, ready, and error presentation.

## Recovery behavior

- Completed prepared videos survive backend restarts because the final media and manifest are stored in `downloads/`.
- In-progress job manifests found after a restart are marked `INTERRUPTED` rather than being reported as permanently active.
- Corrupt or incomplete final media is never trusted solely because a file exists.
- Partial and stale temp workspaces can be removed with the cleanup endpoint/UI.
- The same video cannot start two simultaneous preparation jobs within one backend process.

## Phase 2 handoff contract

Phase 2 must operate on the **verified local video**, not on YouTube directly.

Phase 2 can assume:

- a valid `video_id` exists
- `downloads/<video_id>/lecture.mp4` is stable and no longer being written
- duration and prepared-video metadata are known
- the backend can resolve the absolute local path internally through the prepared-video service
- the file contains a readable video stream

The intended boundary is:

```text
YouTube URL
   ↓ Phase 1
Verified local lecture.mp4
   ↓ Phase 2+
Frame analysis
```

## Tests

Backend:

```powershell
cd backend
pytest
```

Frontend production build:

```powershell
cd frontend
npm run build
```
