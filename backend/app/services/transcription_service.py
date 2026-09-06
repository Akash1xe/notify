from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Iterable

from app.core.errors import AppError, ErrorCode
from app.models.job import utc_now_iso
from app.services.candidate_review_service import CandidateReviewService
from app.services.media_service import MediaService
from app.services.prepared_video_service import PreparedVideoService
from app.services.storage_service import StorageService

ProgressCallback = Callable[[str, float, str], None]
ModelLoader = Callable[[str, str, str], Any]


class TranscriptionService:
    def __init__(
        self,
        storage: StorageService,
        prepared: PreparedVideoService,
        media: MediaService,
        review: CandidateReviewService,
        model_name: str = "small.en",
        language: str = "en",
        device: str = "cpu",
        compute_type: str = "int8",
        model_loader: ModelLoader | None = None,
    ) -> None:
        self.storage = storage
        self.prepared = prepared
        self.media = media
        self.review = review
        self.model_name = model_name
        self.language = language
        self.device = device
        self.compute_type = compute_type
        self._model_loader = model_loader or self._load_faster_whisper_model
        self._model: Any | None = None
        self._model_lock = threading.Lock()

    @staticmethod
    def _load_faster_whisper_model(model_name: str, device: str, compute_type: str) -> Any:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise AppError(
                ErrorCode.WHISPER_UNAVAILABLE,
                "faster-whisper is not installed. Install the backend requirements and try again.",
                503,
            ) from exc
        try:
            return WhisperModel(model_name, device=device, compute_type=compute_type)
        except Exception as exc:
            raise AppError(
                ErrorCode.WHISPER_UNAVAILABLE,
                "The configured Whisper model could not be loaded. The first local run may need to download the model.",
                503,
            ) from exc

    def _model_instance(self) -> Any:
        with self._model_lock:
            if self._model is None:
                self._model = self._model_loader(self.model_name, self.device, self.compute_type)
            return self._model

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
            raise AppError(ErrorCode.TRANSCRIPTION_FAILED, "Transcript metadata could not be saved.", 500) from exc

    @staticmethod
    def _write_jsonl_atomic(path: Path, records: Iterable[dict], error_message: str) -> None:
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
            raise AppError(ErrorCode.TRANSCRIPTION_FAILED, error_message, 500) from exc

    def _valid_transcript_summary(self, video_id: str) -> dict | None:
        prepared = self.prepared.get_prepared_video(video_id)
        if not prepared:
            return None
        summary = self._read_json(self.storage.transcript_summary_path(video_id))
        segments_path = self.storage.transcript_segments_path(video_id)
        if not summary or not segments_path.exists():
            return None
        try:
            stat = prepared.local_video_path.stat()
        except OSError:
            return None
        if summary.get("video_id") != video_id:
            return None
        if summary.get("source_size_bytes") != stat.st_size or summary.get("source_mtime_ns") != stat.st_mtime_ns:
            return None
        if summary.get("model_name") != self.model_name or summary.get("requested_language") != self.language:
            return None
        return summary

    def _trusted_summary(self, video_id: str) -> dict:
        review = self.review.get_review(video_id)
        summary = review.get("summary")
        if not isinstance(summary, dict) or int(summary.get("selected_count") or 0) <= 0:
            raise AppError(ErrorCode.TRUSTED_SCREENSHOTS_NOT_FOUND, "Review the screenshot candidates before transcript alignment.", 409)
        return summary

    def _valid_alignment_summary(self, video_id: str, transcript: dict, trusted: dict) -> dict | None:
        summary = self._read_json(self.storage.screenshot_transcript_map_summary_path(video_id))
        mapping_path = self.storage.screenshot_transcript_map_path(video_id)
        if not summary or not mapping_path.exists():
            return None
        if summary.get("video_id") != video_id:
            return None
        if summary.get("transcript_generated_at") != transcript.get("generated_at"):
            return None
        if summary.get("trusted_generated_at") != trusted.get("generated_at"):
            return None
        if int(summary.get("trusted_screenshot_count") or -1) != int(trusted.get("selected_count") or 0):
            return None
        return summary

    def get_result(self, video_id: str) -> dict | None:
        transcript = self._valid_transcript_summary(video_id)
        if not transcript:
            return None
        try:
            trusted = self._trusted_summary(video_id)
        except AppError:
            return None
        alignment = self._valid_alignment_summary(video_id, transcript, trusted)
        if not alignment:
            return None
        return {"transcript": transcript, "alignment": alignment}

    def _transcribe(self, video_id: str, progress: ProgressCallback) -> dict:
        prepared = self.prepared.get_prepared_video(video_id)
        if not prepared:
            raise AppError(ErrorCode.VIDEO_NOT_PREPARED, "Prepare the lecture before transcription.", 409)

        audio_path = self.storage.transcript_audio_path(video_id)
        progress("AUDIO", 2.0, "Extracting lecture audio for transcription...")
        self.media.extract_transcription_audio(prepared.local_video_path, audio_path)
        progress("TRANSCRIBE", 12.0, f"Loading Whisper model {self.model_name}...")

        model = self._model_instance()
        try:
            segments_iter, info = model.transcribe(
                str(audio_path),
                language=self.language or None,
                beam_size=5,
                vad_filter=True,
                word_timestamps=False,
            )
        except AppError:
            raise
        except Exception as exc:
            raise AppError(ErrorCode.TRANSCRIPTION_FAILED, "Whisper could not transcribe the lecture audio.", 500) from exc

        try:
            source_duration = float(getattr(info, "duration", 0) or 0)
        except (TypeError, ValueError):
            source_duration = 0.0
        if source_duration <= 0:
            try:
                source_duration = float(self.media.probe(prepared.local_video_path).duration_seconds)
            except AppError:
                source_duration = 1.0

        records: list[dict] = []
        word_count = 0
        try:
            for index, segment in enumerate(segments_iter):
                start = max(0.0, float(getattr(segment, "start", 0.0) or 0.0))
                end = max(start, float(getattr(segment, "end", start) or start))
                text = str(getattr(segment, "text", "") or "").strip()
                if not text:
                    continue
                record = {
                    "segment_index": len(records),
                    "start_seconds": round(start, 6),
                    "end_seconds": round(end, 6),
                    "text": text,
                }
                records.append(record)
                word_count += len(text.split())
                pct = 12.0 + min(72.0, (end / max(source_duration, 0.001)) * 72.0)
                if index % 4 == 0:
                    progress("TRANSCRIBE", pct, f"Transcribing lecture... {end / 60:.1f} min processed")
        except AppError:
            raise
        except Exception as exc:
            raise AppError(ErrorCode.TRANSCRIPTION_FAILED, "Whisper transcription stopped unexpectedly.", 500) from exc

        self._write_jsonl_atomic(
            self.storage.transcript_segments_path(video_id),
            records,
            "Timestamped transcript segments could not be saved.",
        )
        stat = prepared.local_video_path.stat()
        detected_language = str(getattr(info, "language", self.language) or self.language)
        try:
            probability = float(getattr(info, "language_probability", 0.0) or 0.0)
        except (TypeError, ValueError):
            probability = 0.0
        summary = {
            "video_id": video_id,
            "status": "READY",
            "model_name": self.model_name,
            "requested_language": self.language,
            "detected_language": detected_language,
            "language_probability": round(probability, 6),
            "duration_seconds": round(source_duration, 6),
            "segment_count": len(records),
            "word_count": word_count,
            "audio_sample_rate_hz": 16000,
            "source_size_bytes": stat.st_size,
            "source_mtime_ns": stat.st_mtime_ns,
            "generated_at": utc_now_iso(),
        }
        self._atomic_json_write(self.storage.transcript_summary_path(video_id), summary)
        progress("TRANSCRIBE", 86.0, f"Transcript ready with {len(records):,} timestamped segments.")
        return summary

    def _load_segments(self, video_id: str, expected_count: int) -> list[dict]:
        path = self.storage.transcript_segments_path(video_id)
        records: list[dict] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    payload = json.loads(line)
                    if int(payload["segment_index"]) != len(records):
                        raise ValueError
                    records.append(payload)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise AppError(ErrorCode.TRANSCRIPTION_FAILED, "The persisted transcript segment file is invalid.", 422) from exc
        if len(records) != expected_count:
            raise AppError(ErrorCode.TRANSCRIPTION_FAILED, "Transcript segment coverage does not match its summary.", 422)
        return records

    def _load_trusted_records(self, video_id: str, expected_count: int) -> list[dict]:
        path = self.storage.analysis_dir(video_id) / "trusted-screenshots.jsonl"
        records: list[dict] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    payload = json.loads(line)
                    if int(payload["trusted_index"]) != len(records):
                        raise ValueError
                    records.append(payload)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise AppError(ErrorCode.TRUSTED_SCREENSHOTS_NOT_FOUND, "The trusted screenshot manifest is invalid.", 422) from exc
        if len(records) != expected_count:
            raise AppError(ErrorCode.TRUSTED_SCREENSHOTS_NOT_FOUND, "Trusted screenshot coverage does not match its summary.", 422)
        return records

    def _align(self, video_id: str, transcript: dict, trusted: dict, progress: ProgressCallback) -> dict:
        progress("ALIGN", 88.0, "Aligning trusted screenshots with nearby lecture speech...")
        segments = self._load_segments(video_id, int(transcript.get("segment_count") or 0))
        trusted_records = self._load_trusted_records(video_id, int(trusted.get("selected_count") or 0))
        mappings: list[dict] = []
        aligned_count = 0
        for screenshot in trusted_records:
            timestamp = float(screenshot["timestamp_seconds"])
            window_start = max(0.0, timestamp - 6.0)
            window_end = timestamp + 8.0
            nearby = [
                segment
                for segment in segments
                if float(segment["end_seconds"]) >= window_start and float(segment["start_seconds"]) <= window_end
            ]
            text = " ".join(str(segment["text"]).strip() for segment in nearby if str(segment["text"]).strip()).strip()
            if text:
                aligned_count += 1
            mappings.append(
                {
                    "trusted_index": int(screenshot["trusted_index"]),
                    "candidate_index": int(screenshot["candidate_index"]),
                    "frame_index": int(screenshot["frame_index"]),
                    "timestamp_seconds": timestamp,
                    "context_start_seconds": round(window_start, 6),
                    "context_end_seconds": round(window_end, 6),
                    "segment_indexes": [int(segment["segment_index"]) for segment in nearby],
                    "text": text,
                }
            )

        self._write_jsonl_atomic(
            self.storage.screenshot_transcript_map_path(video_id),
            mappings,
            "Screenshot-to-transcript alignment could not be saved.",
        )
        summary = {
            "video_id": video_id,
            "status": "READY",
            "trusted_screenshot_count": len(trusted_records),
            "aligned_screenshot_count": aligned_count,
            "unaligned_screenshot_count": len(trusted_records) - aligned_count,
            "context_before_seconds": 6.0,
            "context_after_seconds": 8.0,
            "transcript_generated_at": transcript["generated_at"],
            "trusted_generated_at": trusted["generated_at"],
            "generated_at": utc_now_iso(),
        }
        self._atomic_json_write(self.storage.screenshot_transcript_map_summary_path(video_id), summary)
        progress("ALIGN", 100.0, f"Transcript aligned to {aligned_count:,}/{len(trusted_records):,} trusted screenshots.")
        return summary

    def process(self, video_id: str, progress: ProgressCallback) -> dict:
        trusted = self._trusted_summary(video_id)
        transcript = self._valid_transcript_summary(video_id)
        if transcript:
            progress("TRANSCRIBE", 86.0, "Reusing the existing timestamped transcript.")
        else:
            transcript = self._transcribe(video_id, progress)

        alignment = self._valid_alignment_summary(video_id, transcript, trusted)
        if not alignment:
            alignment = self._align(video_id, transcript, trusted, progress)
        else:
            progress("ALIGN", 100.0, "Transcript and screenshot alignment already exist and are valid.")
        return {"transcript": transcript, "alignment": alignment}
