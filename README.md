# Notify — Lecture to PDF

Notify is a local-first lecture processing application. It accepts a YouTube lecture URL, prepares and verifies a local copy, detects stable teaching states, builds a protected screenshot set, generates a timestamped local transcript, groups the lecture into sections, and now extracts visible screenshot text with local OCR.

> Current milestone: **Phase 4 complete — OCR + screenshot content enrichment**.

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
Extract 16 kHz mono audio
    ↓
faster-whisper timestamped transcript
    ↓
Trusted screenshot ↔ nearby speech alignment
    ↓
Detect coherent lecture sections
    ↓
Assign every trusted screenshot to one section
    ↓
Tesseract OCR over every trusted screenshot
    ↓
Visible text + nearby speech + topic context
    ↓
ENRICHED TRUSTED SCREENSHOT SET
```

## Completed milestones

### Phase 1 — local lecture preparation

- YouTube URL validation and normalization
- yt-dlp metadata/accessibility inspection
- Metadata preview
- 720p-first local download/preparation
- FFmpeg/ffprobe media verification
- Background preparation jobs and progress polling
- Restart-safe prepared-video reuse
- Interrupted-job recovery and stale temp cleanup

### Phase 2.1 — frame timeline

- OpenCV sequential decoding
- One frame at a time in memory
- Ordered frame indexes and monotonic timestamps
- Persisted complete timeline

### Phase 2.2 — visual change detection

- Inspects every consecutive frame pair
- Requires `N` decoded frames to produce exactly `N-1` comparisons
- Conservative `NONE`, `LOCAL`, `STRUCTURAL`, `SCENE` classification
- Uses color, edges, changed-region area, and pixel differences
- Does not discard local changes prematurely

### Phase 2.3 — stable teaching-state detection

- Groups continuous writing/drawing into temporal activity
- Normal checkpoint after about 1.25 seconds of stability
- Avoids one screenshot per written character
- Protects completed content before strong transitions
- Keeps unfinished final content with an end-of-video fallback

### Phase 2.4 — screenshot extraction + deduplication

- Resolves stable checkpoints to exact lecture frames
- Saves high-quality JPEG candidates
- Persists evidence for every checkpoint, including suppressed duplicates
- Near-duplicate removal requires both dHash and pixel-distance agreement
- Protected checkpoints are never automatically discarded

### Phase 2.5 — candidate review + content protection

- Detects scene/detail-loss risk
- Builds a separate ordered trusted screenshot set
- Original candidate evidence remains non-destructive
- Allows manual restore/suppress for ordinary candidates
- Prevents accidental suppression of protected candidates

### Phase 3.1 — local transcript + screenshot alignment

- Uses faster-whisper locally; no custom model training
- Extracts mono 16 kHz WAV with FFmpeg
- Default model: `small.en`
- Default CPU compute mode: `int8`
- Persists timestamped transcript segments
- Aligns every trusted screenshot to nearby speech
- Default context window: 6 seconds before / 8 seconds after screenshot time
- Silent screenshots remain valid educational content
- Screenshot review changes rebuild alignment without rerunning Whisper

### Phase 3.2 — lecture topic / section detection

Topic detection is deterministic and local. It combines:

- meaningful speech gaps
- transcript vocabulary shifts
- explicit transition phrases such as `next`, `moving on`, or `finally`
- strong visual section transitions from screenshot provenance

Current section-duration defaults:

- minimum normal section duration: about **45 seconds**
- maximum section duration before a forced split: about **5 minutes**

Every trusted screenshot must be assigned to exactly one section. Coverage fails closed if this is not true. Visual-only sections are supported when speech is sparse.

### Phase 4 — OCR + screenshot content enrichment

OCR is local and uses the **Tesseract** system executable directly. No cloud OCR service and no custom model training are required.

For every trusted screenshot Notify now stores:

- detected visible text
- OCR line records
- per-line bounding boxes
- line confidence
- screenshot mean OCR confidence
- OCR word/line counts
- whether text was detected
- whether recognized text is low-confidence

Before OCR, Notify applies conservative preprocessing:

- grayscale conversion
- dark-screen inversion when appropriate
- upscaling for smaller screenshots
- local contrast enhancement with CLAHE

Default OCR settings:

```text
OCR_LANGUAGE=eng
OCR_PSM=11
```

`PSM 11` is used as a practical sparse-text default for lecture slides, boards, editors, diagrams, and mixed-layout screens.

The current low-confidence marker is approximately:

```text
mean OCR confidence < 55
```

This is a review/coverage signal only. It does not remove screenshots.

## OCR is evidence, not authority

A critical project rule is:

```text
OCR says no text
       ≠
