# Notify — Lecture to PDF

Notify is a local-first lecture processing application. It accepts a YouTube lecture URL, prepares a verified local video, detects stable teaching states, builds a protected screenshot set, generates a timestamped local transcript, and now organizes that transcript and the trusted screenshots into ordered lecture sections.

> Current milestone: **Phase 3.2 complete — lecture topic / section detection**.

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

Topic detection is deterministic and local. It does not require an external LLM.

Boundary evidence combines:

- meaningful speech gaps
- transcript vocabulary shifts
- explicit transition phrases such as "next", "moving on", or "finally"
- strong visual section transitions from screenshot provenance

The detector also applies section-duration constraints so normal sentence changes do not become dozens of tiny topics.

Current defaults:

- minimum normal section duration: about **45 seconds**
- maximum section duration before a forced split: about **5 minutes**

For each section Notify persists:

- ordered topic index
- locally derived title
- start/end timestamps
- transcript segment range
- word count
- top keywords
- boundary reasons
- trusted screenshot indexes
- original candidate indexes
- screenshot count

Coverage fails closed unless every trusted screenshot is assigned to a section.

If a lecture contains trusted visual content but little/no detected speech, Notify can create visual-only sections rather than deleting those screenshots.

## Topic detection example

```text
0:00  Binary Search Introduction
        screenshots 0, 1

1:05  Search Space And Mid Calculation
        screenshots 2, 3, 4

3:10  Moving Low And High
        screenshots 5, 6

5:40  Time Complexity And Logarithmic Growth
        screenshots 7, 8
```

The titles are heuristic local labels. The original transcript and screenshot evidence remain unchanged and can be enriched later by OCR/semantic processing.

## Runtime storage

A lecture that reaches Phase 3.2 can contain:

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
    └── lecture-topics-summary.json
```

A topic record is conceptually:

```json
{
  "topic_index": 2,
  "title": "Time complexity and logarithmic growth",
  "start_seconds": 301.5,
  "end_seconds": 420.2,
  "segment_start_index": 48,
  "segment_end_index": 66,
  "keywords": ["complexity", "logarithmic", "binary", "search"],
  "boundary_reasons": ["TRANSITION_PHRASE", "VOCABULARY_SHIFT"],
  "trusted_screenshot_indexes": [7, 8],
  "screenshot_count": 2
}
```

## Why data layers remain separate

```text
lecture.mp4
    ↓
visual evidence
    ↓
trusted screenshots

lecture.mp4
    ↓
audio
    ↓
raw timestamped transcript

trusted screenshots + transcript
    ↓
alignment
    ↓
ordered topic groups
```

Changing a screenshot review decision does not destroy or regenerate the raw transcript. Topic results are invalidated and rebuilt only when their transcript/alignment/trusted-set dependencies change.

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

```text
WHISPER_MODEL=small.en
WHISPER_LANGUAGE=en
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

The first real transcription may need internet access once to download the selected pretrained model. Afterwards the local model cache can be reused.

## Frontend setup

```powershell
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

Frontend: `http://localhost:3000`

Default frontend environment:

```text
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Topic API

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/analysis/topics/start` | Start/reuse lecture topic detection |
| GET | `/api/analysis/topics/jobs/{job_id}` | Poll topic detection |
| GET | `/api/analysis/{video_id}/topics` | Read ordered topic groups |

The existing transcript endpoints remain:

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/analysis/transcript/start` | Generate/reuse transcript + alignment |
| GET | `/api/analysis/transcript/jobs/{job_id}` | Poll transcription |
| GET | `/api/analysis/{video_id}/transcript` | Read transcript/alignment summary |

## Verification

GitHub Actions runs:

- backend automated tests on Python 3.12 with FFmpeg
- frontend TypeScript typecheck
- Next.js production build

Phase 3.2 tests verify:

- coherent section splitting from transcript/visual evidence
- transition phrase + vocabulary-shift boundaries
- every trusted screenshot is assigned exactly once
- topic result cache is tied to transcript, alignment, and trusted-set versions
- changing the trusted screenshot version invalidates topics without changing the raw transcript

## Not implemented yet

- OCR / screenshot text extraction
- transcript + OCR semantic enrichment
- semantic importance/ranking
- final coverage-verification pass
- PDF generation

## Next milestone

**Phase 4 — OCR + Screenshot Content Enrichment foundation**

The next stage should extract visible text from trusted screenshots locally, preserve equations/code/board text where practical, and combine screenshot text with transcript/topic context before the final coverage and PDF stages.
