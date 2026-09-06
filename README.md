# Notify — Lecture to PDF

Notify is a local-first application that turns a YouTube lecture into a coverage-verified PDF of useful teaching screenshots. The pipeline prepares the lecture locally, analyzes every frame transition, waits for stable teaching states, protects content before it disappears, builds a reviewed screenshot set, enriches it with transcript/topic/OCR context, audits for possible missed teaching content, and finally generates a downloadable PDF.

> **Project status: Phase 1–6 complete. The end-to-end local lecture-to-PDF workflow is implemented.**

## Complete pipeline

```text
YouTube URL
    ↓
Validate URL + read metadata
    ↓
Download / verify lecture.mp4 locally
    ↓
Build complete frame timeline
    ↓
Compare every consecutive frame pair
    ↓
Detect stable teaching states
    ↓
Protect content before erase / strong transition
    ↓
Extract screenshot candidates
    ↓
Conservative near-duplicate filtering
    ↓
Manual candidate review
    ↓
Trusted screenshot set
    ↓
Local faster-whisper transcript
    ↓
Screenshot ↔ nearby speech alignment
    ↓
Lecture topic / section detection
    ↓
Local Tesseract OCR
    ↓
Visible text + speech + topic enrichment
    ↓
Fail-closed coverage verification
    ↓
Final PDF review / ordering
    ↓
Coverage-verified PDF preview + download
```

## Core safety rules

Notify is intentionally conservative about educational content.

```text
Writing still changing       → wait
Stable meaningful state      → candidate
Teacher pauses mid-solution  → candidate
Important state before erase → protected candidate
Near-identical image         → suppress conservatively
OCR cannot read handwriting  → keep screenshot
Coverage finds unresolved gap→ block PDF
```

A final PDF cannot bypass the trusted screenshot and coverage stages. Final PDF review may reorder pages, but it must contain **every trusted screenshot exactly once**. To remove or restore a screenshot, change it in candidate review; that changes the trusted set and causes dependent transcript/topic/OCR/coverage results to become stale and require regeneration.

## Completed phases

### Phase 1 — Local application and video preparation

- Next.js + TypeScript + Tailwind frontend
- FastAPI local backend
- YouTube URL parsing, normalization and backend validation
- yt-dlp metadata/accessibility inspection
- Metadata preview
- 720p-first local video preparation
- FFmpeg/ffprobe verification
- Background jobs and frontend polling
- deterministic local storage
- prepared-video reuse
- stale temporary-workspace cleanup and restart recovery

### Phase 2 — Visual teaching-state extraction

#### 2.1 Frame timeline

- Sequential OpenCV decoding
- One frame at a time in memory
- Ordered frame indexes and timestamps
- Complete persisted timeline

#### 2.2 Visual change detection

- Compares every consecutive frame pair
- Requires `N` frames to produce exactly `N - 1` comparisons
- Classifies `NONE`, `LOCAL`, `STRUCTURAL`, and `SCENE` changes
- Uses LAB color differences, changed-pixel area and edge changes
- Does not prematurely discard local writing/annotation changes

#### 2.3 Stable teaching states

- Groups continuous writing/drawing activity
- Waits for stability before normal checkpoint capture
- Avoids capturing one image per written character
- Preserves meaningful intermediate pauses
- Protects content before strong transitions/erase events
- End-of-video fallback preserves unfinished final content

#### 2.4 Screenshot extraction and duplicate filtering

- Resolves checkpoints to exact lecture frames
- Saves high-quality screenshot candidates
- Persists evidence even for duplicate-suppressed candidates
- Near-duplicate suppression requires multiple visual signals
- Protected checkpoints are never automatically removed

#### 2.5 Candidate review and trusted set

- Detects content-loss risk
- Builds a separate ordered trusted screenshot set
- Supports manual keep/restore/suppress decisions
- Protected screenshots require explicit override before suppression
- Original candidate evidence remains non-destructive

### Phase 3 — Transcript and lecture structure

#### 3.1 Local transcript + screenshot alignment

- faster-whisper runs locally
- FFmpeg extracts mono 16 kHz WAV
- default model: `small.en`
- default CPU compute type: `int8`
- timestamped transcript segments
- each trusted screenshot receives nearby speech context
- default context window: about 6 seconds before / 8 seconds after
- silent screenshots remain valid educational evidence
- trusted-set changes rebuild alignment without unnecessarily rerunning an unchanged raw transcript

#### 3.2 Lecture topic detection

Deterministic local section detection combines:

