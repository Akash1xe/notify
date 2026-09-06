from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Iterable

from app.core.errors import AppError, ErrorCode
from app.models.job import utc_now_iso
from app.services.candidate_review_service import CandidateReviewService
from app.services.ocr_service import OcrService
from app.services.storage_service import StorageService
from app.services.topic_detection_service import TopicDetectionService
from app.services.visual_change_service import VisualChangeService

ProgressCallback = Callable[[float, str], None]


class CoverageService:
    """Evidence-aware coverage audit.

    BLOCK is reserved for strong evidence loss. REVIEW marks suspicious but
    unconfirmed windows. WARNING is informational. Duplicate-suppressed or manually
    dismissed stable states are considered represented instead of creating repeated
    false-positive blockers.
    """

    PIPELINE_VERSION = 2
    NEARBY_SCREENSHOT_SECONDS = 8.0
    STRONG_STRUCTURAL_SCORE = 30.0
    LONG_GAP_SECONDS = 75.0
    SPEECH_DENSE_GAP_SECONDS = 45.0
    CLUSTER_SECONDS = 4.0
    STATE_CANDIDATE_TOLERANCE_SECONDS = 0.75

    def __init__(self, storage: StorageService, review: CandidateReviewService, topics: TopicDetectionService, ocr: OcrService, visual_changes: VisualChangeService) -> None:
        self.storage = storage
        self.review = review
        self.topics = topics
        self.ocr = ocr
        self.visual_changes = visual_changes

    def _findings_path(self, video_id: str) -> Path:
        return self.storage.analysis_dir(video_id) / "coverage-findings.jsonl"

    def _summary_path(self, video_id: str) -> Path:
        return self.storage.analysis_dir(video_id) / "coverage-summary.json"

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
    def _read_jsonl(path: Path) -> list[dict]:
        records: list[dict] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        value = json.loads(line)
                        if not isinstance(value, dict):
                            raise ValueError
                        records.append(value)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise AppError(ErrorCode.COVERAGE_AUDIT_FAILED, f"Coverage evidence is invalid: {path.name}.", 422) from exc
        return records

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
            raise AppError(ErrorCode.COVERAGE_AUDIT_FAILED, "Coverage summary could not be saved.", 500) from exc

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
            raise AppError(ErrorCode.COVERAGE_AUDIT_FAILED, "Coverage findings could not be saved.", 500) from exc

    @staticmethod
    def _nearest_distance(timestamp: float, values: list[float]) -> float | None:
        return min((abs(timestamp - value) for value in values), default=None)

    @staticmethod
    def _overlap(record: dict, start: float, end: float) -> bool:
        left = float(record.get("start_seconds", record.get("timestamp_seconds", 0.0)) or 0.0)
        right = float(record.get("end_seconds", record.get("timestamp_seconds", left)) or left)
        return right >= start and left <= end

    @staticmethod
    def _word_count(text: str) -> int:
        return len([item for item in text.strip().split() if item])

    def _inputs(self, video_id: str) -> dict:
        changes_summary = self.visual_changes.get_summary(video_id)
        review_result = self.review.get_review(video_id)
        topic_result = self.topics.get_result(video_id)
        ocr_result = self.ocr.get_result(video_id)
        if not changes_summary:
            raise AppError(ErrorCode.CHANGE_ANALYSIS_NOT_FOUND, "Visual-change analysis is required before coverage verification.", 409)
        if not topic_result:
            raise AppError(ErrorCode.TOPICS_NOT_FOUND, "Lecture topics are required before coverage verification.", 409)
        if not ocr_result:
            raise AppError(ErrorCode.OCR_RESULT_NOT_FOUND, "OCR enrichment is required before coverage verification.", 409)
        trusted_summary = review_result.get("summary")
        if not isinstance(trusted_summary, dict) or int(trusted_summary.get("selected_count") or 0) <= 0:
            raise AppError(ErrorCode.TRUSTED_SCREENSHOTS_NOT_FOUND, "A trusted screenshot set is required before coverage verification.", 409)
        analysis = self.storage.analysis_dir(video_id)
        required = {
            "changes": self.storage.frame_differences_path(video_id),
            "states": self.storage.teaching_states_path(video_id),
            "candidates": self.storage.screenshot_candidates_path(video_id),
            "trusted": analysis / "trusted-screenshots.jsonl",
            "transcript": self.storage.transcript_segments_path(video_id),
            "ocr": analysis / "screenshot-ocr.jsonl",
        }
        for path in required.values():
            if not path.exists():
                raise AppError(ErrorCode.COVERAGE_AUDIT_FAILED, f"Required coverage evidence is missing: {path.name}.", 409)
        return {
            "changes_summary": changes_summary,
            "trusted_summary": trusted_summary,
            "review_candidates": list(review_result.get("candidates") or []),
            "topic_result": topic_result,
            "ocr_result": ocr_result,
            **{name: self._read_jsonl(path) for name, path in required.items()},
        }

    @staticmethod
    def _cluster_strong_changes(records: list[dict], cluster_seconds: float) -> list[list[dict]]:
        strong = [record for record in records if str(record.get("kind") or "") == "SCENE" or (str(record.get("kind") or "") == "STRUCTURAL" and float(record.get("change_score") or 0.0) >= CoverageService.STRONG_STRUCTURAL_SCORE)]
        clusters: list[list[dict]] = []
        for record in strong:
            timestamp = float(record.get("timestamp_seconds") or 0.0)
            if not clusters or timestamp - float(clusters[-1][-1].get("timestamp_seconds") or 0.0) > cluster_seconds:
                clusters.append([record])
            else:
                clusters[-1].append(record)
        return clusters

    def _finding(self, findings: list[dict], severity: str, reasons: list[str], start: float, end: float, evidence: dict, blocking: bool) -> None:
        findings.append({
            "finding_index": len(findings),
            "severity": severity,
            "blocking": blocking,
            "start_seconds": round(max(0.0, start), 6),
            "end_seconds": round(max(start, end), 6),
            "reasons": reasons,
            "evidence": evidence,
            "rechecked": True,
        })

    def _state_resolution(self, timestamp: float, review_candidates: list[dict], trusted_indexes: set[int]) -> str:
        best: dict | None = None
        best_distance = float("inf")
        for candidate in review_candidates:
            distance = abs(float(candidate.get("timestamp_seconds") or 0.0) - timestamp)
            if distance < best_distance:
                best, best_distance = candidate, distance
        if best is None or best_distance > self.STATE_CANDIDATE_TOLERANCE_SECONDS:
            return "UNRESOLVED"
        candidate_index = int(best.get("candidate_index", -1))
        if candidate_index in trusted_indexes or bool(best.get("selected")):
            return "TRUSTED"
        if not bool(best.get("kept", True)):
            return "AUTO_DISMISSED_DUPLICATE"
        if best.get("manual_decision") is False:
            return "MANUALLY_DISMISSED"
        return "UNRESOLVED"

    def process(self, video_id: str, progress: ProgressCallback) -> dict:
        progress(2.0, "Loading complete lecture evidence...")
        inputs = self._inputs(video_id)
        trusted = inputs["trusted"]
        changes = inputs["changes"]
        states = inputs["states"]
        candidates = inputs["candidates"]
        transcript = inputs["transcript"]
        ocr_records = inputs["ocr"]
        review_candidates = inputs["review_candidates"]
        topics = list(inputs["topic_result"].get("topics") or [])
        trusted_times = [float(item.get("timestamp_seconds") or 0.0) for item in trusted]
        trusted_candidate_indexes = {int(item.get("candidate_index", -1)) for item in trusted}
        state_times = [float(item.get("timestamp_seconds") or 0.0) for item in states]
        duration = max([float(topic.get("end_seconds") or 0.0) for topic in topics] + [float(item.get("end_seconds") or 0.0) for item in transcript] + trusted_times + [0.0])
        findings: list[dict] = []

        progress(15.0, "Rechecking strong visual transitions...")
        for cluster in self._cluster_strong_changes(changes, self.CLUSTER_SECONDS):
            start = float(cluster[0].get("previous_timestamp_seconds", cluster[0].get("timestamp_seconds", 0.0)) or 0.0)
            end = float(cluster[-1].get("timestamp_seconds") or start)
            peak = max(float(item.get("change_score") or 0.0) for item in cluster)
            midpoint = (start + end) / 2.0
            screenshot_distance = self._nearest_distance(midpoint, trusted_times)
            if screenshot_distance is not None and screenshot_distance <= self.NEARBY_SCREENSHOT_SECONDS:
                continue
            nearby_states = [value for value in state_times if start - self.NEARBY_SCREENSHOT_SECONDS <= value <= end + self.NEARBY_SCREENSHOT_SECONDS]
            unresolved_states = [value for value in nearby_states if self._state_resolution(value, review_candidates, trusted_candidate_indexes) == "UNRESOLVED"]
            scene_count = sum(1 for item in cluster if str(item.get("kind") or "") == "SCENE")
            if nearby_states and not unresolved_states and scene_count == 0:
                continue
            reasons = ["UNCAPTURED_STRONG_VISUAL_CHANGE"]
            if unresolved_states:
                reasons.append("STABLE_STATE_NOT_IN_TRUSTED_SET")
            hard_block = scene_count > 0 and bool(unresolved_states)
            self._finding(findings, "HIGH" if hard_block else "REVIEW", reasons, start, end, {
                "scene_change_count": scene_count,
                "structural_change_count": len(cluster) - scene_count,
                "max_change_score": round(peak, 4),
                "nearest_trusted_screenshot_seconds": None if screenshot_distance is None else round(screenshot_distance, 4),
                "nearby_stable_state_timestamps": [round(value, 4) for value in nearby_states[:8]],
                "unresolved_stable_state_timestamps": [round(value, 4) for value in unresolved_states[:8]],
            }, blocking=hard_block)

        progress(35.0, "Checking protected and content-loss evidence...")
        for candidate in candidates:
            candidate_index = int(candidate.get("candidate_index", -1))
            protected = bool(candidate.get("protected")) or bool(candidate.get("content_loss_risk"))
            if protected and candidate_index not in trusted_candidate_indexes:
                self._finding(findings, "HIGH", ["PROTECTED_EVIDENCE_NOT_TRUSTED"], float(candidate.get("timestamp_seconds") or 0.0), float(candidate.get("timestamp_seconds") or 0.0), {
                    "candidate_index": candidate_index,
                    "reason": str(candidate.get("reason") or "UNKNOWN"),
                    "content_loss_risk": bool(candidate.get("content_loss_risk")),
                }, blocking=True)

        progress(50.0, "Auditing long screenshot gaps against speech and adaptive activity...")
        boundaries = [0.0] + trusted_times + ([duration] if duration > 0 else [])
        for left, right in zip(boundaries, boundaries[1:]):
            gap = right - left
            if gap < self.SPEECH_DENSE_GAP_SECONDS:
                continue
            speech = [item for item in transcript if self._overlap(item, left, right)]
            words = sum(self._word_count(str(item.get("text") or "")) for item in speech)
            visual = [item for item in changes if left <= float(item.get("timestamp_seconds") or 0.0) <= right and str(item.get("kind") or "") != "NONE"]
            stable = [value for value in state_times if left < value < right]
            unresolved = [value for value in stable if self._state_resolution(value, review_candidates, trusted_candidate_indexes) == "UNRESOLVED"]
            if gap < self.LONG_GAP_SECONDS and words < 90 and len(visual) < 30:
                continue
            if not unresolved:
                continue
            reasons = ["LONG_TRUSTED_SCREENSHOT_GAP"]
            if words >= 90:
                reasons.append("SPEECH_DENSE_GAP")
            reasons.append("UNUSED_STABLE_STATE_IN_GAP")
            self._finding(findings, "REVIEW", reasons, left, right, {
                "gap_seconds": round(gap, 3),
                "transcript_segment_count": len(speech),
                "transcript_word_count": words,
                "visual_change_count": len(visual),
                "stable_state_count": len(stable),
                "unresolved_stable_state_count": len(unresolved),
            }, blocking=False)

        progress(68.0, "Checking topic screenshot coverage...")
        for topic in topics:
            if int(topic.get("screenshot_count") or 0) <= 0:
                self._finding(findings, "HIGH", ["TOPIC_WITHOUT_TRUSTED_SCREENSHOT"], float(topic.get("start_seconds") or 0.0), float(topic.get("end_seconds") or 0.0), {
                    "topic_index": int(topic.get("topic_index") or 0),
                    "title": str(topic.get("title") or "Lecture section"),
                    "segment_count": int(topic.get("segment_count") or 0),
                    "word_count": int(topic.get("word_count") or 0),
                }, blocking=True)

        progress(80.0, "Recording OCR uncertainty warnings...")
        for record in ocr_records:
            has_text, low_confidence = bool(record.get("has_text")), bool(record.get("low_confidence"))
            if has_text and not low_confidence:
                continue
            trusted_index = int(record.get("trusted_index") or 0)
            if trusted_index < 0 or trusted_index >= len(trusted):
                raise AppError(ErrorCode.COVERAGE_AUDIT_FAILED, "OCR coverage no longer matches the trusted screenshot set.", 422)
            timestamp = float(trusted[trusted_index].get("timestamp_seconds") or 0.0)
            self._finding(findings, "WARNING", ["OCR_NO_TEXT" if not has_text else "OCR_LOW_CONFIDENCE"], timestamp, timestamp, {
                "trusted_index": trusted_index,
                "mean_confidence": float(record.get("mean_confidence") or 0.0),
                "word_count": int(record.get("word_count") or 0),
            }, blocking=False)

        progress(92.0, "Finalizing coverage decision...")
        blocking = [item for item in findings if bool(item["blocking"])]
        reviews = [item for item in findings if item["severity"] == "REVIEW"]
        warnings = [item for item in findings if item["severity"] == "WARNING"]
        ready_for_pdf = len(blocking) == 0
        summary = {
            "video_id": video_id,
            "status": "READY",
            "pipeline_version": self.PIPELINE_VERSION,
            "coverage_passed": ready_for_pdf,
            "ready_for_pdf": ready_for_pdf,
            "pdf_status": "BLOCKED" if blocking else ("REVIEW" if reviews else "READY"),
            "finding_count": len(findings),
            "blocking_finding_count": len(blocking),
            "review_finding_count": len(reviews),
            "high_severity_count": sum(1 for item in findings if item["severity"] == "HIGH"),
            "medium_severity_count": sum(1 for item in findings if item["severity"] == "MEDIUM"),
            "warning_count": len(warnings),
            "rechecked_window_count": len(findings),
            "trusted_screenshot_count": len(trusted),
            "topic_count": len(topics),
            "visual_pair_count": int(inputs["changes_summary"].get("compared_pair_count") or 0),
            "ocr_record_count": len(ocr_records),
            "audit_config": {
                "nearby_screenshot_seconds": self.NEARBY_SCREENSHOT_SECONDS,
                "strong_structural_score": self.STRONG_STRUCTURAL_SCORE,
                "long_gap_seconds": self.LONG_GAP_SECONDS,
                "speech_dense_gap_seconds": self.SPEECH_DENSE_GAP_SECONDS,
            },
            "source_versions": {
                "visual_changes_generated_at": inputs["changes_summary"].get("generated_at"),
                "trusted_generated_at": inputs["trusted_summary"].get("generated_at"),
                "topics_generated_at": (inputs["topic_result"].get("summary") or {}).get("generated_at"),
                "ocr_generated_at": ((inputs["ocr_result"].get("ocr") or {}).get("generated_at")),
                "content_generated_at": ((inputs["ocr_result"].get("content") or {}).get("generated_at")),
            },
            "generated_at": utc_now_iso(),
        }
        self._write_jsonl_atomic(self._findings_path(video_id), findings)
        self._write_json_atomic(self._summary_path(video_id), summary)
        progress(100.0, "Coverage audit complete." if ready_for_pdf else "Coverage audit found confirmed blocking evidence.")
        return {"summary": summary, "findings": findings}

    def get_result(self, video_id: str) -> dict | None:
        try:
            inputs = self._inputs(video_id)
        except AppError:
            return None
        summary = self._read_json(self._summary_path(video_id))
        findings_path = self._findings_path(video_id)
        if not summary or not findings_path.exists():
            return None
        if summary.get("video_id") != video_id or int(summary.get("pipeline_version") or 0) != self.PIPELINE_VERSION:
            return None
        expected = {
            "visual_changes_generated_at": inputs["changes_summary"].get("generated_at"),
            "trusted_generated_at": inputs["trusted_summary"].get("generated_at"),
            "topics_generated_at": (inputs["topic_result"].get("summary") or {}).get("generated_at"),
            "ocr_generated_at": ((inputs["ocr_result"].get("ocr") or {}).get("generated_at")),
            "content_generated_at": ((inputs["ocr_result"].get("content") or {}).get("generated_at")),
        }
        if summary.get("source_versions") != expected:
            return None
        findings = self._read_jsonl(findings_path)
        if len(findings) != int(summary.get("finding_count") or 0):
            return None
        return {"summary": summary, "findings": findings}
