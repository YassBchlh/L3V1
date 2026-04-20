# Version5/back/segmentation/SegRouter.py
from typing import List, Dict, Any

from back.segmentation.SegmentationTxt import segment_clean_text
from back.segmentation.SegmentationWeb import segment_web_text
from back.segmentation.SegmentationYT import segment_youtube_text
from back.segmentation.SegDiapo import segment_diaporama_text
from back.segmentation.SegmentationFallback import build_universal_segments
def _wrap_segments(
    segments: List[str],
    source_type: str,
    title: str,
    sourceID: str,
    importedAt
) -> List[Dict[str, Any]]:
    return [
        {
            "segment_id": i,
            "source_type": source_type,
            "title": title,
            "sourceID": sourceID,
            "importedAt": importedAt,
            "text": seg,
            "length": len(seg),
        }
        for i, seg in enumerate(segments, start=1)
    ]


def segment_extracted_resource(
    resource: Dict[str, Any],
    min_length: int = 120,
    max_length: int = 1200,
    overlap: int = 200
) -> List[Dict[str, Any]]:
    source_type = str(resource.get("type", "")).lower().strip()
    subtype = str(resource.get("subtype", "")).lower().strip() if resource.get("subtype") else None
    text = resource.get("text", "").strip()
    title = resource.get("title", "Sans titre")
    sourceID = resource.get("sourceID", "unknown")
    importedAt = resource.get("importedAt")

    if not text:
        return []

    try:
        if source_type in {"txt", "md", "docx"}:
            segments = segment_clean_text(
                text,
                min_length=min_length,
                max_length=max_length,
                overlap=overlap
            )
            return _wrap_segments(segments, source_type, title, sourceID, importedAt)

        if source_type == "website":
            segments = segment_web_text(
                text,
                min_length=min_length,
                max_length=max_length,
                overlap=overlap
            )
            return _wrap_segments(segments, "website", title, sourceID, importedAt)

        if source_type == "youtube":
            segments = segment_youtube_text(
                text,
                min_length=180,
                max_length=1500,
                overlap=250
            )
            return _wrap_segments(segments, "youtube", title, sourceID, importedAt)

        if source_type == "pdf":
            if subtype == "diaporama" or "--- Slide" in text:
                segments = segment_diaporama_text(
                    text,
                    min_length=100,
                    max_length=1200,
                    overlap=200
                )
                return _wrap_segments(segments, "diaporama", title, sourceID, importedAt)

            return build_universal_segments(
                text=text,
                source_type="pdf",
                title=title,
                sourceID=sourceID,
                importedAt=importedAt,
                min_length=min_length,
                max_length=max_length,
                overlap=overlap
            )

        return build_universal_segments(
            text=text,
            source_type=source_type or "unknown",
            title=title,
            sourceID=sourceID,
            importedAt=importedAt,
            min_length=min_length,
            max_length=max_length,
            overlap=overlap
        )

    except Exception:
        return build_universal_segments(
            text=text,
            source_type=source_type or "unknown",
            title=title,
            sourceID=sourceID,
            importedAt=importedAt,
            min_length=min_length,
            max_length=max_length,
            overlap=overlap
        )