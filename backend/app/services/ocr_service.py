from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable

import cv2

from app.core.errors import AppError, ErrorCode
from app.models.job import utc_now_iso
from app.services.candidate_review_service import CandidateReviewService
from app.services.storage_service import StorageService
from app.services.topic_detection_service import TopicDetectionService

ProgressCallback = Callable[[str, float, str], None]
OcrRunner = Callable[[Path], dict]


class OcrService:
    PIPELINE_VERSION = 1
    LOW_CONFIDENCE_THRESHOLD = 55.0
    STOPWORDS = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have", "in", "is",
        "it", "of", "on", "or", "that", "the", "this", "to", "was", "we", "will", "with", "you", "your",
        "can", "now", "let", "use", "using", "then", "than", "if", "else", "when", "where", "which",
    }

    def __init__(
        self,
        storage: StorageService,
        review: CandidateReviewService,
        topics: TopicDetectionService,
        tesseract_cmd: str | None = None,
        language: str = "eng",
        psm: int = 11,
        runner: OcrRunner | None = None,
    ) -> None:
        self.storage = storage
        self.review = review
        self.topics = topics
        self.language = language or "eng"
        self.psm = int(psm)
        self.tesseract_cmd = self._resolve_tesseract(tesseract_cmd)
        self._runner = runner or self._run_tesseract
        self._version: str | None = None

    @staticmethod
    def _resolve_tesseract(command: str | None) -> str | None:
        value = (command or "tesseract").strip()
        discovered = shutil.which(value)
        if discovered:
            return discovered
        try:
            path = Path(value).expanduser()
            return str(path.resolve()) if path.is_file() else None
        except OSError:
            return None

    @property
    def available(self) -> bool:
        return self.tesseract_cmd is not None

    def engine_version(self) -> str:
        if self._version is not None:
            return self._version
        if not self.tesseract_cmd:
            self._version = "unavailable"
            return self._version
        try:
            completed = subprocess.run(
                [self.tesseract_cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            first = (completed.stdout or completed.stderr or "").splitlines()
            self._version = first[0].strip() if first else "tesseract"
        except (OSError, subprocess.SubprocessError):
            self._version = "tesseract"
        return self._version

    def _ocr_path(self, video_id: str) -> Path:
        return self.storage.analysis_dir(video_id) / "screenshot-ocr.jsonl"

    def _ocr_summary_path(self, video_id: str) -> Path:
        return self.storage.analysis_dir(video_id) / "screenshot-ocr-summary.json"

    def _content_path(self, video_id: str) -> Path:
        return self.storage.analysis_dir(video_id) / "screenshot-content.jsonl"

    def _content_summary_path(self, video_id: str) -> Path:
        return self.storage.analysis_dir(video_id) / "screenshot-content-summary.json"

    def _topic_content_path(self, video_id: str) -> Path:
        return self.storage.analysis_dir(video_id) / "topic-content.jsonl"

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return payload if isinstance(payload, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _atomic_json_write(path: Path, payload: dict) -> None:
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
            raise AppError(ErrorCode.OCR_FAILED, "OCR metadata could not be saved.", 500) from exc

    @staticmethod
    def _write_jsonl_atomic(path: Path, records: Iterable[dict], message: str) -> None:
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
            raise AppError(ErrorCode.OCR_FAILED, message, 500) from exc

    @staticmethod
    def _read_jsonl(path: Path, index_key: str, expected_count: int, message: str) -> list[dict]:
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
            raise AppError(ErrorCode.OCR_FAILED, message, 422) from exc
        if len(records) != expected_count:
            raise AppError(ErrorCode.OCR_FAILED, message, 422)
        return records

    @staticmethod
    def _trusted_manifest_path(storage: StorageService, video_id: str) -> Path:
        return storage.analysis_dir(video_id) / "trusted-screenshots.jsonl"

    @staticmethod
    def _trusted_dir(storage: StorageService, video_id: str) -> Path:
        return storage.analysis_dir(video_id) / "trusted-screenshots"

    @classmethod
    def _tokens(cls, text: str) -> list[str]:
        return [
            token
            for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_+#.-]{2,}", text.lower())
            if token not in cls.STOPWORDS
        ]

    @staticmethod
    def _prepare_for_tesseract(image_path: Path) -> Path:
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise AppError(ErrorCode.OCR_FAILED, "A trusted screenshot could not be decoded for OCR.", 422)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if float(gray.mean()) < 118.0:
            gray = cv2.bitwise_not(gray)
        height, width = gray.shape[:2]
        if width < 1600:
            scale = min(2.0, max(1.0, 1600.0 / max(1, width)))
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        gray = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8)).apply(gray)
        handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        path = Path(handle.name)
        handle.close()
        if not cv2.imwrite(str(path), gray):
            path.unlink(missing_ok=True)
            raise AppError(ErrorCode.OCR_FAILED, "A temporary OCR image could not be created.", 500)
        return path

    @staticmethod
    def _parse_tsv(payload: str) -> dict:
        lines: dict[tuple[str, str, str, str], dict] = {}
        valid_confidences: list[float] = []
        word_count = 0
        try:
            reader = csv.DictReader(io.StringIO(payload), delimiter="\t")
            for row in reader:
                text = str(row.get("text") or "").strip()
                if not text:
                    continue
                try:
                    confidence = float(row.get("conf") or -1)
                    left = int(float(row.get("left") or 0))
                    top = int(float(row.get("top") or 0))
                    width = int(float(row.get("width") or 0))
                    height = int(float(row.get("height") or 0))
                except (TypeError, ValueError):
                    continue
                key = (
                    str(row.get("page_num") or "0"),
                    str(row.get("block_num") or "0"),
                    str(row.get("par_num") or "0"),
                    str(row.get("line_num") or "0"),
                )
                current = lines.setdefault(
                    key,
                    {
                        "words": [],
                        "confidences": [],
                        "left": left,
                        "top": top,
                        "right": left + width,
                        "bottom": top + height,
                    },
                )
                current["words"].append(text)
                if confidence >= 0:
                    current["confidences"].append(confidence)
                    valid_confidences.append(confidence)
                current["left"] = min(current["left"], left)
                current["top"] = min(current["top"], top)
                current["right"] = max(current["right"], left + width)
                current["bottom"] = max(current["bottom"], top + height)
                word_count += 1
        except csv.Error as exc:
            raise AppError(ErrorCode.OCR_FAILED, "Tesseract returned malformed OCR data.", 500) from exc

        line_records: list[dict] = []
        for item in lines.values():
            text = " ".join(item["words"]).strip()
            confidences = item["confidences"]
            confidence = sum(confidences) / len(confidences) if confidences else 0.0
            line_records.append(
                {
                    "text": text,
                    "confidence": round(confidence, 3),
                    "bbox": [
                        int(item["left"]),
                        int(item["top"]),
                        int(item["right"] - item["left"]),
                        int(item["bottom"] - item["top"]),
                    ],
                }
            )
        text = "\n".join(item["text"] for item in line_records if item["text"]).strip()
        mean_confidence = sum(valid_confidences) / len(valid_confidences) if valid_confidences else 0.0
        return {
            "text": text,
            "lines": line_records,
            "line_count": len(line_records),
            "word_count": word_count,
            "mean_confidence": round(mean_confidence, 3),
            "has_text": bool(text),
        }

    def _run_tesseract(self, image_path: Path) -> dict:
        if not self.tesseract_cmd:
            raise AppError(
                ErrorCode.OCR_ENGINE_UNAVAILABLE,
                "Tesseract OCR was not detected. Install Tesseract 5, add it to PATH, or configure TESSERACT_CMD.",
                503,
            )
        prepared = self._prepare_for_tesseract(image_path)
        try:
            completed = subprocess.run(
                [
                    self.tesseract_cmd,
                    str(prepared),
                    "stdout",
                    "-l",
                    self.language,
                    "--oem",
                    "1",
                    "--psm",
                    str(self.psm),
                    "tsv",
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AppError(ErrorCode.OCR_FAILED, "Tesseract could not process a trusted screenshot.", 500) from exc
        finally:
            prepared.unlink(missing_ok=True)
        if completed.returncode != 0:
            message = (completed.stderr or "").strip()
            if "failed loading language" in message.lower() or "error opening data file" in message.lower():
                raise AppError(
                    ErrorCode.OCR_ENGINE_UNAVAILABLE,
                    f"Tesseract language data '{self.language}' is not available.",
                    503,
                )
            raise AppError(ErrorCode.OCR_FAILED, "Tesseract could not process a trusted screenshot.", 500)
        return self._parse_tsv(completed.stdout)

    def _trusted_inputs(self, video_id: str) -> tuple[dict, list[dict]]:
        review = self.review.get_review(video_id)
        summary = review.get("summary")
        if not isinstance(summary, dict):
            raise AppError(ErrorCode.TRUSTED_SCREENSHOTS_NOT_FOUND, "Review screenshot candidates before OCR enrichment.", 409)
        count = int(summary.get("selected_count") or 0)
        if count <= 0:
            raise AppError(ErrorCode.TRUSTED_SCREENSHOTS_NOT_FOUND, "No trusted screenshots are available for OCR enrichment.", 409)
        records = self._read_jsonl(
            self._trusted_manifest_path(self.storage, video_id),
            "trusted_index",
            count,
            "The trusted screenshot manifest is invalid.",
        )
        directory = self._trusted_dir(self.storage, video_id)
        for record in records:
            filename = str(record.get("image_filename") or "")
            if not filename or not (directory / filename).is_file():
                raise AppError(ErrorCode.TRUSTED_SCREENSHOTS_NOT_FOUND, "A trusted screenshot image is missing.", 422)
        return summary, records

    def _valid_ocr_summary(self, video_id: str, trusted: dict) -> dict | None:
        summary = self._read_json(self._ocr_summary_path(video_id))
        path = self._ocr_path(video_id)
        if not summary or not path.exists():
            return None
        if summary.get("video_id") != video_id or int(summary.get("pipeline_version") or 0) != self.PIPELINE_VERSION:
            return None
        if summary.get("trusted_generated_at") != trusted.get("generated_at"):
            return None
        if int(summary.get("trusted_screenshot_count") or -1) != int(trusted.get("selected_count") or 0):
            return None
        if summary.get("language") != self.language or int(summary.get("psm") or -1) != self.psm:
            return None
        try:
            self._read_jsonl(path, "trusted_index", int(trusted.get("selected_count") or 0), "Persisted OCR coverage is invalid.")
        except AppError:
            return None
        return summary

    def _run_ocr(self, video_id: str, trusted: dict, records: list[dict], progress: ProgressCallback) -> dict:
        if not self.available and self._runner == self._run_tesseract:
            raise AppError(
                ErrorCode.OCR_ENGINE_UNAVAILABLE,
                "Tesseract OCR was not detected. Install Tesseract 5, add it to PATH, or configure TESSERACT_CMD.",
                503,
            )
        directory = self._trusted_dir(self.storage, video_id)
        output: list[dict] = []
        detected_count = 0
        low_confidence_count = 0
        total_words = 0
        confidence_values: list[float] = []
        count = len(records)
        for index, record in enumerate(records):
            image_path = directory / str(record["image_filename"])
            result = self._runner(image_path)
            text = str(result.get("text") or "").strip()
            has_text = bool(result.get("has_text", bool(text)))
            confidence = float(result.get("mean_confidence") or 0.0)
            word_count = int(result.get("word_count") or 0)
            lines = result.get("lines") if isinstance(result.get("lines"), list) else []
            low_confidence = has_text and confidence < self.LOW_CONFIDENCE_THRESHOLD
            detected_count += int(has_text)
            low_confidence_count += int(low_confidence)
            total_words += word_count
            if has_text:
                confidence_values.append(confidence)
            output.append(
                {
                    "trusted_index": int(record["trusted_index"]),
                    "candidate_index": int(record["candidate_index"]),
                    "frame_index": int(record["frame_index"]),
                    "timestamp_seconds": float(record["timestamp_seconds"]),
                    "text": text,
                    "lines": lines,
                    "line_count": int(result.get("line_count") or len(lines)),
                    "word_count": word_count,
                    "mean_confidence": round(confidence, 3),
                    "has_text": has_text,
                    "low_confidence": low_confidence,
                }
            )
            pct = 4.0 + ((index + 1) / max(1, count)) * 74.0
            progress("OCR", pct, f"Reading visible text from screenshot {index + 1:,}/{count:,}...")

        self._write_jsonl_atomic(self._ocr_path(video_id), output, "Screenshot OCR records could not be saved.")
        summary = {
            "video_id": video_id,
            "status": "READY",
            "pipeline_version": self.PIPELINE_VERSION,
            "engine": "tesseract",
            "engine_version": self.engine_version() if self.available else "injected-test-engine",
            "language": self.language,
            "psm": self.psm,
            "trusted_screenshot_count": count,
            "processed_screenshot_count": len(output),
            "text_detected_count": detected_count,
            "no_text_count": len(output) - detected_count,
            "low_confidence_count": low_confidence_count,
            "total_word_count": total_words,
            "average_confidence": round(sum(confidence_values) / len(confidence_values), 3) if confidence_values else 0.0,
            "coverage_complete": len(output) == count,
            "trusted_generated_at": trusted["generated_at"],
            "generated_at": utc_now_iso(),
        }
        self._atomic_json_write(self._ocr_summary_path(video_id), summary)
        progress("OCR", 80.0, f"OCR complete for all {len(output):,} trusted screenshots.")
        return summary

    def _valid_content_summary(self, video_id: str, ocr: dict, topic_result: dict, trusted: dict) -> dict | None:
        summary = self._read_json(self._content_summary_path(video_id))
        if not summary or not self._content_path(video_id).exists() or not self._topic_content_path(video_id).exists():
            return None
        topic_summary = topic_result.get("summary") or {}
        if summary.get("video_id") != video_id:
            return None
        if summary.get("ocr_generated_at") != ocr.get("generated_at"):
            return None
        if summary.get("topics_generated_at") != topic_summary.get("generated_at"):
            return None
        if summary.get("trusted_generated_at") != trusted.get("generated_at"):
            return None
        if int(summary.get("enriched_screenshot_count") or -1) != int(trusted.get("selected_count") or 0):
            return None
        return summary

    def _load_alignment(self, video_id: str, expected_count: int) -> list[dict]:
        return self._read_jsonl(
            self.storage.screenshot_transcript_map_path(video_id),
            "trusted_index",
            expected_count,
            "Screenshot-to-transcript alignment is invalid.",
        )

    def _enrich(self, video_id: str, ocr_summary: dict, trusted: dict, topic_result: dict, progress: ProgressCallback) -> tuple[dict, list[dict]]:
        progress("ENRICH", 83.0, "Combining visible text, nearby speech, and lecture topics...")
        count = int(trusted.get("selected_count") or 0)
        ocr_records = self._read_jsonl(self._ocr_path(video_id), "trusted_index", count, "Persisted OCR coverage is invalid.")
        alignment = self._load_alignment(video_id, count)
        topics = topic_result.get("topics")
        if not isinstance(topics, list) or not topics:
            raise AppError(ErrorCode.OCR_ENRICHMENT_FAILED, "Lecture topics are not available for screenshot enrichment.", 409)

        topic_for_index: dict[int, dict] = {}
        for topic in topics:
            if not isinstance(topic, dict):
                raise AppError(ErrorCode.OCR_ENRICHMENT_FAILED, "Lecture topic data is invalid.", 422)
            for trusted_index in topic.get("trusted_screenshot_indexes") or []:
                index = int(trusted_index)
                if index in topic_for_index:
                    raise AppError(ErrorCode.OCR_ENRICHMENT_FAILED, "A trusted screenshot belongs to more than one lecture topic.", 422)
                topic_for_index[index] = topic

        enriched: list[dict] = []
        topic_visual_tokens: dict[int, Counter[str]] = {int(topic["topic_index"]): Counter() for topic in topics}
        topic_text_counts: dict[int, int] = {int(topic["topic_index"]): 0 for topic in topics}
        topic_ocr_words: dict[int, int] = {int(topic["topic_index"]): 0 for topic in topics}

        for index, (ocr, speech) in enumerate(zip(ocr_records, alignment)):
            trusted_index = int(ocr["trusted_index"])
            if int(speech["trusted_index"]) != trusted_index:
                raise AppError(ErrorCode.OCR_ENRICHMENT_FAILED, "OCR and transcript alignment indexes do not match.", 422)
            topic = topic_for_index.get(trusted_index)
            if topic is None:
                raise AppError(ErrorCode.OCR_ENRICHMENT_FAILED, "A trusted screenshot was not assigned to a lecture topic.", 422)
            topic_index = int(topic["topic_index"])
            visible_text = str(ocr.get("text") or "").strip()
            speech_text = str(speech.get("text") or "").strip()
            combined = "\n\n".join(value for value in (visible_text, speech_text) if value).strip()
            flags: list[str] = []
            if not bool(ocr.get("has_text")):
                flags.append("OCR_NO_TEXT")
            elif bool(ocr.get("low_confidence")):
                flags.append("OCR_LOW_CONFIDENCE")
            if not speech_text:
                flags.append("NO_NEARBY_SPEECH")
            if visible_text:
                topic_text_counts[topic_index] += 1
                topic_ocr_words[topic_index] += int(ocr.get("word_count") or 0)
                topic_visual_tokens[topic_index].update(self._tokens(visible_text))
            enriched.append(
                {
                    "trusted_index": trusted_index,
                    "candidate_index": int(ocr["candidate_index"]),
                    "frame_index": int(ocr["frame_index"]),
                    "timestamp_seconds": float(ocr["timestamp_seconds"]),
                    "topic_index": topic_index,
                    "topic_title": str(topic.get("title") or f"Lecture Section {topic_index + 1}"),
                    "visible_text": visible_text,
                    "nearby_speech": speech_text,
                    "combined_context": combined,
                    "ocr_mean_confidence": float(ocr.get("mean_confidence") or 0.0),
                    "ocr_word_count": int(ocr.get("word_count") or 0),
                    "coverage_flags": flags,
                }
            )
            pct = 83.0 + ((index + 1) / max(1, count)) * 12.0
            progress("ENRICH", pct, f"Enriching screenshot context {index + 1:,}/{count:,}...")

        topic_records: list[dict] = []
        for topic in topics:
            topic_index = int(topic["topic_index"])
            topic_records.append(
                {
                    "topic_index": topic_index,
                    "title": str(topic.get("title") or f"Lecture Section {topic_index + 1}"),
                    "screenshot_count": int(topic.get("screenshot_count") or 0),
                    "screenshots_with_ocr_text": topic_text_counts[topic_index],
                    "ocr_word_count": topic_ocr_words[topic_index],
                    "visual_keywords": [word for word, _ in topic_visual_tokens[topic_index].most_common(8)],
                }
            )

        self._write_jsonl_atomic(self._content_path(video_id), enriched, "Enriched screenshot content could not be saved.")
        self._write_jsonl_atomic(self._topic_content_path(video_id), topic_records, "Topic OCR enrichment could not be saved.")
        topic_summary = topic_result["summary"]
        content_summary = {
            "video_id": video_id,
            "status": "READY",
            "pipeline_version": self.PIPELINE_VERSION,
            "topic_count": len(topic_records),
            "trusted_screenshot_count": count,
            "enriched_screenshot_count": len(enriched),
            "screenshots_with_visible_text": int(ocr_summary.get("text_detected_count") or 0),
            "screenshots_without_visible_text": int(ocr_summary.get("no_text_count") or 0),
            "screenshots_with_low_confidence_text": int(ocr_summary.get("low_confidence_count") or 0),
            "coverage_complete": len(enriched) == count and len(topic_for_index) == count,
            "ocr_generated_at": ocr_summary["generated_at"],
            "topics_generated_at": topic_summary["generated_at"],
            "alignment_generated_at": topic_summary["alignment_generated_at"],
            "trusted_generated_at": trusted["generated_at"],
            "generated_at": utc_now_iso(),
        }
        if not content_summary["coverage_complete"]:
            raise AppError(ErrorCode.OCR_ENRICHMENT_FAILED, "Screenshot content enrichment did not cover every trusted screenshot.", 422)
        self._atomic_json_write(self._content_summary_path(video_id), content_summary)
        progress("ENRICH", 100.0, f"Visible text and lecture context enriched for all {len(enriched):,} trusted screenshots.")
        return content_summary, topic_records

    def get_result(self, video_id: str) -> dict | None:
        try:
            trusted, _ = self._trusted_inputs(video_id)
        except AppError:
            return None
        topic_result = self.topics.get_result(video_id)
        if not topic_result:
            return None
        ocr = self._valid_ocr_summary(video_id, trusted)
        if not ocr:
            return None
        content = self._valid_content_summary(video_id, ocr, topic_result, trusted)
        if not content:
            return None
        try:
            topic_content = self._read_jsonl(
                self._topic_content_path(video_id),
                "topic_index",
                int(content.get("topic_count") or 0),
                "Persisted topic OCR enrichment is invalid.",
            )
        except AppError:
            return None
        return {"ocr": ocr, "content": content, "topics": topic_content}

    def process(self, video_id: str, progress: ProgressCallback) -> dict:
        trusted, records = self._trusted_inputs(video_id)
        topic_result = self.topics.get_result(video_id)
        if not topic_result:
            raise AppError(ErrorCode.TOPICS_NOT_FOUND, "Detect lecture topics before OCR enrichment.", 409)

        ocr = self._valid_ocr_summary(video_id, trusted)
        if ocr:
            progress("OCR", 80.0, "Reusing cached OCR for the unchanged trusted screenshot set.")
        else:
            ocr = self._run_ocr(video_id, trusted, records, progress)

        content = self._valid_content_summary(video_id, ocr, topic_result, trusted)
        if content:
            progress("ENRICH", 100.0, "Screenshot OCR enrichment already exists and is valid.")
            topic_records = self._read_jsonl(
                self._topic_content_path(video_id),
                "topic_index",
                int(content.get("topic_count") or 0),
                "Persisted topic OCR enrichment is invalid.",
            )
        else:
            content, topic_records = self._enrich(video_id, ocr, trusted, topic_result, progress)
        return {"ocr": ocr, "content": content, "topics": topic_records}
