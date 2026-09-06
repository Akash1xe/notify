# Notify — Lecture to PDF

Notify is a local-first lecture processing application. It accepts a YouTube lecture URL, prepares a verified local copy, detects stable teaching states, builds a protected screenshot set, generates a timestamped transcript, organizes the lecture into sections, enriches screenshots with OCR, and now performs a fail-closed missed-content audit before PDF generation.

> Current milestone: **Phase 5 complete — coverage verification / missed-content detection**.

## Current pipeline

```text
YouTube URL
    ↓
Validate + metadata
    ↓
Prepare verified lecture.mp4
    ↓
Build complete frame timeline
    ↓
Compare every consecutive frame pair
    ↓
Detect stable teaching states
    ↓
Extract screenshot candidates
    ↓
Conservative duplicate filtering
    ↓
Content-loss protection + manual review
    ↓
Ordered trusted screenshot set
    ↓
faster-whisper timestamped transcript
    ↓
Trusted screenshot ↔ nearby speech alignment
    ↓
Detect coherent lecture sections
    ↓
Tesseract OCR over every trusted screenshot
    ↓
Visible text + speech + topic context
    ↓
Fail-closed coverage audit
    ↓
PDF GATE: READY or BLOCKED
```

## Completed milestones

### Phase 1 — local lecture preparation

- YouTube URL validation and normalization
- yt-dlp metadata/accessibility inspection
- Metadata preview
- 720p-first local download/preparation
- FFmpeg/ffprobe media verification
- Background jobs, restart recovery, stale temp cleanup

### Phase 2 — visual teaching-state pipeline

#### 2.1 Frame timeline
- OpenCV sequential decoding
- One frame at a time in memory
- Ordered frame indexes and monotonic timestamps

#### 2.2 Visual change detection
- Inspects every consecutive frame pair
- Requires `N` decoded frames to produce exactly `N-1` comparisons
- Conservative `NONE`, `LOCAL`, `STRUCTURAL`, `SCENE` classification

#### 2.3 Stable teaching-state detection
- Collapses continuous writing/drawing into useful checkpoints
- Waits for stability instead of taking one screenshot per character
- Protects content before strong erase/replace transitions
- Preserves unfinished final content with an end-of-video fallback

#### 2.4 Screenshot extraction + deduplication
- Resolves checkpoints to exact lecture frames
- Saves high-quality JPEG candidates
- Near-duplicate filtering requires both dHash and pixel-distance agreement
- Protected checkpoints are never automatically discarded

#### 2.5 Candidate review + content protection
- Detects content-loss risk
- Maintains original evidence non-destructively
- Allows restore/suppress decisions for ordinary candidates
- Builds an ordered `trusted-screenshots` set

### Phase 3 — transcript + lecture structure

#### 3.1 Local transcript + screenshot alignment
- faster-whisper locally; no custom training
- mono 16 kHz audio extraction with FFmpeg
- timestamped transcript segments
- trusted screenshot ↔ nearby speech alignment
- screenshot review changes rebuild alignment without rerunning Whisper

#### 3.2 Topic / section detection
- Deterministic and local
- Uses speech gaps, vocabulary shifts, transition phrases, and visual transitions
- Assigns every trusted screenshot to exactly one section
- Supports visual-only sections when speech is sparse

### Phase 4 — OCR + screenshot content enrichment

- Local Tesseract OCR
- visible text, lines, bounding boxes, confidence, word counts
- separate raw OCR and enrichment caches
- combines visible text + nearby speech + lecture topic
- OCR uncertainty never removes a screenshot

Important rule:

```text
OCR says no text
       ≠
screenshot is unimportant
```

Handwriting, equations, diagrams, code formatting, and low-contrast boards remain valid visual evidence even when OCR is weak.

### Phase 5 — coverage verification / missed-content detection

Phase 5 is a **fail-closed safety gate**. It does not simply calculate a score. It checks whether evidence suggests that important teaching content may have been omitted from the trusted screenshot set.

The audit cross-checks:

- complete frame-change history
- stable teaching-state checkpoints
- protected/content-loss screenshot candidates
- final trusted screenshots
- transcript density
- lecture-topic coverage
- OCR confidence/no-text uncertainty

Current blocking checks include:

#### Uncaptured strong visual changes

A `SCENE` change or sufficiently strong `STRUCTURAL` change with no nearby trusted screenshot creates:

```text
UNCAPTURED_STRONG_VISUAL_CHANGE
```

If a stable teaching state also exists near that window, the finding additionally records:

```text
STABLE_STATE_NOT_IN_TRUSTED_SET
```

