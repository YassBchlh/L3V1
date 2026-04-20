# Version5/back/segmentation/SegmentationWeb.py
from typing import List, Dict, Any
import re

from back.extraction.gestionExtraction import WebLinkSource
from back.segmentation.SegmentationFallback import build_universal_segments


class WebSegmentationError(Exception):
    pass


def validate_text(text: str) -> None:
    if not text or not text.strip():
        raise WebSegmentationError("Le texte du site web est vide.")


def normalize_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_by_markdown_titles(text: str) -> List[str]:
    sections = re.split(r"(?=^#{1,6}\s+)", text, flags=re.MULTILINE)
    return [section.strip() for section in sections if section.strip()]


def split_by_paragraphs(text: str) -> List[str]:
    paragraphs = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paragraphs if p.strip()]


def split_by_sentences(text: str) -> List[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def merge_short_segments(segments: List[str], min_length: int = 120) -> List[str]:
    merged = []
    buffer = ""

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        if len(segment) < min_length:
            if buffer:
                buffer += "\n\n" + segment
            else:
                buffer = segment
        else:
            if buffer:
                merged.append((buffer + "\n\n" + segment).strip())
                buffer = ""
            else:
                merged.append(segment)

    if buffer:
        if merged:
            merged[-1] = (merged[-1] + "\n\n" + buffer).strip()
        else:
            merged.append(buffer)

    return merged


def split_long_segment(segment: str, max_length: int = 1200, overlap: int = 200) -> List[str]:
    if len(segment) <= max_length:
        return [segment.strip()]

    chunks = []
    start = 0
    step = max_length - overlap

    while start < len(segment):
        end = min(start + max_length, len(segment))

        if end < len(segment):
            last_break = max(
                segment.rfind("\n\n", start, end),
                segment.rfind(". ", start, end),
                segment.rfind("! ", start, end),
                segment.rfind("? ", start, end),
                segment.rfind("; ", start, end),
                segment.rfind(": ", start, end),
            )
            if last_break > start + max_length // 2:
                end = last_break + 1

        chunk = segment[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start += step

    return chunks


def refine_segments(
    segments: List[str],
    min_length: int = 120,
    max_length: int = 1200,
    overlap: int = 200
) -> List[str]:
    merged = merge_short_segments(segments, min_length=min_length)

    refined = []
    for seg in merged:
        refined.extend(split_long_segment(seg, max_length=max_length, overlap=overlap))

    return [seg.strip() for seg in refined if seg.strip()]


def segment_web_text(
    text: str,
    min_length: int = 120,
    max_length: int = 1200,
    overlap: int = 200
) -> List[str]:
    validate_text(text)
    text = normalize_text(text)

    markdown_segments = split_by_markdown_titles(text)
    if len(markdown_segments) >= 2:
        return refine_segments(markdown_segments, min_length, max_length, overlap)

    paragraph_segments = split_by_paragraphs(text)
    if len(paragraph_segments) >= 2:
        return refine_segments(paragraph_segments, min_length, max_length, overlap)

    sentence_segments = split_by_sentences(text)
    if sentence_segments:
        return refine_segments(sentence_segments, min_length, max_length, overlap)

    raise WebSegmentationError("Aucun segment exploitable n'a été trouvé.")


def extract_clean_and_segment_webpage(
    url: str,
    min_length: int = 120,
    max_length: int = 1200,
    overlap: int = 200
) -> List[Dict[str, Any]]:
    try:
        source = WebLinkSource(url)
        source.validate()

        extracted_text = source.extract_text()
        cleaned_text = source.clean_text(extracted_text)

        source.set_title()
        source.set_sourceID()
        source.set_importedAt()

        try:
            segments = segment_web_text(
                cleaned_text,
                min_length=min_length,
                max_length=max_length,
                overlap=overlap
            )

            return [
                {
                    "segment_id": i,
                    "source_type": "website",
                    "title": source.title,
                    "sourceID": source.sourceID,
                    "importedAt": source.importedAt,
                    "text": segment,
                    "length": len(segment),
                    "url": url
                }
                for i, segment in enumerate(segments, start=1)
            ]

        except Exception:
            return build_universal_segments(
                text=cleaned_text,
                source_type="website",
                title=source.title,
                sourceID=source.sourceID,
                importedAt=source.importedAt,
                min_length=min_length,
                max_length=max_length,
                overlap=overlap
            )

    except Exception as e:
        raise WebSegmentationError(
            f"Erreur pendant extraction + nettoyage + segmentation web : {e}"
        )