- speech gaps
- vocabulary shifts
- transition phrases such as `next`, `moving on`, and `finally`
- strong visual transition evidence

Every trusted screenshot must belong to exactly one section. Visual-only sections are supported when speech is sparse.

### Phase 4 — OCR and screenshot content enrichment

Local Tesseract OCR extracts:

- visible text
- line records
- bounding boxes
- word/line counts
- confidence
- no-text / low-confidence flags

Preprocessing includes grayscale conversion, dark-screen inversion when useful, upscaling of smaller images, and CLAHE local contrast enhancement.

Default settings:

```text
OCR_LANGUAGE=eng
OCR_PSM=11
```

OCR is evidence, not authority:

```text
OCR_NO_TEXT
OCR_LOW_CONFIDENCE
```

are uncertainty signals only. Handwriting, equations, diagrams, roots, fractions, integrals, arrows, code formatting and low-contrast board writing remain preserved even when OCR is weak.

### Phase 5 — Coverage verification / missed-content detection

Coverage verification is a fail-closed safety gate over the evidence created by the earlier phases.

It checks:

- strong scene/structural changes without a nearby trusted screenshot
- stable teaching states absent from the trusted set
- protected/content-loss candidates missing from the trusted set
- long trusted-screenshot gaps with speech or visual activity
- speech-dense gaps
- unused stable states inside gaps
- lecture topics without a trusted screenshot
- OCR uncertainty

Blocking findings include signals such as:

```text
UNCAPTURED_STRONG_VISUAL_CHANGE
STABLE_STATE_NOT_IN_TRUSTED_SET
PROTECTED_EVIDENCE_NOT_TRUSTED
LONG_TRUSTED_SCREENSHOT_GAP
SPEECH_DENSE_GAP
UNUSED_STABLE_STATE_IN_GAP
TOPIC_WITHOUT_TRUSTED_SCREENSHOT
```

OCR uncertainty remains non-blocking.

The PDF gate is:

```text
blocking_finding_count == 0
        ↓
ready_for_pdf = true
```

Any current upstream evidence change invalidates an old coverage approval.

### Phase 6 — Final PDF generator and review UI

The final stage uses **ReportLab** locally to generate a real PDF only from a current coverage-approved trusted set.

Features:

- final page-order review
- safe Up / Down reordering controls
- reset to topic/timestamp order
- every trusted screenshot required exactly once
- optional cover page
- optional lecture-topic divider pages
- optional OCR + nearby-speech context captions
- configurable screenshot JPEG quality
- landscape A4 screenshot pages with aspect-ratio preservation
- background PDF generation with progress polling
- atomic PDF finalization
- `%PDF-` output validation
- inline browser PDF preview
- download endpoint
- stale PDF invalidation when trusted set, topics, coverage result, final ordering, or generation settings change
- PDF-specific interrupted-job recovery messaging

Default PDF settings:

```text
image_quality=92
include_cover=true
include_topic_dividers=true
include_context=false
```

Quality presets in the UI include standard, high/recommended, and original JPEG quality.

## Runtime artifacts

A fully processed lecture can contain:

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
    ├── screenshot-transcript-map-summary.json
    ├── lecture-topics.jsonl
    ├── lecture-topics-summary.json
    ├── screenshot-ocr.jsonl
    ├── screenshot-ocr-summary.json
    ├── screenshot-content.jsonl
    ├── screenshot-content-summary.json
    ├── topic-content.jsonl
    ├── coverage-findings.jsonl
    ├── coverage-summary.json
    └── pdf-review.json

output/<video_id>/
├── lecture-notes.pdf
└── pdf-manifest.json
```

Generated/downloaded runtime media is excluded from Git; only placeholder files keep runtime directories present in the repository.

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
- OpenCV + NumPy
- FFmpeg / ffprobe
- faster-whisper / CTranslate2
- Tesseract OCR
- ReportLab

No database, Redis, message broker, cloud OCR, hosted LLM, or custom-trained ML model is required for the current local application.

## Local requirements

Recommended:

- Node.js 20+
- Python 3.11+
- FFmpeg with `ffmpeg` and `ffprobe`
- Tesseract OCR 5+

Verify system tools:

```powershell
ffmpeg -version
ffprobe -version
tesseract --version
```

On Windows, make `tesseract.exe` available on `PATH` or configure `TESSERACT_CMD` with the executable path.

## Backend setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend:

```text
http://localhost:8000
```

Optional backend configuration:

```text
FRONTEND_ORIGIN=http://localhost:3000
MAX_VIDEO_HEIGHT=720
TEMP_RETENTION_HOURS=24
MIN_FREE_SPACE_BYTES=536870912

