# Notify — Lecture to PDF

Notify is a local-first lecture processing application. It accepts a YouTube lecture URL, prepares and verifies a local processing copy, analyzes every decoded frame transition, and identifies conservative stable teaching-state checkpoints for later screenshot extraction and PDF generation.

> Current milestone: **Phase 2.3 complete — stable teaching-state / writing-completion detection**.

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
- Persisted frame timeline as JSON Lines plus a validated summary
- Cache invalidation if the prepared source video changes
- Background frame-analysis jobs, polling, duplicate-job protection, and restart recovery

### Phase 2.2 — visual change detection

- Every consecutive frame pair is inspected (`N` frames must produce exactly `N-1` comparisons)
- Coverage fails closed if frames are missing, duplicated, reordered, or left uncompared
- Changes are classified conservatively as:
  - `NONE` — no meaningful visible change
  - `LOCAL` — localized movement or new content
  - `STRUCTURAL` — broader teaching-content modification
  - `SCENE` — large slide/board/screen transition
- Visual signatures use downscaled color and edge information
- Metrics include changed-pixel ratio, edge-change ratio, changed-region area, mean pixel delta, and composite change score
- Color-only changes are retained instead of relying only on grayscale comparison
- `LOCAL` changes are intentionally **not discarded**, because cursor movement, a hand, and a newly written character can look similar from one frame pair alone
- Persisted full visual-change map and summary

### Phase 2.3 — stable teaching-state detection

- Streams the persisted visual-change map instead of decoding the video a third time
- Groups continuous writing/drawing activity into temporal segments
- Default normal checkpoint requires approximately **1.25 seconds of visual stability**
- Does not create a screenshot candidate for every written character or pen stroke
- Protects a shorter completed pause before a strong transition using a conservative pre-transition checkpoint
- Preserves unfinished final content with an end-of-video fallback checkpoint
- Verifies the entire visual transition sequence remains contiguous and timestamp ordered
- Persists checkpoint references by frame index and timestamp; images are not extracted yet
- Checkpoint reasons include:
  - `INITIAL_STABLE`
  - `STABLE_AFTER_CHANGE`
  - `PRE_TRANSITION_PROTECTION`
  - `END_OF_VIDEO_FALLBACK`
  - `SINGLE_FRAME`
- Background state-detection jobs support progress polling, reuse, failure handling, and restart recovery

## Important behavior

Suppose a teacher writes continuously:

```text
m
mi
mid
mid =
mid = low
mid = low + ...
```

Notify does **not** treat each intermediate character as a screenshot. The visual changes remain pending while writing continues. Once the completed screen remains visually stable for the configured stability interval, Notify records a stable checkpoint referencing that frame.

If useful content is visible only briefly and a strong slide/board/replacement transition follows, Notify can preserve the previous frame through `PRE_TRANSITION_PROTECTION`. This is currently a conservative transition heuristic, not semantic understanding of erasing.

## Not implemented yet

The current stage finds **checkpoint references**. The following are still future work:

- exact screenshot image extraction for teaching checkpoints
- screenshot candidate quality selection
- SSIM/perceptual hashing and near-duplicate screenshot removal
- semantic distinction between cursor/hand motion and educational writing
- stronger erase/content-loss verification
- OCR
- Whisper/transcripts
- topic detection and screenshot-topic mapping
- semantic importance analysis
- final coverage verification
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
- NumPy
- FFmpeg / ffprobe (system tools)

## Repository layout

```text
notify/
├── frontend/               Next.js UI
├── backend/                FastAPI local processing service
├── downloads/              Verified videos + persistent analysis (ignored by Git)
├── temp/                   Temporary job workspaces (ignored by Git)
├── output/                 Future generated PDFs (ignored by Git)
├── .github/workflows/      Backend tests + frontend typecheck/build
├── .gitignore
└── README.md
```

## Runtime storage

A lecture that has completed Phase 2.3 is retained as:

```text
downloads/<video_id>/
├── lecture.mp4
├── metadata.json
└── analysis/
    ├── frame-timeline.jsonl
    ├── frame-timeline-summary.json
    ├── frame-differences.jsonl
    ├── frame-differences-summary.json
    ├── teaching-states.jsonl
    └── teaching-states-summary.json
```

`frame-timeline.jsonl` contains one compact record per decoded frame:

```json
{"frame_index":0,"timestamp_seconds":0.0}
{"frame_index":1,"timestamp_seconds":0.033333}
```

