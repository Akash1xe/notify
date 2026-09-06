# Notify — Lecture to PDF

Notify is a local-first lecture processing application. It accepts a YouTube lecture URL, prepares and verifies a local processing copy, then builds a sequential frame timeline that later phases will use to detect meaningful teaching-state changes and ultimately generate visual PDF notes.

> Current milestone: **Phase 2.1 complete — streaming video reader and frame timestamp timeline**.

## Current capabilities

### Phase 1 — local lecture preparation

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

### Phase 2.1 — video reader and frame timeline

- OpenCV-based sequential video decoding
- One frame at a time in memory rather than loading the complete lecture
- Ordered frame indexes from the beginning to the end of the prepared lecture
- Per-frame timestamps with FPS-based fallback when container timestamps are unavailable
- Monotonic timestamp protection
- Background frame-analysis job with progress polling
- Duplicate active frame-analysis job protection per video
- Persisted frame timeline as JSON Lines
- Persisted frame-timeline summary
- Timeline cache invalidation if the prepared source file changes
- Restart-aware analysis job recovery
- Frontend `Start Frame Analysis` workflow and progress screen
- Final timeline summary showing decoded frame count, FPS, dimensions, and last frame timestamp

## Not implemented yet

Phase 2.1 deliberately does **not** decide which frames are educationally important. The following are still future phases:

- visual-change detection
- scene/slide transition detection
- screenshot candidate selection
- SSIM/perceptual hashing and duplicate screenshot removal
- stable-writing detection
- erase/content-protection detection
- OCR
- Whisper/transcripts
- topic detection
- semantic importance analysis
- coverage verification
- PDF generation

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
- OpenCV (`opencv-python-headless`)
- FFmpeg / ffprobe (system tools)

## Repository layout

```text
notify/
├── frontend/               Next.js UI
├── backend/                FastAPI local processing service
├── downloads/              Verified prepared videos + analysis data (ignored by Git)
├── temp/                   Temporary job workspaces (ignored by Git)
├── output/                 Future generated PDFs (ignored by Git)
├── .github/workflows/      CI for backend tests + frontend build
├── .gitignore
└── README.md
```

### Runtime storage

A successfully prepared and frame-scanned lecture is retained as:

```text
downloads/<video_id>/
├── lecture.mp4
├── metadata.json
└── analysis/
    ├── frame-timeline.jsonl
    └── frame-timeline-summary.json
```

`frame-timeline.jsonl` contains one compact record per decoded frame:

```json
{"frame_index": 0, "timestamp_seconds": 0.0}
{"frame_index": 1, "timestamp_seconds": 0.033333}
```

The timeline intentionally stores timestamps rather than frame images. Later analysis phases can stream the lecture again and use these timestamps without creating thousands of image files unnecessarily.

Preparation and analysis jobs use isolated workspaces under `temp/<job_id>/`. Final persistent data is only written after the relevant operation succeeds.

## Requirements

Install these locally:

- Node.js 20+ recommended
- Python 3.11+ recommended
- FFmpeg (must include both `ffmpeg` and `ffprobe`)

Python dependencies, including OpenCV, are installed through `backend/requirements.txt`.

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

The backend can still start and fetch YouTube metadata when FFmpeg is unavailable; only local media preparation is blocked.

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

Optional backend environment variables are documented in `backend/.env.example`.

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

## Current user flow

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
READY
        ↓
Start Frame Analysis
        ↓
Sequentially decode lecture with OpenCV
        ↓
Record every frame index + timestamp
        ↓
Persist frame timeline
        ↓
FRAME TIMELINE READY
```

If the same prepared video and matching timeline are submitted later, the backend verifies the retained artifacts and reuses them instead of repeating unnecessary work.

## Main API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Backend connectivity |
| POST | `/api/video/validate` | Validate and normalize a YouTube URL |
| POST | `/api/video/metadata` | Validate and return normalized metadata |
| POST | `/api/video/prepare` | Create/reuse a local preparation job |
| GET | `/api/video/{video_id}/status` | Check whether local media is prepared |
| DELETE | `/api/video/{video_id}/local` | Remove a retained local copy and its analysis data |
| GET | `/api/jobs/{job_id}` | Poll preparation state |
| POST | `/api/analysis/start` | Start/reuse a frame-timeline analysis job |
| GET | `/api/analysis/jobs/{job_id}` | Poll frame-analysis state |
| GET | `/api/analysis/{video_id}/timeline` | Read the completed frame-timeline summary |
| GET | `/api/storage/status` | Local storage usage |
| POST | `/api/storage/cleanup` | Remove stale temporary data |
| GET | `/api/system/status` | FFmpeg/filesystem capability check |

## Processing states

Jobs use centralized status values. Preparation uses:

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

Frame-timeline analysis additionally uses:

```text
SCANNING_FRAMES
```

Jobs also carry a type:

```text
PREPARATION
FRAME_TIMELINE
```

This allows recovery and API behavior to distinguish acquisition jobs from analysis jobs while preserving the same job infrastructure.

## Recovery behavior

- Completed prepared videos survive backend restarts because final media and manifests are stored in `downloads/`.
- Completed frame timelines survive backend restarts under the video's `analysis/` directory.
- A timeline is considered reusable only when its recorded source size and modification time still match `lecture.mp4`.
- In-progress preparation jobs found after a restart are marked as preparation interruptions.
- In-progress frame-timeline jobs found after a restart are marked as analysis interruptions.
- Corrupt or incomplete final media is never trusted solely because a file exists.
- Partial and stale temp workspaces can be removed with the cleanup endpoint/UI.
- Active preparation and frame-analysis workspaces are protected from cleanup.

## Phase boundary

Video acquisition remains separate from video understanding:

```text
YouTube URL
   ↓ Phase 1
Verified local lecture.mp4
   ↓ Phase 2.1
Ordered frame timeline
   ↓ Phase 2.2+
Visual-change / teaching-state analysis
```

The frame-timeline implementation deliberately streams frames and discards each image after its timestamp is recorded. This keeps memory usage bounded even for long lectures.

## Tests and CI

Backend:

```powershell
cd backend
pytest -q
```

Frontend:

```powershell
cd frontend
npm run typecheck
npm run build
```

GitHub Actions runs both backend tests (with FFmpeg installed) and the frontend typecheck/build on pushes to `main` and on pull requests.

## Next milestone

**Phase 2 — Sub-phase 2: Visual Change Detection / Frame Difference Engine** will compare streamed frames conservatively to identify regions/timestamps where meaningful screen content changes, without yet deciding final screenshots.