#### Protected evidence missing from the trusted set

If a screenshot candidate was marked protected or as content-loss risk but is absent from the final trusted set:

```text
PROTECTED_EVIDENCE_NOT_TRUSTED
```

This is blocking.

#### Long screenshot gaps

Long intervals between trusted screenshots are rechecked against transcript density, visual-change activity, and stable-state checkpoints. Suspicious gaps can produce:

```text
LONG_TRUSTED_SCREENSHOT_GAP
SPEECH_DENSE_GAP
UNUSED_STABLE_STATE_IN_GAP
```

#### Topic with no trusted screenshot

A detected lecture topic with zero trusted screenshots creates:

```text
TOPIC_WITHOUT_TRUSTED_SCREENSHOT
```

#### OCR uncertainty

OCR uncertainty produces warnings such as:

```text
OCR_NO_TEXT
OCR_LOW_CONFIDENCE
```

These are deliberately **non-blocking** by themselves and do not delete evidence.

## PDF readiness gate

The final decision is intentionally simple:

```text
blocking findings == 0
        ↓
ready_for_pdf = true
```

Otherwise:

```text
blocking findings > 0
        ↓
ready_for_pdf = false
        ↓
PDF generation blocked
```

The coverage report states that the implemented evidence checks passed; it does **not** claim a mathematical guarantee that arbitrary lecture content can never be missed.

## Coverage audit persistence and cache validity

Phase 5 stores:

```text
coverage-findings.jsonl
coverage-summary.json
```

Every finding records:

- severity
- whether it blocks PDF generation
- suspicious time range
- reason codes
- supporting evidence
- that the window was rechecked across the available evidence layers

The coverage cache includes upstream generation versions. Changes to visual analysis, trusted screenshot review, topics, OCR, or enriched content invalidate the old coverage result instead of reusing stale approval.

## Runtime storage

A lecture that reaches Phase 5 can contain:

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
    └── coverage-summary.json
```

## Stack

### Frontend
- Next.js App Router
- TypeScript
- Tailwind CSS

### Backend
- Python / FastAPI / Uvicorn
- yt-dlp
- OpenCV / NumPy
- FFmpeg / ffprobe
- faster-whisper / CTranslate2
- Tesseract OCR

## Local requirements

Recommended:

- Node.js 20+
- Python 3.11+
- FFmpeg with `ffmpeg` and `ffprobe`
- Tesseract OCR 5+

Verify:

```powershell
ffmpeg -version
ffprobe -version
tesseract --version
```

On Windows, make `tesseract.exe` available on `PATH` or configure `TESSERACT_CMD`.

## Backend setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend: `http://localhost:8000`

Optional configuration:

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

## Frontend setup

```powershell
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

Frontend: `http://localhost:3000`

```text
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Main Phase 5 API

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/analysis/coverage/start` | Start/reuse fail-closed coverage audit |
| GET | `/api/analysis/coverage/jobs/{job_id}` | Poll coverage job |
| GET | `/api/analysis/{video_id}/coverage` | Read coverage summary + findings |

Earlier phase APIs remain available for preparation, frame analysis, screenshot review, transcript, topics, and OCR.

## Verification

GitHub Actions performs:

- Python 3.12 backend tests
- FFmpeg installation
- Tesseract installation and verification
- real Tesseract smoke test
- deterministic OCR tests
- deterministic coverage-audit tests
- frontend TypeScript typecheck
- Next.js production build

Coverage-specific tests verify:

- a clean evidence chain passes the PDF gate
- an uncaptured scene/stable state blocks PDF readiness
- OCR no-text / low-confidence conditions remain warning-only
- a topic without screenshots blocks coverage
- an upstream evidence-version change invalidates cached coverage

## Current user flow

```text
Paste YouTube URL
      ↓
Prepare lecture
      ↓
Frame timeline
      ↓
Visual changes
      ↓
Stable teaching states
      ↓
Screenshot extraction
      ↓
Candidate review + trusted set
      ↓
Transcript
      ↓
Lecture topics
      ↓
OCR + content enrichment
      ↓
Verify Lecture Coverage
      ↓
PASS → PDF READY
or
BLOCKED → review findings
```

## Not implemented yet

- final PDF generation
- final PDF layout/review/export UI
- OCR specifically trained for handwriting or mathematical notation

## Next milestone

**Phase 6 — Final PDF Generator + Final UI**

Phase 6 must consume the ordered trusted screenshot/topic data only after Phase 5 reports:

```text
ready_for_pdf = true
```

It will produce the final ordered lecture PDF, topic-aware layout, preview/export flow, and final local file output.