`frame-differences.jsonl` contains one record per consecutive frame pair and its visual metrics/classification.

`teaching-states.jsonl` contains only checkpoint references, for example conceptually:

```json
{"checkpoint_index":0,"frame_index":142,"timestamp_seconds":4.733333,"reason":"STABLE_AFTER_CHANGE","stability_seconds":1.266667,"protected_before_transition":false}
```

This architecture avoids creating thousands of image files during early analysis. The later screenshot-extraction stage will read only the referenced checkpoint frames.

Preparation and analysis jobs use isolated workspaces under `temp/<job_id>/`. Persistent analysis files are finalized only after their respective operation succeeds.

## Requirements

Install locally:

- Node.js 20+ recommended
- Python 3.11+ recommended
- FFmpeg with both `ffmpeg` and `ffprobe`

Python dependencies are installed through `backend/requirements.txt`.

### Windows FFmpeg

```powershell
winget install Gyan.FFmpeg
```

Open a new terminal afterwards and verify:

```powershell
ffmpeg -version
ffprobe -version
```

The backend can still start and fetch YouTube metadata if FFmpeg is unavailable; local media preparation requires it.

## Backend setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend URL: `http://localhost:8000`

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

Frontend URL: `http://localhost:3000`

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
Prepare + verify local lecture.mp4
        ↓
Start Frame Analysis
        ↓
Decode every frame sequentially
        ↓
Persist complete frame timeline
        ↓
Analyze Visual Changes
        ↓
Compare every consecutive frame pair
        ↓
Persist NONE / LOCAL / STRUCTURAL / SCENE map
        ↓
Detect Stable Teaching States
        ↓
Group continuous activity and wait for stable states
        ↓
Protect short completed states before strong transitions
        ↓
Persist ordered checkpoint references
        ↓
STABLE TEACHING STATES READY
```

Valid retained artifacts are reused instead of repeating unnecessary work. Dependency timestamps and source-file metadata are checked before cached analysis is accepted.

## Main API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Backend connectivity |
| POST | `/api/video/validate` | Validate and normalize a YouTube URL |
| POST | `/api/video/metadata` | Return normalized video metadata |
| POST | `/api/video/prepare` | Create/reuse local video preparation |
| GET | `/api/video/{video_id}/status` | Check local prepared-video state |
| DELETE | `/api/video/{video_id}/local` | Remove local video and analysis data |
| GET | `/api/jobs/{job_id}` | Poll preparation job |
| POST | `/api/analysis/start` | Start/reuse frame-timeline analysis |
| GET | `/api/analysis/jobs/{job_id}` | Poll frame-timeline job |
| GET | `/api/analysis/{video_id}/timeline` | Read frame-timeline summary |
| POST | `/api/analysis/changes/start` | Start/reuse visual-change analysis |
| GET | `/api/analysis/changes/jobs/{job_id}` | Poll visual-change job |
| GET | `/api/analysis/{video_id}/changes` | Read visual-change summary |
| POST | `/api/analysis/states/start` | Start/reuse stable teaching-state detection |
| GET | `/api/analysis/states/jobs/{job_id}` | Poll teaching-state job |
| GET | `/api/analysis/{video_id}/states` | Read teaching-state summary |
| GET | `/api/storage/status` | Local storage usage |
| POST | `/api/storage/cleanup` | Remove stale temporary data |
| GET | `/api/system/status` | FFmpeg/filesystem capability check |

## Processing states and job types

Relevant transient states include:

```text
QUEUED
DOWNLOADING
MERGING
VERIFYING
FINALIZING
SCANNING_FRAMES
COMPARING_FRAMES
DETECTING_STATES
```

Terminal states:

```text
READY
FAILED
INTERRUPTED
CANCELLED
```

Job types:

```text
PREPARATION
FRAME_TIMELINE
VISUAL_CHANGE
TEACHING_STATE
```

## Verification

GitHub Actions runs:

- backend automated tests with Python 3.12 and FFmpeg
- frontend TypeScript typecheck
- Next.js production build

Phase 2.3 tests specifically cover continuous writing collapsing into a stable checkpoint, protection before a strong transition, end-of-video fallback, persisted checkpoint ordering/reuse, and full visual-transition coverage.

## Next milestone

**Phase 2.4 — Screenshot Candidate Extraction and Near-Duplicate Filtering**

The next stage will resolve the stored teaching-state frame references back to exact images, preserve protected candidates, compare candidate screenshots for near-duplicates, and prepare a compact ordered screenshot set without silently dropping uncertain educational content.
