# Notify — Lecture to PDF

Notify is a local-first lecture processing application. It accepts a YouTube lecture URL, prepares and verifies a local copy, analyzes visual changes, detects stable teaching states, extracts screenshot candidates, and now builds a reviewable protected screenshot set before later transcript/topic/PDF stages.

> Current milestone: **Phase 2.5 complete — candidate review + content protection hardening**.

## Current capabilities

### Phase 1 — local lecture preparation

- YouTube URL input and validation
- yt-dlp metadata/accessibility inspection
- Metadata preview (title, channel, duration, thumbnail, resolution)
- Local 720p-first download/preparation
- FFmpeg/ffprobe verification
- Background preparation jobs and progress polling
- Restart-safe prepared-video reuse
- interrupted-job recovery, stale-temp cleanup, storage status, and local-copy deletion

### Phase 2.1 — frame timeline

- OpenCV sequential decoding
- One frame at a time in memory
- Frame indexes + monotonic timestamps
- Persisted complete frame timeline
- Cache invalidation when the source video changes

### Phase 2.2 — visual change detection

- Inspects every consecutive frame pair (`N` frames => exactly `N-1` comparisons)
- Fails closed on gaps/reordering/incomplete coverage
- Conservative `NONE`, `LOCAL`, `STRUCTURAL`, `SCENE` classification
- Uses color, edge, changed-region, and pixel-difference information
- Does not discard `LOCAL` changes prematurely

### Phase 2.3 — stable teaching-state detection

- Groups continuous writing/drawing activity temporally
- Normal checkpoint after about 1.25 seconds of visual stability
- Avoids one screenshot per written character or pen stroke
- Preserves short completed pauses before strong transitions
- Preserves unfinished final content at end-of-video
- Persists ordered checkpoint references

### Phase 2.4 — screenshot candidate extraction

- Resolves teaching checkpoints to exact video frames
- Saves retained candidates as JPEG (quality 92)
- Persists a manifest entry for every checkpoint, including suppressed duplicates
- Near-duplicate removal requires both close dHash distance and very small thumbnail pixel difference
- Never automatically removes transition/end/single-frame protected checkpoints
- Uses only a small recent comparison window to avoid distant-section overmatching

### Phase 2.5 — candidate review + content protection hardening

- Adds visual-detail metrics to every candidate (`edge_density`, `contrast_std`)
- Marks a completed candidate as `content_loss_risk` when:
  - the following stable state comes from a `SCENE` replacement, or
  - visual detail drops sharply afterwards
- Candidate pipeline versioning invalidates older Phase 2.4 manifests so the new safety metadata is regenerated
- Builds a separate, ordered **trusted screenshot set** without modifying or deleting the original candidate evidence
- Default trusted selection keeps:
  - normal dedup-retained screenshots
  - transition-protected screenshots
  - end-of-video/single-frame protected screenshots
  - content-loss-risk screenshots, even when they were previously dedup-suppressed
- Suppressed candidates remain previewable by restoring the exact original frame from `lecture.mp4` on demand
- User can manually restore a suppressed candidate
- User can manually suppress an ordinary retained candidate
- Auto-protected candidates cannot be suppressed accidentally through the normal review action
- Manual review decisions are persisted separately and the trusted image directory is rebuilt atomically
- Review UI is paginated so long lectures do not load every candidate preview at once

## Content-safety philosophy

When uncertain, Notify favors **keeping educational content** over aggressive deduplication.

Example:

```text
Teacher finishes equation
        ↓
Screen is stable
        ↓
Candidate A
        ↓
Teacher changes slide / erases board
        ↓
Candidate B has much less detail or starts after SCENE
        ↓
Candidate A receives content-loss protection
        ↓
Candidate A remains in trusted set
```

A screenshot previously suppressed as a near-duplicate can therefore be restored automatically if later analysis shows that content may disappear after it.

## Runtime storage

A lecture that reaches Phase 2.5 can contain:

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
    ├── screenshots/
    │   ├── candidate-000000.jpg
    │   └── ...
    ├── candidate-review.json
    ├── trusted-screenshots.jsonl
    ├── trusted-screenshots-summary.json
    └── trusted-screenshots/
        ├── trusted-000000.jpg
        └── ...