WHISPER_MODEL=small.en
WHISPER_LANGUAGE=en
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8

OCR_LANGUAGE=eng
OCR_PSM=11
TESSERACT_CMD=<optional full path to tesseract executable>
```

The first real transcription may download the configured faster-whisper pretrained model. No model training is performed.

## Frontend setup

```powershell
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

Frontend:

```text
http://localhost:3000
```

Default frontend environment:

```text
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Main API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Backend connectivity |
| GET | `/api/system/status` | Local tool/storage capability status |
| POST | `/api/video/validate` | Validate YouTube URL |
| POST | `/api/video/metadata` | Read lecture metadata |
| POST | `/api/video/prepare` | Prepare/reuse local lecture |
| GET | `/api/jobs/{job_id}` | Poll video preparation |
| POST | `/api/analysis/start` | Build/reuse frame timeline |
| POST | `/api/analysis/changes/start` | Analyze visual changes |
| POST | `/api/analysis/states/start` | Detect stable teaching states |
| POST | `/api/analysis/candidates/start` | Extract screenshot candidates |
| GET | `/api/analysis/{video_id}/candidate-review` | Read candidate/trusted state |
| PUT | `/api/analysis/{video_id}/candidate-review/{candidate_index}` | Keep/restore/suppress candidate |
| POST | `/api/analysis/transcript/start` | Generate transcript + alignment |
| POST | `/api/analysis/topics/start` | Detect lecture sections |
| POST | `/api/analysis/ocr/start` | OCR/enrich trusted screenshots |
| POST | `/api/analysis/coverage/start` | Run fail-closed coverage audit |
| GET | `/api/analysis/{video_id}/coverage` | Read current coverage result |
| GET | `/api/pdf/{video_id}/review` | Read final coverage-approved PDF order |
| PUT | `/api/pdf/{video_id}/review` | Save a full trusted-screenshot order |
| POST | `/api/pdf/start` | Generate/reuse final PDF |
| GET | `/api/pdf/jobs/{job_id}` | Poll PDF generation |
| GET | `/api/pdf/{video_id}` | Read current PDF manifest |
| GET | `/api/pdf/{video_id}/preview` | Preview PDF inline |
| GET | `/api/pdf/{video_id}/download` | Download generated PDF |
| GET | `/api/storage/status` | Local storage usage |
| POST | `/api/storage/cleanup` | Remove stale temporary workspaces |

The analysis API also exposes result/job endpoints for each intermediate stage.

## Verification and CI

GitHub Actions validates the repository with:

- Python 3.12 backend test suite
- FFmpeg installation
- Tesseract installation and version check
- deterministic OCR tests
- real Tesseract subprocess smoke test
- coverage fail-closed tests
- real ReportLab PDF generation tests using generated screenshot images
- PDF `%PDF-` validation
- PDF review completeness/invalidation tests
- PDF interrupted-job recovery test
- frontend TypeScript typecheck
- Next.js production build

The tests intentionally avoid downloading Whisper model weights in CI; transcription behavior is tested with deterministic substitutes while a normal local run uses faster-whisper.

## Current end-to-end user flow

```text
Paste YouTube URL
      ↓
Analyze metadata
      ↓
Prepare lecture
      ↓
Build frame timeline
      ↓
Visual change analysis
      ↓
Stable teaching-state detection
      ↓
Screenshot extraction
      ↓
Candidate review / trusted set
      ↓
Transcript generation
      ↓
Lecture topic detection
      ↓
OCR enrichment
      ↓
Coverage verification
      ↓
PDF gate passes
      ↓
Final page review / ordering
      ↓
Generate Final PDF
      ↓
Preview + Download
```

## Limitations and optional future improvements

The required Phase 1–6 pipeline is complete, but real-world lecture formats vary. Useful future improvements include:

- stronger handwriting/math-specific OCR
- richer semantic importance ranking
- more advanced recovery suggestions for coverage-blocked windows
- drag-and-drop final page ordering
- searchable text layer/bookmarks inside the PDF
- broader multilingual presets
- profiling/tuning on long lectures and different teaching styles

No algorithm can guarantee that every arbitrary lecture will have zero missed educational content. Notify therefore uses conservative extraction, explicit review, evidence preservation and fail-closed coverage verification rather than claiming an absolute guarantee.
