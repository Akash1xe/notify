# Notify — Lecture to PDF

Notify is a local-first application that turns a YouTube lecture into organized visual notes and a coverage-checked PDF. It preserves stable teaching states, protects content before erase/slide transitions, enriches screenshots with transcript/topic/OCR context, and generates the final PDF locally.

> **Current status: core lecture-to-PDF workflow complete, with adaptive visual processing for practical long-lecture performance.**

## Pipeline

```text
YouTube URL
    ↓
Validate + download/verify lecture.mp4
    ↓
Read source timing metadata (no full-frame timeline decode)
    ↓
Adaptive visual analysis
    ├─ coarse whole-video scan (default 4 FPS, small frames)
    ├─ identify/pad/merge activity windows
    └─ fine scan only in activity windows (default 12 FPS)
    ↓
Stable teaching-state detection
    ↓
Pre-transition / erase protection
    ↓
Direct full-resolution checkpoint extraction
    ↓
Conservative near-duplicate filtering
    ↓
Candidate review → trusted screenshots
    ↓
Raw faster-whisper transcript (can prewarm during visual scan)
    ↓
Screenshot ↔ speech alignment
    ↓
Topic detection
    ↓
Local Tesseract OCR
    ↓
Evidence-aware coverage verification
    ↓
Final PDF review, preview and download
```

## Why the visual pipeline is adaptive

The original implementation decoded the complete source frame timeline and then compared every consecutive frame pair. A one-hour lecture can contain well over 100,000 source frames, even though most lecture time is visually static.

Notify now avoids redundant work without blindly taking screenshots at fixed time intervals.

```text
Static lecture region
    ↓
coarse samples only

Potential writing / scrolling / slide change
    ↓
open padded activity window
    ↓
fine temporal scan
    ↓
wait for stable state
    ↓
extract original-resolution checkpoint
```

The coarse pass is only a detector for where higher precision is required. Final screenshots are always extracted from the prepared source video, not from low-resolution detection frames.

### Content-preservation safeguards

Performance optimizations must not silently discard teaching content:

- persistent local changes such as writing can open fine-analysis windows
- a stable-anchor comparison detects cumulative writing even when each individual edit is small
- activity windows are padded before and after detected activity
- nearby windows are merged to avoid gaps during continuous teaching
- synthetic quiet-gap evidence preserves stable states between separated activity windows
- strong scene/structural transitions remain visible to the teaching-state detector
- meaningful pre-transition states stay protected before erase/slide replacement
- end-of-video fallback preserves unfinished final content
- duplicate suppression remains conservative and protected evidence is never automatically removed

## Performance metrics

The visual-analysis result records and displays:

```text
source_frame_count
coarse_sample_count
fine_sample_count
analyzed_sample_count
activity_window_count
activity_seconds
static_seconds_skipped
estimated_frame_reduction_percent
processing_wall_seconds
analysis_real_time_factor
```

These are measurements, not hard runtime promises. Lecture activity and hardware vary. Static slide lectures should require much less fine analysis than continuous coding/whiteboard lectures.

Default adaptive settings:

```text
ANALYSIS_COARSE_FPS=4
ANALYSIS_FINE_FPS=12
ANALYSIS_COARSE_WIDTH=320
ANALYSIS_FINE_WIDTH=640
ANALYSIS_STABLE_SECONDS=1.25
ANALYSIS_PRE_WINDOW_PADDING_SECONDS=1.0
ANALYSIS_POST_WINDOW_PADDING_SECONDS=2.0
ANALYSIS_WINDOW_MERGE_GAP_SECONDS=2.0
```

Sampling FPS is capped to the source FPS for low-frame-rate videos.

## Transcript concurrency and caching

Raw faster-whisper transcription depends only on the prepared source video and transcription configuration. Notify can prewarm that raw transcript while adaptive visual scanning runs.

Changing the trusted screenshot set does **not** rerun Whisper. It only invalidates/rebuilds downstream screenshot-to-speech alignment and dependent stages.

Default transcript settings:

```text
WHISPER_MODEL=small.en
WHISPER_LANGUAGE=en
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

The first local transcription may download the configured pretrained faster-whisper model. Notify does not train a model.

## Coverage semantics

Coverage verification cross-checks visual events, stable checkpoints, protected candidates, trusted screenshots, transcript density, topics and OCR uncertainty.

Findings are separated by meaning:

```text
BLOCK
  Confirmed high-risk evidence loss, such as protected evidence missing,
  a topic without required trusted visual evidence, or an unresolved
  destructive scene transition.

