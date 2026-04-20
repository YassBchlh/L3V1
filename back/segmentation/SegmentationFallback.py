# Version5/back/segmentation/SegmentationFallback.py
from typing import List, Dict, Any
import re


class UniversalSegmentationError(Exception):
    """
    Exception levée lorsqu'aucune segmentation universelle exploitable n'est possible.
    """
    pass


def validate_text(text: str) -> None:
    if not text or not text.strip():
        raise UniversalSegmentationError("Le texte à segmenter est vide.")


def normalize_text(text: str) -> str:
    """
    Normalisation générique robuste.
    """
    text = text.replace("\xa0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # espaces multiples
    text = re.sub(r"[ \t]+", " ", text)

    # trop de lignes vides
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def split_by_blocks(text: str) -> List[str]:
    """
    Découpe d'abord par blocs séparés par des lignes vides.
    """
    blocks = re.split(r"\n\s*\n", text)
    return [block.strip() for block in blocks if block.strip()]


def split_by_sentences(text: str) -> List[str]:
    """
    Découpe par phrases.
    """
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []

    sentences = re.split(r"(?<=[.!?])\s+", compact)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def merge_short_segments(segments: List[str], min_length: int = 120) -> List[str]:
    """
    Fusionne les segments trop courts.
    """
    if not segments:
        return []

    merged: List[str] = []
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
    """
    Découpe un segment trop long avec overlap.
    """
    if max_length <= 0:
        raise UniversalSegmentationError("max_length doit être strictement positif.")
    if overlap < 0:
        raise UniversalSegmentationError("overlap doit être positif ou nul.")
    if overlap >= max_length:
        raise UniversalSegmentationError("overlap doit être strictement inférieur à max_length.")

    if len(segment) <= max_length:
        return [segment.strip()]

    chunks: List[str] = []
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

    refined: List[str] = []
    for segment in merged:
        refined.extend(
            split_long_segment(
                segment,
                max_length=max_length,
                overlap=overlap
            )
        )

    return [segment.strip() for segment in refined if segment.strip()]


def segment_universal_text(
    text: str,
    min_length: int = 120,
    max_length: int = 1200,
    overlap: int = 200
) -> List[str]:
    """
    Segmentation universelle générique.
    """
    validate_text(text)
    text = normalize_text(text)

    blocks = split_by_blocks(text)
    if len(blocks) >= 2:
        segments = refine_segments(
            blocks,
            min_length=min_length,
            max_length=max_length,
            overlap=overlap
        )
        if segments:
            return segments

    sentences = split_by_sentences(text)
    if sentences:
        segments = refine_segments(
            sentences,
            min_length=min_length,
            max_length=max_length,
            overlap=overlap
        )
        if segments:
            return segments

    raise UniversalSegmentationError("Impossible de segmenter ce texte avec le fallback universel.")


def build_universal_segments(
    text: str,
    source_type: str = "unknown",
    title: str = "Untitled",
    sourceID: str = "unknown",
    importedAt=None,
    min_length: int = 120,
    max_length: int = 1200,
    overlap: int = 200
) -> List[Dict[str, Any]]:
    """
    Construit une sortie standardisée à partir d'un texte déjà extrait/nettoyé.
    """
    segments = segment_universal_text(
        text,
        min_length=min_length,
        max_length=max_length,
        overlap=overlap
    )

    return [
        {
            "segment_id": i,
            "source_type": source_type,
            "title": title,
            "sourceID": sourceID,
            "importedAt": importedAt,
            "text": segment,
            "length": len(segment),
        }
        for i, segment in enumerate(segments, start=1)
    ]