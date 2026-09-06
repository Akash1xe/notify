# Notify — Lecture to PDF

Notify is a local-first lecture processing application. It accepts a YouTube lecture URL, prepares and verifies a local copy, analyzes visual changes, detects stable teaching states, builds a protected trusted screenshot set, and now generates a timestamped local transcript aligned to those trusted screenshots.

> Current milestone: **Phase 3.1 complete — local transcript generation + trusted screenshot alignment**.

## Current capabilities

### Phase 1 — local lecture preparation

- YouTube URL input and validation
- yt-dlp metadata/accessibility inspection
- Metadata preview (title, channel, duration, thumbnail, resolution)
- Local 720p-first download/preparation
- FFmpeg/ffprobe verification
- Background preparation jobs and progress polling
- Restart-safe prepared-video reuse
- Interrupted-job recovery, stale-temp cleanup, storage status, and local-copy deletion

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

- Adds visual-detail metrics (`edge_density`, `contrast_std`)
- Detects content-loss risk before scene replacement / major detail loss
- Builds a separate ordered **trusted screenshot set**
- Keeps original candidate evidence non-destructive and auditable
- Allows manual restore of suppressed duplicates
- Allows manual suppression of ordinary retained candidates
- Prevents accidental suppression of auto-protected candidates
- Rebuilds the trusted set atomically after review decisions

### Phase 3.1 — local transcript + screenshot alignment

- Uses **faster-whisper** locally; no custom model training is required
- Extracts a standard mono 16 kHz WAV with FFmpeg
- Default model: `small.en`
- Default CPU compute mode: `int8`
- Generates ordered timestamped transcript segments
- Persists transcript independently from screenshot review state
- Aligns every trusted screenshot to nearby teacher speech
- Default alignment context:
  - 6 seconds before screenshot timestamp
  - 8 seconds after screenshot timestamp
- Keeps silent screenshots even when no speech is nearby
- Changing screenshot review decisions invalidates only screenshot/transcript alignment, not the expensive Whisper transcript
- Background transcript jobs support progress polling, duplicate-job prevention, failure reporting, and restart recovery
- The first local run may download the configured pretrained Whisper model

## Why transcript and alignment are separate

The raw transcript depends on the prepared lecture audio, while screenshot alignment depends on the current trusted screenshot set.

```text
lecture.mp4
    ↓
16 kHz mono audio
    ↓
faster-whisper
    ↓
timestamped transcript (cached)
    ↓
trusted screenshot timestamps
    ↓
screenshot ↔ nearby speech alignment
```

If you restore or suppress screenshots later:

```text
Trusted set changes
      ↓
Keep existing Whisper transcript
      ↓
Rebuild only screenshot alignment
```

This avoids repeating the expensive transcription stage.

## Content-safety philosophy

When uncertain, Notify favors **keeping educational content** over aggressive deduplication.

A screenshot is not considered unimportant simply because the teacher is silent near that frame. Visual equations, completed diagrams, code, or board content can remain in the trusted set without transcript text.

## Runtime storage

A lecture that reaches Phase 3.1 can contain:

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
    │   └── candidate-*.jpg
    ├── candidate-review.json
    ├── trusted-screenshots.jsonl
    ├── trusted-screenshots-summary.json
    ├── trusted-screenshots/
    │   └── trusted-*.jpg
    ├── transcript-audio.wav
    ├── transcript-segments.jsonl
    ├── transcript-summary.json
    ├── screenshot-transcript-map.jsonl
    └── screenshot-transcript-map-summary.json
```

### Transcript segment record

`transcript-segments.jsonl` contains ordered records such as:

```json
{
  "segment_index": 18,
  "start_seconds": 72.14,
  "end_seconds": 78.42,
  "text": "Now we calculate the middle index using low and high."
}
```

### Screenshot alignment record

`screenshot-transcript-map.jsonl` contains records such as:

```json
{
  "trusted_index": 7,
  "candidate_index": 9,
  "frame_index": 2310,
  "timestamp_seconds": 77.0,
  "context_start_seconds": 71.0,
  "context_end_seconds": 85.0,
  "segment_indexes": [17, 18, 19],
  "text": "Now we calculate the middle index using low and high..."
}
```

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
- faster-whisper / CTranslate2
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

### Whisper configuration

Defaults are chosen for an English lecture on a normal CPU:

```text
WHISPER_MODEL=small.en
WHISPER_LANGUAGE=en
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

They are optional environment variables. For another language, use a multilingual model such as `small` and change `WHISPER_LANGUAGE` accordingly.

The first transcription run may need internet access once to download the selected pretrained model. After it is cached locally, transcription can reuse it.

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
Build ordered trusted screenshot set
    ↓
Extract 16 kHz mono audio
    ↓
Generate timestamped faster-whisper transcript
    ↓
Align teacher speech to trusted screenshots
    ↓
TRANSCRIPT + SCREENSHOT CONTEXT READY
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
| POST | `/api/analysis/transcript/start` | Start/reuse local transcription + alignment |
| GET | `/api/analysis/transcript/jobs/{job_id}` | Poll transcript job |
| GET | `/api/analysis/{video_id}/transcript` | Read transcript/alignment summaries |
| GET | `/api/storage/status` | Local storage usage |
| POST | `/api/storage/cleanup` | Clean stale temporary data |

## Verification

GitHub Actions runs:

- backend automated tests on Python 3.12 with FFmpeg
- frontend TypeScript typecheck
- Next.js production build

Phase 3.1 adds deterministic tests with a fake Whisper model so CI never downloads model weights. Tests verify:

- timestamped transcript persistence
- trusted screenshot ↔ nearby speech alignment
- transcript cache validation against the source lecture
- review changes trigger realignment without rerunning Whisper or audio extraction

## Not implemented yet

- semantic topic/section detection
- OCR / screenshot text extraction
- topic ↔ screenshot grouping
- semantic importance ranking
- full coverage verification pass
- PDF generation

## Next milestone

**Phase 3.2 — Lecture Topic / Section Detection**

The next stage will use the timestamped transcript plus trusted screenshot timing to identify coherent lecture sections, assign screenshots to those sections, and produce ordered topic groups without changing the original transcript or trusted screenshot evidence.
