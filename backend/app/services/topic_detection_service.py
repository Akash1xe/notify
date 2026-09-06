from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable

from app.core.errors import AppError, ErrorCode
from app.models.job import utc_now_iso
from app.services.candidate_review_service import CandidateReviewService
from app.services.storage_service import StorageService
from app.services.transcription_service import TranscriptionService

ProgressCallback = Callable[[float, str], None]


class TopicDetectionService:
    PIPELINE_VERSION = 1
    MIN_TOPIC_SECONDS = 45.0
    MAX_TOPIC_SECONDS = 300.0
    BOUNDARY_THRESHOLD = 0.9

    STOPWORDS = {
        "a", "about", "after", "again", "all", "also", "am", "an", "and", "any", "are", "as", "at",
        "be", "because", "been", "before", "being", "but", "by", "can", "could", "did", "do", "does",
        "doing", "for", "from", "get", "go", "going", "got", "had", "has", "have", "he", "here", "how",
        "i", "if", "in", "into", "is", "it", "its", "just", "let", "like", "may", "me", "more", "most",
        "my", "no", "not", "now", "of", "on", "one", "or", "our", "out", "over", "right", "say", "see",
        "so", "some", "such", "than", "that", "the", "their", "them", "then", "there", "these", "they",
        "this", "those", "to", "too", "up", "us", "use", "very", "was", "we", "well", "were", "what",
        "when", "where", "which", "while", "who", "why", "will", "with", "would", "you", "your", "okay",
        "basically", "actually", "simply", "thing", "things", "example", "suppose"
    }

    TRANSITION_RE = re.compile(
        r"^(?:okay[, ]+)?(?:now|next|finally|first|second|third|then|moving on|let(?:'s| us)|we will now|"
        r"coming to|the next|another important|now we|now let|so now|after this)\b",
        re.IGNORECASE,
    )

    def __init__(self, storage: StorageService, transcription: TranscriptionService, review: CandidateReviewService) -> None:
        self.storage = storage
        self.transcription = transcription
        self.review = review

    def _topics_path(self, video_id: str) -> Path:
        return self.storage.analysis_dir(video_id) / "lecture-topics.jsonl"

    def _summary_path(self, video_id: str) -> Path:
        return self.storage.analysis_dir(video_id) / "lecture-topics-summary.json"

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
            return value if isinstance(value, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        except OSError as exc:
            temp.unlink(missing_ok=True)
            raise AppError(ErrorCode.TOPIC_DETECTION_FAILED, "Lecture topic metadata could not be saved.", 500) from exc

    @staticmethod
    def _write_jsonl_atomic(path: Path, records: Iterable[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        except OSError as exc:
            temp.unlink(missing_ok=True)
            raise AppError(ErrorCode.TOPIC_DETECTION_FAILED, "Lecture topic records could not be saved.", 500) from exc

    def _load_jsonl(self, path: Path, index_key: str, expected_count: int, error_message: str) -> list[dict]:
        records: list[dict] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    payload = json.loads(line)
                    if not isinstance(payload, dict) or int(payload[index_key]) != len(records):
                        raise ValueError
                    records.append(payload)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise AppError(ErrorCode.TOPIC_DETECTION_FAILED, error_message, 422) from exc
        if len(records) != expected_count:
            raise AppError(ErrorCode.TOPIC_DETECTION_FAILED, error_message, 422)
        return records

    @classmethod
    def _tokens(cls, text: str) -> list[str]:
        return [
            token for token in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{2,}", text.lower())
            if token not in cls.STOPWORDS
        ]

    @classmethod
    def _window_tokens(cls, segments: list[dict], start: int, end: int) -> set[str]:
        values: set[str] = set()
        for segment in segments[max(0, start):min(len(segments), end)]:
            values.update(cls._tokens(str(segment.get("text") or "")))
        return values

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / max(1, len(left | right))

    def _candidate_visual_signals(self, video_id: str) -> dict[int, str]:
        result: dict[int, str] = {}
        path = self.storage.screenshot_candidates_path(video_id)
        if not path.exists():
            return result
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    payload = json.loads(line)
                    candidate_index = int(payload["candidate_index"])
                    source_kind = str(payload.get("source_change_kind") or "")
                    reason = str(payload.get("reason") or "")
                    if source_kind == "SCENE" or reason in {"PRE_TRANSITION_PROTECTION", "END_OF_VIDEO_FALLBACK"}:
                        result[candidate_index] = source_kind or reason
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return {}
        return result

    def _boundary_scores(self, segments: list[dict], screenshot_map: list[dict], visual_signals: dict[int, str]) -> list[dict]:
        strong_visual_times = [
            float(item["timestamp_seconds"])
            for item in screenshot_map
            if int(item.get("candidate_index", -1)) in visual_signals
        ]
        candidates: list[dict] = []
        for index in range(1, len(segments)):
            previous = segments[index - 1]
            current = segments[index]
            start = float(current["start_seconds"])
            gap = max(0.0, start - float(previous["end_seconds"]))
            left = self._window_tokens(segments, index - 3, index)
            right = self._window_tokens(segments, index, index + 3)
            similarity = self._jaccard(left, right)
            text = str(current.get("text") or "").strip()
            cue = bool(self.TRANSITION_RE.match(text))
            visual = any(abs(timestamp - start) <= 6.0 for timestamp in strong_visual_times)

            score = 0.0
            reasons: list[str] = []
            if gap >= 15.0:
                score += 0.9
                reasons.append("LONG_SPEECH_GAP")
            elif gap >= 8.0:
                score += 0.55
                reasons.append("SPEECH_GAP")
            if cue:
                score += 0.65
                reasons.append("TRANSITION_PHRASE")
            if len(left) >= 5 and len(right) >= 5:
                novelty = 1.0 - similarity
                score += novelty * 0.55
                if novelty >= 0.72:
                    reasons.append("VOCABULARY_SHIFT")
            if visual:
                score += 0.5
                reasons.append("VISUAL_SECTION_CHANGE")

            candidates.append({
                "segment_index": index,
                "timestamp_seconds": start,
                "score": round(score, 6),
                "reasons": reasons,
            })
        return candidates

    def _choose_boundaries(self, segments: list[dict], candidates: list[dict]) -> list[dict]:
        if not segments:
            return []
        chosen: list[dict] = []
        topic_start = float(segments[0]["start_seconds"])
        pending: list[dict] = []
        by_index = {int(item["segment_index"]): item for item in candidates}

        for index in range(1, len(segments)):
            current = by_index.get(index)
            timestamp = float(segments[index]["start_seconds"])
            elapsed = timestamp - topic_start
            if current and current["score"] >= self.BOUNDARY_THRESHOLD:
                pending.append(current)

            if elapsed >= self.MIN_TOPIC_SECONDS and pending:
                eligible = [item for item in pending if float(item["timestamp_seconds"]) - topic_start >= self.MIN_TOPIC_SECONDS]
                if eligible:
                    best = max(eligible, key=lambda item: (float(item["score"]), float(item["timestamp_seconds"])))
                    chosen.append(best)
                    topic_start = float(best["timestamp_seconds"])
                    pending = [item for item in pending if int(item["segment_index"]) > int(best["segment_index"])]
                    continue

            if elapsed >= self.MAX_TOPIC_SECONDS:
                start_index = chosen[-1]["segment_index"] if chosen else 0
                pool = [
                    item for item in candidates
                    if start_index < int(item["segment_index"]) <= index
                    and float(item["timestamp_seconds"]) - topic_start >= self.MIN_TOPIC_SECONDS
                ]
                if pool:
                    best = max(pool, key=lambda item: float(item["score"]))
                else:
                    best = {
                        "segment_index": index,
                        "timestamp_seconds": timestamp,
                        "score": 0.0,
                        "reasons": ["MAX_SECTION_DURATION"],
                    }
                if not best.get("reasons"):
                    best["reasons"] = ["MAX_SECTION_DURATION"]
                chosen.append(best)
                topic_start = float(best["timestamp_seconds"])
                pending = []
        return chosen

    @classmethod
    def _keywords(cls, texts: list[str], limit: int = 5) -> list[str]:
        counter: Counter[str] = Counter()
        for text in texts:
            counter.update(cls._tokens(text))
        return [word for word, _ in counter.most_common(limit)]

    @classmethod
    def _title(cls, texts: list[str], keywords: list[str], topic_index: int) -> str:
        clean: list[str] = []
        for text in texts:
            value = re.sub(cls.TRANSITION_RE, "", text.strip(), count=1).strip(" ,.-:")
            value = re.sub(r"\s+", " ", value)
            words = value.split()
            if 3 <= len(words) <= 12:
                clean.append(value)
        if clean:
            keyword_set = set(keywords)
            best = max(clean, key=lambda text: sum(1 for token in cls._tokens(text) if token in keyword_set))
            words = best.split()[:9]
            title = " ".join(words).strip(" ,.-:")
            if title:
                return title[0].upper() + title[1:]
        if keywords:
            return " · ".join(word.replace("-", " ").title() for word in keywords[:3])
        return f"Lecture Section {topic_index + 1}"

    def _visual_only_topics(self, trusted_records: list[dict], duration: float) -> list[dict]:
        if not trusted_records:
            return []
        groups: list[list[dict]] = [[]]
        group_start = float(trusted_records[0]["timestamp_seconds"])
        last = group_start
        for record in trusted_records:
            timestamp = float(record["timestamp_seconds"])
            if groups[-1] and ((timestamp - last >= 90.0 and timestamp - group_start >= self.MIN_TOPIC_SECONDS) or timestamp - group_start >= self.MAX_TOPIC_SECONDS):
                groups.append([])
                group_start = timestamp
            groups[-1].append(record)
            last = timestamp
        topics: list[dict] = []
        for index, group in enumerate(groups):
            start = float(group[0]["timestamp_seconds"])
            end = float(groups[index + 1][0]["timestamp_seconds"]) if index + 1 < len(groups) else max(start, duration)
            topics.append({
                "topic_index": index,
                "title": f"Visual Lecture Section {index + 1}",
                "start_seconds": round(start, 6),
                "end_seconds": round(end, 6),
                "duration_seconds": round(max(0.0, end - start), 6),
                "segment_start_index": None,
                "segment_end_index": None,
                "segment_count": 0,
                "word_count": 0,
                "keywords": [],
                "boundary_reasons": ["VISUAL_ONLY" if index else "LECTURE_START"],
                "trusted_screenshot_indexes": [int(item["trusted_index"]) for item in group],
                "candidate_indexes": [int(item["candidate_index"]) for item in group],
                "screenshot_count": len(group),
            })
        return topics

    def _build_topics(self, segments: list[dict], trusted_records: list[dict], boundaries: list[dict], duration: float) -> list[dict]:
        if not segments:
            return self._visual_only_topics(trusted_records, duration)

        starts = [0] + [int(item["segment_index"]) for item in boundaries]
        ends = [index - 1 for index in starts[1:]] + [len(segments) - 1]
        topics: list[dict] = []
        for topic_index, (start_index, end_index) in enumerate(zip(starts, ends)):
            chunk = segments[start_index:end_index + 1]
            start_seconds = float(chunk[0]["start_seconds"])
            end_seconds = float(chunk[-1]["end_seconds"])
            if topic_index + 1 < len(starts):
                end_seconds = max(end_seconds, float(segments[starts[topic_index + 1]]["start_seconds"]))
            elif duration > 0:
                end_seconds = max(end_seconds, duration)

            screenshots = [
                record for record in trusted_records
                if float(record["timestamp_seconds"]) >= start_seconds
                and (topic_index == len(starts) - 1 or float(record["timestamp_seconds"]) < end_seconds)
            ]
            texts = [str(segment.get("text") or "").strip() for segment in chunk if str(segment.get("text") or "").strip()]
            keywords = self._keywords(texts)
            boundary_reasons = ["LECTURE_START"] if topic_index == 0 else list(boundaries[topic_index - 1].get("reasons") or ["DETECTED_BOUNDARY"])
            topics.append({
                "topic_index": topic_index,
                "title": self._title(texts, keywords, topic_index),
                "start_seconds": round(start_seconds, 6),
                "end_seconds": round(end_seconds, 6),
                "duration_seconds": round(max(0.0, end_seconds - start_seconds), 6),
                "segment_start_index": start_index,
                "segment_end_index": end_index,
                "segment_count": len(chunk),
                "word_count": sum(len(text.split()) for text in texts),
                "keywords": keywords,
                "boundary_reasons": boundary_reasons,
                "trusted_screenshot_indexes": [int(item["trusted_index"]) for item in screenshots],
                "candidate_indexes": [int(item["candidate_index"]) for item in screenshots],
                "screenshot_count": len(screenshots),
            })
        return topics

    def get_result(self, video_id: str) -> dict | None:
        transcript_result = self.transcription.get_result(video_id)
        if not transcript_result:
            return None
        trusted = self.review.get_review(video_id).get("summary")
        if not isinstance(trusted, dict):
            return None
        summary = self._read_json(self._summary_path(video_id))
        topics_path = self._topics_path(video_id)
        if not summary or not topics_path.exists():
            return None
        if summary.get("video_id") != video_id or int(summary.get("pipeline_version") or 0) != self.PIPELINE_VERSION:
            return None
        transcript = transcript_result["transcript"]
        if summary.get("transcript_generated_at") != transcript.get("generated_at"):
            return None
        if summary.get("trusted_generated_at") != trusted.get("generated_at"):
            return None
        if summary.get("alignment_generated_at") != transcript_result["alignment"].get("generated_at"):
            return None
        try:
            topics = self._load_jsonl(topics_path, "topic_index", int(summary["topic_count"]), "Persisted lecture topics are invalid.")
        except AppError:
            return None
        return {"summary": summary, "topics": topics}

    def process(self, video_id: str, progress: ProgressCallback) -> dict:
        cached = self.get_result(video_id)
        if cached:
            progress(100.0, "Lecture topics already exist and are valid.")
            return cached

        transcript_result = self.transcription.get_result(video_id)
        if not transcript_result:
            raise AppError(ErrorCode.TRANSCRIPT_NOT_FOUND, "Generate and align the lecture transcript before detecting topics.", 409)
        transcript = transcript_result["transcript"]
        alignment = transcript_result["alignment"]
        review_result = self.review.get_review(video_id)
        trusted = review_result.get("summary")
        if not isinstance(trusted, dict):
            raise AppError(ErrorCode.TRUSTED_SCREENSHOTS_NOT_FOUND, "The trusted screenshot set is unavailable.", 409)

        progress(8.0, "Loading timestamped transcript and trusted screenshot timing...")
        segments = self._load_jsonl(
            self.storage.transcript_segments_path(video_id),
            "segment_index",
            int(transcript.get("segment_count") or 0),
            "The timestamped transcript is invalid.",
        )
        trusted_records = self._load_jsonl(
            self.storage.analysis_dir(video_id) / "trusted-screenshots.jsonl",
            "trusted_index",
            int(trusted.get("selected_count") or 0),
            "The trusted screenshot manifest is invalid.",
        )
        screenshot_map = self._load_jsonl(
            self.storage.screenshot_transcript_map_path(video_id),
            "trusted_index",
            int(alignment.get("trusted_screenshot_count") or 0),
            "The screenshot transcript alignment is invalid.",
        )

        progress(30.0, "Scoring speech gaps, vocabulary shifts, and visual section changes...")
        visual_signals = self._candidate_visual_signals(video_id)
        candidates = self._boundary_scores(segments, screenshot_map, visual_signals)
        boundaries = self._choose_boundaries(segments, candidates)

        progress(62.0, "Building coherent lecture sections and assigning trusted screenshots...")
        duration = float(transcript.get("duration_seconds") or 0.0)
        topics = self._build_topics(segments, trusted_records, boundaries, duration)
        if not topics and trusted_records:
            topics = self._visual_only_topics(trusted_records, duration)
        if not topics:
            raise AppError(ErrorCode.TOPIC_DETECTION_FAILED, "No transcript or trusted screenshot content was available for topic detection.", 422)

        assigned = sum(int(topic["screenshot_count"]) for topic in topics)
        coverage_complete = assigned == len(trusted_records)
        if not coverage_complete:
            raise AppError(ErrorCode.TOPIC_DETECTION_FAILED, "Not every trusted screenshot could be assigned to a lecture section.", 422)

        progress(86.0, "Persisting ordered lecture topic groups...")
        self._write_jsonl_atomic(self._topics_path(video_id), topics)
        summary = {
            "video_id": video_id,
            "status": "READY",
            "pipeline_version": self.PIPELINE_VERSION,
            "topic_count": len(topics),
            "transcript_segment_count": len(segments),
            "trusted_screenshot_count": len(trusted_records),
            "assigned_screenshot_count": assigned,
            "unassigned_screenshot_count": len(trusted_records) - assigned,
            "coverage_complete": coverage_complete,
            "min_topic_duration_seconds": self.MIN_TOPIC_SECONDS,
            "max_topic_duration_seconds": self.MAX_TOPIC_SECONDS,
            "boundary_candidate_count": len(candidates),
            "accepted_boundary_count": len(boundaries),
            "transcript_generated_at": transcript["generated_at"],
            "alignment_generated_at": alignment["generated_at"],
            "trusted_generated_at": trusted["generated_at"],
            "generated_at": utc_now_iso(),
        }
        self._write_json_atomic(self._summary_path(video_id), summary)
        progress(100.0, f"Detected {len(topics):,} ordered lecture section(s).")
        return {"summary": summary, "topics": topics}
