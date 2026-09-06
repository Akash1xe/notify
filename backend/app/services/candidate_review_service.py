from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import cv2

from app.core.errors import AppError, ErrorCode
from app.models.job import utc_now_iso
from app.services.prepared_video_service import PreparedVideoService
from app.services.screenshot_candidate_service import ScreenshotCandidateService
from app.services.storage_service import StorageService


class CandidateReviewService:
    def __init__(
        self,
        storage: StorageService,
        prepared: PreparedVideoService,
        candidates: ScreenshotCandidateService,
    ) -> None:
        self.storage = storage
        self.prepared = prepared
        self.candidates = candidates

    def _review_path(self, video_id: str) -> Path:
        return self.storage.analysis_dir(video_id) / "candidate-review.json"

    def _trusted_manifest_path(self, video_id: str) -> Path:
        return self.storage.analysis_dir(video_id) / "trusted-screenshots.jsonl"

    def _trusted_summary_path(self, video_id: str) -> Path:
        return self.storage.analysis_dir(video_id) / "trusted-screenshots-summary.json"

    def _trusted_dir(self, video_id: str) -> Path:
        return self.storage._assert_within(
            self.storage.analysis_dir(video_id) / "trusted-screenshots",
            self.storage.analysis_dir(video_id),
        )

    def _atomic_json_write(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise AppError(ErrorCode.CANDIDATE_REVIEW_FAILED, "Candidate review state could not be saved.", 500) from exc

    def _read_json(self, path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return payload if isinstance(payload, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    def _candidate_records(self, video_id: str) -> tuple[dict, list[dict]]:
        summary = self.candidates.get_summary(video_id)
        if not summary:
            raise AppError(ErrorCode.SCREENSHOT_CANDIDATES_NOT_FOUND, "Generate screenshot candidates before reviewing them.", 409)

        path = self.storage.screenshot_candidates_path(video_id)
        records: list[dict] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise ValueError
                    candidate_index = int(record["candidate_index"])
                    frame_index = int(record["frame_index"])
                    if candidate_index != len(records) or frame_index < 0:
                        raise ValueError
                    records.append(record)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise AppError(ErrorCode.CANDIDATE_REVIEW_FAILED, "The screenshot candidate manifest is invalid.", 422) from exc

        if len(records) != int(summary.get("source_checkpoint_count") or -1):
            raise AppError(ErrorCode.CANDIDATE_REVIEW_FAILED, "Screenshot candidate coverage does not match its summary.", 422)
        return summary, records

    @staticmethod
    def _auto_protected(record: dict) -> bool:
        return bool(record.get("protected")) or bool(record.get("content_loss_risk"))

    @classmethod
    def _default_selected(cls, record: dict) -> bool:
        return bool(record.get("kept")) or cls._auto_protected(record)

    def _review_state(self, video_id: str, candidate_summary: dict) -> dict:
        path = self._review_path(video_id)
        state = self._read_json(path)
        generated_at = str(candidate_summary["generated_at"])
        if (
            not state
            or state.get("video_id") != video_id
            or state.get("candidates_generated_at") != generated_at
            or not isinstance(state.get("decisions"), dict)
        ):
            state = {
                "video_id": video_id,
                "candidates_generated_at": generated_at,
                "decisions": {},
                "updated_at": utc_now_iso(),
            }
            self._atomic_json_write(path, state)
        return state

    def _merged_records(self, records: list[dict], state: dict) -> list[dict]:
        decisions = state.get("decisions") or {}
        merged: list[dict] = []
        for record in records:
            candidate_index = int(record["candidate_index"])
            manual = decisions.get(str(candidate_index))
            default_selected = self._default_selected(record)
            selected = bool(manual) if isinstance(manual, bool) else default_selected
            merged.append(
                {
                    **record,
                    "auto_protected": self._auto_protected(record),
                    "default_selected": default_selected,
                    "manual_decision": manual if isinstance(manual, bool) else None,
                    "selected": selected,
                }
            )
        return merged

    def _preview_bytes_for_record(self, video_id: str, record: dict) -> bytes:
        filename = record.get("image_filename")
        if isinstance(filename, str) and filename:
            source = self.storage.screenshot_candidates_dir(video_id) / filename
            try:
                if source.exists():
                    return source.read_bytes()
            except OSError as exc:
                raise AppError(ErrorCode.CANDIDATE_REVIEW_FAILED, "A retained screenshot could not be read.", 500) from exc

        prepared = self.prepared.get_prepared_video(video_id)
        if not prepared:
            raise AppError(ErrorCode.VIDEO_NOT_PREPARED, "The prepared lecture is no longer available.", 409)
        capture = cv2.VideoCapture(str(prepared.local_video_path))
        if not capture.isOpened():
            raise AppError(ErrorCode.VIDEO_READER_FAILED, "The lecture could not be opened to restore this screenshot.", 422)
        try:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(record["frame_index"]))
            ok, frame = capture.read()
            if not ok or frame is None:
                raise AppError(ErrorCode.CANDIDATE_REVIEW_FAILED, "The requested screenshot frame could not be restored.", 422)
            ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
            if not ok:
                raise AppError(ErrorCode.CANDIDATE_REVIEW_FAILED, "The requested screenshot frame could not be encoded.", 500)
            return encoded.tobytes()
        finally:
            capture.release()

    def preview_bytes(self, video_id: str, candidate_index: int) -> bytes:
        _, records = self._candidate_records(video_id)
        if candidate_index < 0 or candidate_index >= len(records):
            raise AppError(ErrorCode.CANDIDATE_NOT_FOUND, "The requested screenshot candidate was not found.", 404)
        return self._preview_bytes_for_record(video_id, records[candidate_index])

    def _trusted_cache_valid(self, video_id: str, state: dict, candidate_summary: dict) -> dict | None:
        summary = self._read_json(self._trusted_summary_path(video_id))
        manifest = self._trusted_manifest_path(video_id)
        directory = self._trusted_dir(video_id)
        if not summary or not manifest.exists() or not directory.exists():
            return None
        if summary.get("candidates_generated_at") != candidate_summary.get("generated_at"):
            return None
        if summary.get("review_updated_at") != state.get("updated_at"):
            return None
        selected_count = int(summary.get("selected_count") or 0)
        try:
            image_count = sum(1 for item in directory.iterdir() if item.is_file() and item.suffix.lower() == ".jpg")
        except OSError:
            return None
        return summary if image_count == selected_count else None

    def _rebuild_trusted(self, video_id: str, merged: list[dict], state: dict, candidate_summary: dict) -> dict:
        selected = [record for record in merged if bool(record["selected"])]
        final_dir = self._trusted_dir(video_id)
        temp_dir = final_dir.with_name(final_dir.name + ".tmp")
        final_manifest = self._trusted_manifest_path(video_id)
        temp_manifest = final_manifest.with_suffix(".jsonl.tmp")
        temp_manifest.unlink(missing_ok=True)
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

        manual_keep_count = 0
        manual_suppress_count = sum(1 for record in merged if record.get("manual_decision") is False)
        auto_protected_count = sum(1 for record in selected if bool(record.get("auto_protected")))
        restored_suppressed_count = 0

        try:
            with temp_manifest.open("w", encoding="utf-8") as manifest:
                for trusted_index, record in enumerate(selected):
                    if record.get("manual_decision") is True:
                        manual_keep_count += 1
                    if not bool(record.get("kept")):
                        restored_suppressed_count += 1

                    filename = f"trusted-{trusted_index:06d}.jpg"
                    source_name = record.get("image_filename")
                    source_path = (
                        self.storage.screenshot_candidates_dir(video_id) / source_name
                        if isinstance(source_name, str) and source_name
                        else None
                    )
                    if source_path is not None and source_path.exists():
                        shutil.copy2(source_path, temp_dir / filename)
                    else:
                        (temp_dir / filename).write_bytes(self._preview_bytes_for_record(video_id, record))

                    manifest.write(
                        json.dumps(
                            {
                                "trusted_index": trusted_index,
                                "candidate_index": int(record["candidate_index"]),
                                "frame_index": int(record["frame_index"]),
                                "timestamp_seconds": float(record["timestamp_seconds"]),
                                "reason": str(record.get("reason") or "UNKNOWN"),
                                "auto_protected": bool(record.get("auto_protected")),
                                "content_loss_risk": bool(record.get("content_loss_risk")),
                                "manual_decision": record.get("manual_decision"),
                                "image_filename": filename,
                            },
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
                manifest.flush()
                os.fsync(manifest.fileno())

            if final_dir.exists():
                shutil.rmtree(final_dir)
            os.replace(temp_dir, final_dir)
            os.replace(temp_manifest, final_manifest)
            summary = {
                "video_id": video_id,
                "status": "READY",
                "candidate_count": len(merged),
                "selected_count": len(selected),
                "manual_keep_count": manual_keep_count,
                "manual_suppress_count": manual_suppress_count,
                "auto_protected_count": auto_protected_count,
                "restored_suppressed_count": restored_suppressed_count,
                "candidates_generated_at": candidate_summary["generated_at"],
                "review_updated_at": state["updated_at"],
                "generated_at": utc_now_iso(),
            }
            self._atomic_json_write(self._trusted_summary_path(video_id), summary)
            return summary
        except AppError:
            temp_manifest.unlink(missing_ok=True)
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        except OSError as exc:
            temp_manifest.unlink(missing_ok=True)
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise AppError(ErrorCode.CANDIDATE_REVIEW_FAILED, "The trusted screenshot set could not be rebuilt.", 500) from exc

    def get_review(self, video_id: str) -> dict:
        candidate_summary, records = self._candidate_records(video_id)
        state = self._review_state(video_id, candidate_summary)
        merged = self._merged_records(records, state)
        trusted = self._trusted_cache_valid(video_id, state, candidate_summary)
        if not trusted:
            trusted = self._rebuild_trusted(video_id, merged, state, candidate_summary)
        return {
            "summary": trusted,
            "candidates": merged,
        }

    def update_decision(self, video_id: str, candidate_index: int, selected: bool, force: bool = False) -> dict:
        candidate_summary, records = self._candidate_records(video_id)
        if candidate_index < 0 or candidate_index >= len(records):
            raise AppError(ErrorCode.CANDIDATE_NOT_FOUND, "The requested screenshot candidate was not found.", 404)
        record = records[candidate_index]
        if not selected and self._auto_protected(record) and not force:
            raise AppError(
                ErrorCode.PROTECTED_CANDIDATE,
                "This screenshot is protected because content may disappear after it. Keep it unless you explicitly override protection.",
                409,
            )

        state = self._review_state(video_id, candidate_summary)
        decisions = dict(state.get("decisions") or {})
        default_selected = self._default_selected(record)
        if selected == default_selected:
            decisions.pop(str(candidate_index), None)
        else:
            decisions[str(candidate_index)] = selected
        state["decisions"] = decisions
        state["updated_at"] = utc_now_iso()
        self._atomic_json_write(self._review_path(video_id), state)

        merged = self._merged_records(records, state)
        trusted = self._rebuild_trusted(video_id, merged, state, candidate_summary)
        return {
            "summary": trusted,
            "candidate": merged[candidate_index],
        }
