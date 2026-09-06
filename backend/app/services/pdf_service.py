from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path
from typing import Callable

import cv2
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.core.errors import AppError, ErrorCode
from app.models.job import utc_now_iso
from app.services.candidate_review_service import CandidateReviewService
from app.services.coverage_service import CoverageService
from app.services.storage_service import StorageService
from app.services.topic_detection_service import TopicDetectionService
from app.utils.youtube_url import validate_video_id

ProgressCallback = Callable[[float, str], None]


class PdfService:
    PIPELINE_VERSION = 1
    REVIEW_VERSION = 1
    DEFAULT_SETTINGS = {
        "image_quality": 92,
        "include_cover": True,
        "include_topic_dividers": True,
        "include_context": False,
    }

    def __init__(
        self,
        storage: StorageService,
        coverage: CoverageService,
        review: CandidateReviewService,
        topics: TopicDetectionService,
    ) -> None:
        self.storage = storage
        self.coverage = coverage
        self.review = review
        self.topics = topics

    def _review_path(self, video_id: str) -> Path:
        return self.storage.analysis_dir(video_id) / "pdf-review.json"

    def _trusted_path(self, video_id: str) -> Path:
        return self.storage.analysis_dir(video_id) / "trusted-screenshots.jsonl"

    def _trusted_dir(self, video_id: str) -> Path:
        return self.storage.analysis_dir(video_id) / "trusted-screenshots"

    def _content_path(self, video_id: str) -> Path:
        return self.storage.analysis_dir(video_id) / "screenshot-content.jsonl"

    def _output_dir(self, video_id: str) -> Path:
        validate_video_id(video_id)
        root = self.storage.output_dir.resolve()
        path = (root / video_id).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise AppError(ErrorCode.STORAGE_ERROR, "An unsafe PDF output path was rejected.", 400) from exc
        return path

    def _pdf_path(self, video_id: str) -> Path:
        return self._output_dir(video_id) / "lecture-notes.pdf"

    def _manifest_path(self, video_id: str) -> Path:
        return self._output_dir(video_id) / "pdf-manifest.json"

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
    def _read_jsonl(path: Path) -> list[dict]:
        records: list[dict] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError
                    records.append(value)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise AppError(ErrorCode.PDF_GENERATION_FAILED, f"PDF source data is invalid: {path.name}.", 422) from exc
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
            raise AppError(ErrorCode.PDF_GENERATION_FAILED, "PDF metadata could not be saved.", 500) from exc

    @staticmethod
    def _pdf_text(value: object) -> str:
        return str(value or "").encode("latin-1", "replace").decode("latin-1")

    @staticmethod
    def _format_time(seconds: float) -> str:
        total = max(0, int(round(seconds)))
        hours, remainder = divmod(total, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    @classmethod
    def normalize_settings(cls, settings: dict | None) -> dict:
        raw = dict(cls.DEFAULT_SETTINGS)
        if settings:
            raw.update(settings)
        quality = int(raw.get("image_quality") or cls.DEFAULT_SETTINGS["image_quality"])
        if quality < 70 or quality > 100:
            raise AppError(ErrorCode.PDF_GENERATION_FAILED, "PDF image quality must be between 70 and 100.", 422)
        return {
            "image_quality": quality,
            "include_cover": bool(raw.get("include_cover")),
            "include_topic_dividers": bool(raw.get("include_topic_dividers")),
            "include_context": bool(raw.get("include_context")),
        }

    def _inputs(self, video_id: str) -> dict:
        coverage = self.coverage.get_result(video_id)
        if not coverage:
            raise AppError(ErrorCode.COVERAGE_NOT_FOUND, "Run the lecture coverage audit before PDF generation.", 409)
        coverage_summary = coverage.get("summary") or {}
        if not bool(coverage_summary.get("ready_for_pdf")):
            raise AppError(
                ErrorCode.COVERAGE_BLOCKED,
                "PDF generation is blocked because the latest coverage audit still has unresolved findings.",
                409,
            )

        review_result = self.review.get_review(video_id)
        trusted_summary = review_result.get("summary") or {}
        trusted_count = int(trusted_summary.get("selected_count") or 0)
        if trusted_count <= 0:
            raise AppError(ErrorCode.TRUSTED_SCREENSHOTS_NOT_FOUND, "No trusted screenshots are available for PDF generation.", 409)

        topic_result = self.topics.get_result(video_id)
        if not topic_result:
            raise AppError(ErrorCode.TOPICS_NOT_FOUND, "Lecture topics are required before PDF generation.", 409)

        trusted_path = self._trusted_path(video_id)
        if not trusted_path.exists():
            raise AppError(ErrorCode.TRUSTED_SCREENSHOTS_NOT_FOUND, "The trusted screenshot manifest is missing.", 409)
        trusted = self._read_jsonl(trusted_path)
        if len(trusted) != trusted_count:
            raise AppError(ErrorCode.PDF_GENERATION_FAILED, "Trusted screenshot coverage changed before PDF generation.", 422)
        for index, record in enumerate(trusted):
            if int(record.get("trusted_index", -1)) != index:
                raise AppError(ErrorCode.PDF_GENERATION_FAILED, "The trusted screenshot manifest is not contiguous.", 422)
            filename = str(record.get("image_filename") or "")
            if not filename or not (self._trusted_dir(video_id) / filename).is_file():
                raise AppError(ErrorCode.PDF_GENERATION_FAILED, "A trusted screenshot image is missing.", 422)

        return {
            "coverage": coverage,
            "coverage_summary": coverage_summary,
            "trusted_summary": trusted_summary,
            "trusted": trusted,
            "topic_result": topic_result,
        }

    @staticmethod
    def _default_order(topic_result: dict, trusted_count: int) -> list[int]:
        topics = topic_result.get("topics")
        if not isinstance(topics, list) or not topics:
            raise AppError(ErrorCode.PDF_REVIEW_INVALID, "Lecture topics are not available for PDF ordering.", 422)
        order: list[int] = []
        for topic in topics:
            for value in topic.get("trusted_screenshot_indexes") or []:
                order.append(int(value))
        expected = list(range(trusted_count))
        if sorted(order) != expected or len(set(order)) != trusted_count:
            raise AppError(ErrorCode.PDF_REVIEW_INVALID, "Topic ordering does not cover every trusted screenshot exactly once.", 422)
        return order

    @staticmethod
    def _topic_index_map(topic_result: dict, trusted_count: int) -> dict[int, dict]:
        mapping: dict[int, dict] = {}
        for topic in topic_result.get("topics") or []:
            for value in topic.get("trusted_screenshot_indexes") or []:
                index = int(value)
                if index in mapping:
                    raise AppError(ErrorCode.PDF_REVIEW_INVALID, "A screenshot is assigned to multiple PDF sections.", 422)
                mapping[index] = topic
        if sorted(mapping) != list(range(trusted_count)):
            raise AppError(ErrorCode.PDF_REVIEW_INVALID, "PDF section mapping does not cover every trusted screenshot.", 422)
        return mapping

    def _review_valid(self, payload: dict | None, inputs: dict) -> bool:
        if not payload:
            return False
        topic_summary = inputs["topic_result"].get("summary") or {}
        sources = payload.get("source_versions") or {}
        return (
            payload.get("video_id") == inputs["coverage_summary"].get("video_id")
            and int(payload.get("pipeline_version") or 0) == self.REVIEW_VERSION
            and sources.get("coverage_generated_at") == inputs["coverage_summary"].get("generated_at")
            and sources.get("trusted_generated_at") == inputs["trusted_summary"].get("generated_at")
            and sources.get("topics_generated_at") == topic_summary.get("generated_at")
        )

    def _invalidate_pdf(self, video_id: str) -> None:
        self._manifest_path(video_id).unlink(missing_ok=True)
        self._pdf_path(video_id).unlink(missing_ok=True)

    def get_review(self, video_id: str) -> dict:
        inputs = self._inputs(video_id)
        trusted_count = len(inputs["trusted"])
        payload = self._read_json(self._review_path(video_id))
        if not self._review_valid(payload, inputs):
            now = utc_now_iso()
            payload = {
                "video_id": video_id,
                "pipeline_version": self.REVIEW_VERSION,
                "ordered_trusted_indexes": self._default_order(inputs["topic_result"], trusted_count),
                "source_versions": {
                    "coverage_generated_at": inputs["coverage_summary"].get("generated_at"),
                    "trusted_generated_at": inputs["trusted_summary"].get("generated_at"),
                    "topics_generated_at": (inputs["topic_result"].get("summary") or {}).get("generated_at"),
                },
                "updated_at": now,
            }
            self._write_json_atomic(self._review_path(video_id), payload)
            self._invalidate_pdf(video_id)

        order = [int(value) for value in payload.get("ordered_trusted_indexes") or []]
        if sorted(order) != list(range(trusted_count)) or len(set(order)) != trusted_count:
            raise AppError(ErrorCode.PDF_REVIEW_INVALID, "Saved PDF ordering is invalid.", 422)

        topic_map = self._topic_index_map(inputs["topic_result"], trusted_count)
        trusted_by_index = {int(item["trusted_index"]): item for item in inputs["trusted"]}
        items: list[dict] = []
        for position, trusted_index in enumerate(order):
            trusted = trusted_by_index[trusted_index]
            topic = topic_map[trusted_index]
            items.append({
                "position": position,
                "trusted_index": trusted_index,
                "candidate_index": int(trusted.get("candidate_index") or 0),
                "frame_index": int(trusted.get("frame_index") or 0),
                "timestamp_seconds": float(trusted.get("timestamp_seconds") or 0.0),
                "topic_index": int(topic.get("topic_index") or 0),
                "topic_title": str(topic.get("title") or "Lecture section"),
                "image_filename": str(trusted.get("image_filename") or ""),
                "auto_protected": bool(trusted.get("auto_protected")),
                "content_loss_risk": bool(trusted.get("content_loss_risk")),
            })

        return {
            "summary": {
                "video_id": video_id,
                "pipeline_version": self.REVIEW_VERSION,
                "screenshot_count": trusted_count,
                "topic_count": int((inputs["topic_result"].get("summary") or {}).get("topic_count") or 0),
                "coverage_generated_at": inputs["coverage_summary"].get("generated_at"),
                "trusted_generated_at": inputs["trusted_summary"].get("generated_at"),
                "topics_generated_at": (inputs["topic_result"].get("summary") or {}).get("generated_at"),
                "updated_at": payload["updated_at"],
            },
            "items": items,
        }

    def update_review(self, video_id: str, ordered_trusted_indexes: list[int]) -> dict:
        current = self.get_review(video_id)
        count = int(current["summary"]["screenshot_count"])
        order = [int(value) for value in ordered_trusted_indexes]
        if sorted(order) != list(range(count)) or len(set(order)) != count:
            raise AppError(
                ErrorCode.PDF_REVIEW_INVALID,
                "Final PDF ordering must contain every trusted screenshot exactly once. Remove or restore screenshots in candidate review, then rerun downstream analysis.",
                422,
            )
        existing_order = [int(item["trusted_index"]) for item in current["items"]]
        if order == existing_order:
            return current
        payload = {
            "video_id": video_id,
            "pipeline_version": self.REVIEW_VERSION,
            "ordered_trusted_indexes": order,
            "source_versions": {
                "coverage_generated_at": current["summary"]["coverage_generated_at"],
                "trusted_generated_at": current["summary"]["trusted_generated_at"],
                "topics_generated_at": current["summary"]["topics_generated_at"],
            },
            "updated_at": utc_now_iso(),
        }
        self._write_json_atomic(self._review_path(video_id), payload)
        self._invalidate_pdf(video_id)
        return self.get_review(video_id)

    @staticmethod
    def _wrap_lines(pdf: canvas.Canvas, text: str, max_width: float, font_name: str, font_size: float, max_lines: int) -> list[str]:
        words = PdfService._pdf_text(text).replace("\n", " ").split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if pdf.stringWidth(candidate, font_name, font_size) <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
        if current and len(lines) < max_lines:
            lines.append(current)
        if len(lines) == max_lines and words:
            lines[-1] = lines[-1][: max(0, len(lines[-1]) - 3)].rstrip() + "..."
        return lines

    @staticmethod
    def _image_reader(path: Path, quality: int) -> ImageReader:
        if quality >= 97:
            return ImageReader(str(path))
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise AppError(ErrorCode.PDF_GENERATION_FAILED, "A trusted screenshot could not be decoded for PDF generation.", 422)
        ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not ok:
            raise AppError(ErrorCode.PDF_GENERATION_FAILED, "A trusted screenshot could not be encoded for the PDF.", 500)
        return ImageReader(io.BytesIO(encoded.tobytes()))

    def _draw_cover(self, pdf: canvas.Canvas, width: float, height: float, metadata: dict, screenshot_count: int, topic_count: int) -> None:
        pdf.setFillColorRGB(0.06, 0.08, 0.12)
        pdf.rect(0, 0, width, height, fill=1, stroke=0)
        pdf.setFillColorRGB(0.35, 0.95, 0.72)
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(48, height - 64, "NOTIFY  /  LECTURE NOTES")
        pdf.setFillColorRGB(1, 1, 1)
        title = self._pdf_text(metadata.get("title") or "Lecture Notes")
        y = height - 120
        for line in self._wrap_lines(pdf, title, width - 96, "Helvetica-Bold", 28, 4):
            pdf.setFont("Helvetica-Bold", 28)
            pdf.drawString(48, y, line)
            y -= 36
        channel = self._pdf_text(metadata.get("channel") or metadata.get("uploader") or "")
        if channel:
            pdf.setFillColorRGB(0.75, 0.8, 0.88)
            pdf.setFont("Helvetica", 13)
            pdf.drawString(48, y - 4, channel)
        duration = float(metadata.get("duration_seconds") or 0.0)
        pdf.setFillColorRGB(0.75, 0.8, 0.88)
        pdf.setFont("Helvetica", 11)
        details = f"{screenshot_count} trusted screenshots  |  {topic_count} sections"
        if duration > 0:
            details += f"  |  {self._format_time(duration)} lecture"
        pdf.drawString(48, 74, details)
        pdf.setFillColorRGB(0.35, 0.95, 0.72)
        pdf.drawString(48, 50, "Coverage verified before generation")
        pdf.showPage()

    def _draw_topic_divider(self, pdf: canvas.Canvas, width: float, height: float, topic: dict) -> None:
        pdf.setFillColorRGB(0.98, 0.98, 0.99)
        pdf.rect(0, 0, width, height, fill=1, stroke=0)
        pdf.setFillColorRGB(0.18, 0.22, 0.32)
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(48, height - 72, f"SECTION {int(topic.get('topic_index') or 0) + 1}")
        y = height - 126
        title = self._pdf_text(topic.get("title") or "Lecture section")
        for line in self._wrap_lines(pdf, title, width - 96, "Helvetica-Bold", 25, 4):
            pdf.setFont("Helvetica-Bold", 25)
            pdf.drawString(48, y, line)
            y -= 34
        start = self._format_time(float(topic.get("start_seconds") or 0.0))
        end = self._format_time(float(topic.get("end_seconds") or 0.0))
        pdf.setFillColorRGB(0.4, 0.45, 0.55)
        pdf.setFont("Helvetica", 11)
        pdf.drawString(48, max(64, y - 8), f"Lecture time {start} - {end}")
        pdf.showPage()

    def _draw_screenshot_page(
        self,
        pdf: canvas.Canvas,
        width: float,
        height: float,
        image_path: Path,
        item: dict,
        settings: dict,
        context: str,
    ) -> None:
        pdf.setFillColorRGB(1, 1, 1)
        pdf.rect(0, 0, width, height, fill=1, stroke=0)
        pdf.setFillColorRGB(0.12, 0.15, 0.22)
        pdf.setFont("Helvetica-Bold", 11)
        header = f"Section {int(item['topic_index']) + 1}  |  {self._pdf_text(item['topic_title'])}"
        pdf.drawString(30, height - 28, header[:120])
        pdf.setFont("Helvetica", 9)
        pdf.setFillColorRGB(0.4, 0.45, 0.55)
        pdf.drawRightString(width - 30, height - 28, self._format_time(float(item["timestamp_seconds"])))

        context_height = 66 if settings["include_context"] and context.strip() else 0
        top = height - 48
        bottom = 30 + context_height
        box_width = width - 60
        box_height = top - bottom
        reader = self._image_reader(image_path, int(settings["image_quality"]))
        image_width, image_height = reader.getSize()
        scale = min(box_width / max(1, image_width), box_height / max(1, image_height))
        draw_width = image_width * scale
        draw_height = image_height * scale
        x = (width - draw_width) / 2
        y = bottom + (box_height - draw_height) / 2
        pdf.drawImage(reader, x, y, width=draw_width, height=draw_height, preserveAspectRatio=True, mask="auto")

        if context_height:
            pdf.setFillColorRGB(0.96, 0.97, 0.99)
            pdf.rect(30, 28, width - 60, context_height - 8, fill=1, stroke=0)
            pdf.setFillColorRGB(0.28, 0.32, 0.4)
            pdf.setFont("Helvetica", 8.5)
            lines = self._wrap_lines(pdf, context, width - 78, "Helvetica", 8.5, 4)
            line_y = 28 + context_height - 22
            for line in lines:
                pdf.drawString(39, line_y, line)
                line_y -= 11
        pdf.showPage()

    def generate(self, video_id: str, settings: dict | None, progress: ProgressCallback) -> dict:
        normalized = self.normalize_settings(settings)
        inputs = self._inputs(video_id)
        review = self.get_review(video_id)
        metadata = self.storage.read_video_manifest(video_id) or {"video_id": video_id, "title": "Lecture Notes"}
        topic_by_index = {int(topic["topic_index"]): topic for topic in inputs["topic_result"].get("topics") or []}
        content_by_index: dict[int, dict] = {}
        if normalized["include_context"]:
            content_path = self._content_path(video_id)
            if not content_path.exists():
                raise AppError(ErrorCode.PDF_GENERATION_FAILED, "Screenshot context is missing for context-enabled PDF generation.", 409)
            content_by_index = {int(item.get("trusted_index") or 0): item for item in self._read_jsonl(content_path)}

        output_dir = self._output_dir(video_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        final_path = self._pdf_path(video_id)
        temp_path = output_dir / "lecture-notes.pdf.tmp"
        temp_path.unlink(missing_ok=True)
        page_width, page_height = landscape(A4)
        screenshot_count = len(review["items"])
        topic_count = int(review["summary"]["topic_count"])
        page_count = 0

        progress(4.0, "Preparing final topic-ordered PDF...")
        try:
            pdf = canvas.Canvas(str(temp_path), pagesize=(page_width, page_height), pageCompression=1)
            pdf.setTitle(self._pdf_text(metadata.get("title") or "Lecture Notes"))
            pdf.setAuthor("Notify")
            pdf.setCreator("Notify local lecture-to-PDF")
            pdf.setSubject("Coverage-verified lecture screenshot notes")

            if normalized["include_cover"]:
                self._draw_cover(pdf, page_width, page_height, metadata, screenshot_count, topic_count)
                page_count += 1

            last_topic: int | None = None
            for position, item in enumerate(review["items"]):
                topic_index = int(item["topic_index"])
                topic = topic_by_index.get(topic_index)
                if topic is None:
                    raise AppError(ErrorCode.PDF_GENERATION_FAILED, "A PDF page references a missing lecture topic.", 422)
                if normalized["include_topic_dividers"] and topic_index != last_topic:
                    self._draw_topic_divider(pdf, page_width, page_height, topic)
                    page_count += 1
                last_topic = topic_index
                image_path = self._trusted_dir(video_id) / str(item["image_filename"])
                content = content_by_index.get(int(item["trusted_index"]), {})
                context = str(content.get("combined_context") or "")
                self._draw_screenshot_page(pdf, page_width, page_height, image_path, item, normalized, context)
                page_count += 1
                progress(8.0 + ((position + 1) / max(1, screenshot_count)) * 87.0, f"Adding screenshot {position + 1:,}/{screenshot_count:,}...")

            pdf.save()
            if not temp_path.exists() or temp_path.stat().st_size <= 8:
                raise AppError(ErrorCode.PDF_GENERATION_FAILED, "The generated PDF file is empty or invalid.", 500)
            with temp_path.open("rb") as handle:
                if handle.read(5) != b"%PDF-":
                    raise AppError(ErrorCode.PDF_GENERATION_FAILED, "The generated output is not a valid PDF file.", 500)
            os.replace(temp_path, final_path)
        except AppError:
            temp_path.unlink(missing_ok=True)
            raise
        except Exception as exc:
            temp_path.unlink(missing_ok=True)
            raise AppError(ErrorCode.PDF_GENERATION_FAILED, "Final PDF generation failed.", 500) from exc

        title = str(metadata.get("title") or "lecture-notes")
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-._")[:80] or "lecture-notes"
        manifest = {
            "video_id": video_id,
            "status": "READY",
            "pipeline_version": self.PIPELINE_VERSION,
            "file_name": f"{slug}.pdf",
            "file_size_bytes": final_path.stat().st_size,
            "page_count": page_count,
            "screenshot_count": screenshot_count,
            "topic_count": topic_count,
            "settings": normalized,
            "coverage_generated_at": inputs["coverage_summary"].get("generated_at"),
            "review_updated_at": review["summary"]["updated_at"],
            "trusted_generated_at": review["summary"]["trusted_generated_at"],
            "topics_generated_at": review["summary"]["topics_generated_at"],
            "generated_at": utc_now_iso(),
        }
        self._write_json_atomic(self._manifest_path(video_id), manifest)
        progress(100.0, "Final lecture PDF generated successfully.")
        return manifest

    def get_result(self, video_id: str) -> dict | None:
        try:
            inputs = self._inputs(video_id)
            review = self.get_review(video_id)
        except AppError:
            return None
        manifest = self._read_json(self._manifest_path(video_id))
        pdf_path = self._pdf_path(video_id)
        if not manifest or not pdf_path.exists():
            return None
        if manifest.get("video_id") != video_id or int(manifest.get("pipeline_version") or 0) != self.PIPELINE_VERSION:
            return None
        if manifest.get("coverage_generated_at") != inputs["coverage_summary"].get("generated_at"):
            return None
        if manifest.get("review_updated_at") != review["summary"]["updated_at"]:
            return None
        if manifest.get("trusted_generated_at") != review["summary"]["trusted_generated_at"]:
            return None
        if manifest.get("topics_generated_at") != review["summary"]["topics_generated_at"]:
            return None
        try:
            size = pdf_path.stat().st_size
            with pdf_path.open("rb") as handle:
                valid_header = handle.read(5) == b"%PDF-"
        except OSError:
            return None
        if size != int(manifest.get("file_size_bytes") or -1) or not valid_header:
            return None
        return manifest

    def matches_settings(self, video_id: str, settings: dict | None) -> bool:
        result = self.get_result(video_id)
        return bool(result and result.get("settings") == self.normalize_settings(settings))

    def download_path(self, video_id: str) -> tuple[Path, dict]:
        result = self.get_result(video_id)
        if not result:
            raise AppError(ErrorCode.PDF_NOT_FOUND, "A current coverage-verified PDF has not been generated yet.", 404)
        return self._pdf_path(video_id), result
