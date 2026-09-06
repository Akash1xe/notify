# Notify — Lecture to PDF

Notify is a local-first lecture processing application. It accepts a YouTube lecture URL, prepares and verifies a local processing copy, analyzes every decoded frame transition, detects stable teaching-state checkpoints, extracts the referenced images, and conservatively removes only clear near-duplicate screenshot candidates.

> Current milestone: **Phase 2.4 complete — screenshot candidate extraction + conservative near-duplicate filtering**.

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
- Changes are classified conservatively as `NONE`, `LOCAL`, `STRUCTURAL`, or `SCENE`
- Visual signatures use downscaled color and edge information
- Metrics include changed-pixel ratio, edge-change ratio, changed-region area, mean pixel delta, and composite change score
- Color-only changes are retained instead of relying only on grayscale comparison
- `LOCAL` changes are intentionally not discarded because cursor/hand movement and newly written characters can look similar from one frame pair alone
- Persisted full visual-change map and summary

### Phase 2.3 — stable teaching-state detection

- Streams the persisted visual-change map instead of decoding the video again
- Groups continuous writing/drawing activity into temporal segments
- Default normal checkpoint requires approximately **1.25 seconds of visual stability**
- Does not create a screenshot candidate for every written character or pen stroke
- Protects a shorter completed pause before a strong transition using a conservative pre-transition checkpoint
- Preserves unfinished final content with an end-of-video fallback checkpoint
- Verifies the entire visual transition sequence remains contiguous and timestamp ordered
- Persists checkpoint references by frame index and timestamp
- Checkpoint reasons include `INITIAL_STABLE`, `STABLE_AFTER_CHANGE`, `PRE_TRANSITION_PROTECTION`, `END_OF_VIDEO_FALLBACK`, and `SINGLE_FRAME`
- Background state-detection jobs support progress polling, reuse, failure handling, and restart recovery

### Phase 2.4 — screenshot candidate extraction + near-duplicate filtering

- Reads the ordered teaching-state checkpoint file and validates checkpoint indexes, frame order, timestamps, and count
- Sequentially decodes the prepared lecture once and extracts only referenced checkpoint frames
- Saves retained screenshots as high-quality JPEG files (default quality 92)
- Produces a manifest entry for **every** checkpoint, including duplicate-suppressed checkpoints
- Uses two independent signals before calling an unprotected screenshot a near-duplicate:
  - difference-hash (dHash) Hamming distance
  - mean absolute grayscale thumbnail difference
- Compares against a small recent window instead of the entire lecture, reducing over-aggressive matching across distant sections
- Keeps filtering intentionally conservative so newly written lines or diagrams are not removed just because most of the board is unchanged
- Never automatically removes protected checkpoints such as pre-transition preservation, end-of-video fallback, or single-frame fallback
- Persists source/dependency timestamps and prepared-video file metadata for cache invalidation
- Background extraction jobs support polling, reuse, failure handling, duplicate active-job protection, and restart recovery
- Frontend shows checkpoints considered, screenshots retained, near-duplicates removed, and protected screenshots retained

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

Notify first waits for a stable teaching state instead of taking a screenshot at every character. Phase 2.4 then resolves that stable checkpoint to the exact video frame and saves the image.

If two checkpoint images are effectively the same, Notify can suppress the later unprotected one. A match must satisfy both the configured perceptual-hash threshold and a very small pixel-distance threshold. This intentionally favors **keeping uncertain educational content** over aggressive storage reduction.

If a checkpoint was preserved because content was about to disappear, it is always retained even if it resembles another screenshot.

## Not implemented yet

The pipeline now has real screenshot files and an auditable candidate manifest. Future work still includes:

- candidate preview/review UI with manual restore/remove controls
- stronger erase/content-loss verification across retained and suppressed candidates
- wider duplicate analysis using SSIM/semantic information where useful
- screenshot quality/ranking when several nearby frames are possible
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

A lecture that has completed Phase 2.4 is retained as:

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
    ├── teaching-states-summary.json
    ├── screenshot-candidates.jsonl
    ├── screenshot-candidates-summary.json
    └── screenshots/
        ├── candidate-000000.jpg
        ├── candidate-000002.jpg
        └── ...
```

Image indexes may contain gaps because `screenshot-candidates.jsonl` records every original checkpoint while only retained candidates receive image files.

A candidate manifest entry is conceptually:

```json
{
  "candidate_index": 4,
  "checkpoint_index": 4,
  "frame_index": 812,
  "timestamp_seconds": 27.066667,
  "reason": "STABLE_AFTER_CHANGE",
  "protected": false,
  "kept": false,
  "image_filename": null,
  "duplicate_of_candidate_index": 3,
  "duplicate_hash_distance": 1,
  "duplicate_mean_abs_difference": 0.82
}
```

Because rejected candidates remain in the manifest, later coverage/review logic can reason about or restore them instead of losing their provenance.

Preparation and analysis jobs use isolated workspaces under `temp/<job_id>/`. Persistent summaries are accepted only when their source video and upstream analysis dependency metadata still match.

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

## Backend setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend URL: `http://localhost:8000`

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
Build complete frame timeline
        ↓
Compare every consecutive frame pair
        ↓
Persist visual-change map
        ↓
Detect stable teaching states
        ↓
Protect short completed states before strong transitions
        ↓
Persist ordered checkpoint references
        ↓
Extract Screenshot Candidates
        ↓
Decode lecture sequentially and save referenced frames
        ↓
Conservatively suppress clear unprotected near-duplicates
        ↓
Persist complete candidate manifest + retained JPEGs
        ↓
SCREENSHOT CANDIDATES READY
```

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
| POST | `/api/analysis/candidates/start` | Start/reuse screenshot candidate extraction |
| GET | `/api/analysis/candidates/jobs/{job_id}` | Poll screenshot candidate job |
| GET | `/api/analysis/{video_id}/candidates` | Read screenshot candidate summary |
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
EXTRACTING_SCREENSHOTS
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
SCREENSHOT_CANDIDATE
```

## Verification

GitHub Actions runs:

- backend automated tests with Python 3.12 and FFmpeg
- frontend TypeScript typecheck
- Next.js production build

Phase 2.4 adds tests for exact duplicate matching, small visual/encoding noise, preserving meaningful new written content, and finding a repeated recent slide without relying on hash similarity alone.

## Next milestone

**Phase 2.5 — Candidate Review + Content Protection Hardening**

The next stage should expose the retained/suppressed candidate set for review, strengthen before/after transition protection, allow safe restoration of suppressed frames, and prepare a trusted ordered screenshot set for the later topic/coverage/PDF stages.