```

### Original candidate manifest

`screenshot-candidates.jsonl` remains the immutable analysis evidence for review. A record now includes information such as:

```json
{
  "candidate_index": 4,
  "frame_index": 812,
  "timestamp_seconds": 27.066667,
  "reason": "STABLE_AFTER_CHANGE",
  "source_change_kind": "SCENE",
  "protected": false,
  "kept": false,
  "duplicate_of_candidate_index": 3,
  "edge_density": 0.0342,
  "contrast_std": 0.182,
  "content_loss_risk": true,
  "content_loss_reason": "SCENE_REPLACEMENT"
}
```

### Review state

`candidate-review.json` stores only user review decisions plus the exact candidate-generation version they apply to. If screenshot candidates are regenerated, stale review decisions are not applied to unrelated/new candidates.

### Trusted set

`trusted-screenshots.jsonl` and `trusted-screenshots/` contain the actual ordered image set that future transcript/topic/PDF stages should consume.

The original candidate files and manifest are not destroyed when the trusted set changes.

## Stack

### Frontend
- Next.js App Router
- TypeScript
- Tailwind CSS

### Backend
- Python
- FastAPI
- Uvicorn
- yt-dlp
- OpenCV (`opencv-python-headless`)
- NumPy
- FFmpeg / ffprobe

## Requirements

Recommended locally:

- Node.js 20+
- Python 3.11+
- FFmpeg with `ffmpeg` and `ffprobe`

### Windows FFmpeg

```powershell
winget install Gyan.FFmpeg
```

Then verify:

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

Backend: `http://localhost:8000`

## Frontend setup

```powershell
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

Frontend: `http://localhost:3000`

Default frontend env:

```text
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Current user flow

```text
YouTube URL
    ↓
Validate + metadata
    ↓
Prepare verified lecture.mp4
    ↓
Build frame timeline
    ↓
Analyze every consecutive visual transition
    ↓
Detect stable teaching states
    ↓
Extract screenshot candidates
    ↓
Conservative near-duplicate filtering
    ↓
Detect content-loss risk
    ↓
Review retained + suppressed candidates
    ↓
Restore/suppress ordinary candidates manually
    ↓
Protect risky candidates
    ↓
Build ordered trusted-screenshots set
```

## Main API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Backend connectivity |
| POST | `/api/video/metadata` | Validate and return video metadata |
| POST | `/api/video/prepare` | Prepare/reuse local lecture |
| GET | `/api/jobs/{job_id}` | Poll preparation |
| POST | `/api/analysis/start` | Build/reuse frame timeline |
| GET | `/api/analysis/{video_id}/timeline` | Timeline summary |
| POST | `/api/analysis/changes/start` | Analyze visual changes |
| GET | `/api/analysis/{video_id}/changes` | Visual-change summary |
| POST | `/api/analysis/states/start` | Detect stable teaching states |
| GET | `/api/analysis/{video_id}/states` | Teaching-state summary |
| POST | `/api/analysis/candidates/start` | Extract screenshot candidates |
| GET | `/api/analysis/{video_id}/candidates` | Candidate summary |
| GET | `/api/analysis/{video_id}/candidate-review` | Initialize/read review + trusted set |
| PUT | `/api/analysis/{video_id}/candidate-review/{candidate_index}` | Keep/restore/suppress a candidate |
| GET | `/api/analysis/{video_id}/candidates/{candidate_index}/image` | Preview retained or suppressed candidate |
| GET | `/api/storage/status` | Local storage usage |
| POST | `/api/storage/cleanup` | Clean stale temporary data |

## Verification

GitHub Actions runs:

- backend automated tests on Python 3.12 with FFmpeg
- frontend TypeScript typecheck
- Next.js production build

Phase 2.5 tests cover:

- scene-replacement protection
- sharp visual-detail-drop protection
- default restoration of a risk-protected dedup-suppressed candidate
- manual restore of a normal suppressed candidate
- manual suppression of an ordinary retained candidate
- rejection of accidental suppression for an auto-protected candidate
- trusted screenshot directory regeneration

## Not implemented yet

- Whisper/transcript generation
- topic segmentation
- screenshot ↔ transcript/topic alignment
- OCR/semantic importance analysis
- full coverage verification pass
- PDF generation

## Next milestone

**Phase 3 — Transcript + Topic Detection foundation**

The next stage should extract audio locally, generate timestamped transcript segments with a pretrained Whisper/faster-whisper model, and prepare topic boundaries that can later be aligned to the trusted screenshot set. No custom model training is required.