screenshot is unimportant
```

Tesseract is useful for printed slide text, editor text, headings, and many code screens. It can be weaker on:

- handwriting
- mathematical notation
- roots/fractions/integrals
- dense equations
- diagrams
- arrows and geometric notation
- stylized fonts
- low-contrast board writing

Therefore a trusted screenshot with empty or poor OCR remains in the trusted set. Later coverage verification uses OCR as one signal alongside visual-change history, protection flags, transcript context, and topic coverage.

## Separate OCR and enrichment caches

Raw OCR depends on the trusted screenshot set:

```text
trusted screenshots
      ↓
Tesseract OCR
      ↓
screenshot-ocr.jsonl
```

Content enrichment additionally depends on the current topics/alignment:

```text
raw OCR
   +
nearby speech
   +
lecture topic
   ↓
screenshot-content.jsonl
```

Therefore:

```text
Topic grouping changes
       ↓
Keep unchanged raw OCR
       ↓
Rebuild only screenshot/topic/speech enrichment
```

If the trusted screenshot set changes, raw OCR is invalidated and recomputed for the new trusted set.

## Enriched screenshot record

A persisted screenshot enrichment is conceptually:

```json
{
  "trusted_index": 7,
  "candidate_index": 9,
  "frame_index": 2310,
  "timestamp_seconds": 77.0,
  "topic_index": 2,
  "topic_title": "Binary Search Mid Calculation",
  "visible_text": "mid = low + (high - low) / 2",
  "nearby_speech": "Now calculate the middle index using low and high.",
  "combined_context": "mid = low + (high - low) / 2\n\nNow calculate the middle index using low and high.",
  "ocr_mean_confidence": 88.4,
  "ocr_word_count": 8,
  "coverage_flags": []
}
```

Possible coverage flags currently include:

```text
OCR_NO_TEXT
OCR_LOW_CONFIDENCE
NO_NEARBY_SPEECH
```

These flags identify uncertainty; they do not delete evidence.

## Topic-level visual enrichment

Each lecture topic also receives lightweight visual-text statistics:

- trusted screenshot count
- screenshots with OCR text
- OCR word count
- common visual keywords

This gives later coverage verification both spoken and visible topic evidence.

## Runtime storage

A lecture that reaches Phase 4 can contain:

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
    └── topic-content.jsonl
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
- Tesseract OCR

## Local requirements

Recommended:

- Node.js 20+
- Python 3.11+
- FFmpeg with `ffmpeg` and `ffprobe`
- Tesseract OCR 5+

Verify the media tools:

```powershell
ffmpeg -version
ffprobe -version
```

Verify OCR:

```powershell
tesseract --version
```

On Windows, install Tesseract 5 and either make `tesseract.exe` available on `PATH` or set `TESSERACT_CMD` to its full executable path.

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

### Optional backend configuration

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

`TESSERACT_CMD` is optional when `tesseract` is already available on `PATH`.

For multilingual OCR, install the corresponding Tesseract language data and change `OCR_LANGUAGE`.

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
| GET | `/api/system/status` | FFmpeg/ffprobe/Tesseract/storage capability status |
| POST | `/api/video/metadata` | Validate and read YouTube metadata |
| POST | `/api/video/prepare` | Prepare/reuse local lecture |
| GET | `/api/jobs/{job_id}` | Poll video preparation |
| POST | `/api/analysis/start` | Build/reuse frame timeline |
| GET | `/api/analysis/{video_id}/timeline` | Frame timeline summary |
| POST | `/api/analysis/changes/start` | Analyze visual changes |
| GET | `/api/analysis/{video_id}/changes` | Visual-change summary |
| POST | `/api/analysis/states/start` | Detect stable teaching states |
| GET | `/api/analysis/{video_id}/states` | Teaching-state summary |
| POST | `/api/analysis/candidates/start` | Extract screenshot candidates |
| GET | `/api/analysis/{video_id}/candidates` | Candidate summary |
| GET | `/api/analysis/{video_id}/candidate-review` | Review/trusted screenshot state |
| PUT | `/api/analysis/{video_id}/candidate-review/{candidate_index}` | Keep/restore/suppress candidate |
| GET | `/api/analysis/{video_id}/candidates/{candidate_index}/image` | Candidate preview |
| POST | `/api/analysis/transcript/start` | Generate/reuse transcript + alignment |
| GET | `/api/analysis/transcript/jobs/{job_id}` | Poll transcript job |
| GET | `/api/analysis/{video_id}/transcript` | Transcript/alignment summary |
| POST | `/api/analysis/topics/start` | Detect lecture sections |
| GET | `/api/analysis/topics/jobs/{job_id}` | Poll topic job |
| GET | `/api/analysis/{video_id}/topics` | Ordered topic result |
| POST | `/api/analysis/ocr/start` | OCR and enrich trusted screenshots |
| GET | `/api/analysis/ocr/jobs/{job_id}` | Poll OCR job |
| GET | `/api/analysis/{video_id}/ocr` | OCR/enrichment summary |
| GET | `/api/storage/status` | Local storage usage |
| POST | `/api/storage/cleanup` | Remove stale temporary workspaces |

## Verification

GitHub Actions currently performs:

- Python 3.12 backend tests
- FFmpeg installation
- Tesseract OCR installation + `tesseract --version`
- deterministic OCR service tests with a fake OCR engine
- a real Tesseract smoke test against a generated high-contrast lecture image
- frontend TypeScript typecheck
- Next.js production build

OCR-specific tests cover:

- full trusted-screenshot OCR coverage
- text/no-text classification
- low-confidence classification
- TSV line/bounding-box parsing
- visible-text topic keywords
- screenshot + speech + topic enrichment
- topic changes reuse cached raw OCR
- trusted screenshot changes invalidate raw OCR
- actual Tesseract subprocess recognition path

## Current user flow

```text
Paste YouTube URL
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
Candidate review / protected trusted set
      ↓
Transcript generation
      ↓
Lecture topic detection
      ↓
Enrich Screenshot Content
      ↓
Tesseract OCR
      ↓
Visible text + nearby speech + topic context
      ↓
OCR ENRICHMENT READY
```

## Not implemented yet

- full lecture coverage verification/recheck pass
- OCR specifically trained for handwriting or mathematical notation
- semantic importance ranking
- final PDF generation
- final PDF review/export UI

## Next milestone

**Phase 5 — Coverage Verification / Missed-Content Detection**

This is the next critical safety stage before PDF generation.

It will use the evidence already produced:

```text
complete frame timeline
        +
visual change history
        +
stable-state checkpoints
        +
protected screenshot candidates
        +
trusted screenshots
        +
transcript
        +
topic coverage
        +
OCR/visual-text uncertainty
        ↓
coverage audit
        ↓
identify suspicious gaps / possible missed teaching content
        ↓
recheck those time windows conservatively
```

Only after the coverage pass is trusted should the application move to final PDF generation.