REVIEW
  Suspicious but unconfirmed windows, such as a long speech-dense gap
  containing an unresolved stable state. These do not automatically prove
  content was lost.

WARNING
  OCR uncertainty and similar non-destructive uncertainty.
```

Duplicate-suppressed stable states and screenshots explicitly dismissed during candidate review are treated as represented evidence rather than repeatedly creating false blockers.

The final PDF still fails closed for confirmed blockers:

```text
blocking_finding_count == 0
        ↓
ready_for_pdf = true
```

OCR uncertainty never removes a screenshot.

## Core safety rules

```text
Writing still changing       → wait
Stable meaningful state      → candidate
Meaningful intermediate pause→ candidate
Important state before erase → protected candidate
Near-identical image         → suppress conservatively
OCR cannot read content      → keep screenshot
Confirmed evidence loss      → block PDF
```

Final PDF review may reorder trusted screenshots but cannot silently omit one. Every current trusted screenshot is included exactly once.

## Stack

### Frontend
- Next.js App Router
- TypeScript
- Tailwind CSS

### Backend
- Python / FastAPI / Uvicorn
- yt-dlp
- OpenCV + NumPy
- FFmpeg / ffprobe
- faster-whisper / CTranslate2
- Tesseract OCR
- ReportLab

No database, Redis, Kafka, cloud OCR, hosted LLM or paid API is required for the current local application.

## Local requirements

You need:

- Node.js / npm
- Python 3.11+
- FFmpeg including `ffprobe`
- Tesseract OCR 5+

Verify system tools:

```powershell
ffmpeg -version
ffprobe -version
tesseract --version
```

On Windows, if Tesseract is not on PATH, configure:

```text
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

## Backend setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Backend:

```text
http://localhost:8000
```

Useful checks:

```text
http://localhost:8000/health
http://localhost:8000/api/system/status
```

## Frontend setup

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

Frontend:

```text
http://localhost:3000
```

Default frontend configuration:

```text
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Runtime artifacts

A processed lecture uses local files such as:

```text
downloads/<video_id>/
├── lecture.mp4
├── metadata.json
└── analysis/
    ├── frame-timeline.jsonl
    ├── frame-timeline-summary.json
    ├── adaptive-analysis-summary.json
    ├── activity-windows.jsonl
    ├── frame-differences.jsonl
    ├── frame-differences-summary.json
    ├── teaching-states.jsonl
    ├── teaching-states-summary.json
    ├── screenshot-candidates.jsonl
    ├── screenshots/
    ├── candidate-review.json
    ├── trusted-screenshots.jsonl
    ├── trusted-screenshots/
    ├── transcript-audio.wav
    ├── transcript-segments.jsonl
    ├── transcript-summary.json
    ├── screenshot-transcript-map.jsonl
    ├── lecture-topics.jsonl
    ├── screenshot-ocr.jsonl
    ├── screenshot-content.jsonl
    ├── coverage-findings.jsonl
    ├── coverage-summary.json
    └── pdf-review.json

output/<video_id>/
├── lecture-notes.pdf
└── pdf-manifest.json
```

`frame-differences.jsonl` is now sparse adaptive evidence, not one JSON record for every original consecutive source-frame pair.

## Current end-to-end flow

```text
Paste YouTube URL
      ↓
Analyze metadata
      ↓
Prepare lecture
      ↓
Read video timing metadata
      ↓
Adaptive visual scan
      ↓
Stable teaching states
      ↓
Screenshot candidates
      ↓
Candidate review / trusted set
      ↓
Transcript alignment (raw transcript reused if prewarmed)
      ↓
Topics
      ↓
OCR
      ↓
Coverage verification
      ↓
Final page review
      ↓
Generate / preview / download PDF
```

## Verification

CI runs:

- full Python backend test suite
- FFmpeg availability in CI
- Tesseract availability and OCR smoke tests
- adaptive visual scanning tests with synthetic video
- teaching-state and screenshot protection tests
- transcript/topic/OCR/coverage/PDF tests
- frontend TypeScript typecheck
- Next.js production build

The adaptive tests verify that static-heavy video analyzes substantially fewer samples than its source-frame count while still identifying activity regions.

## Design principle

Notify optimizes **redundant frames**, not meaningful teaching states.

```text
expensive analysis only where the lecture changes
+
explicit protection around content loss
+
conservative review and coverage evidence
```

That is the basis of the performance architecture.
