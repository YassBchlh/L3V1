# Version5/back/segmentation/SegDiapo.py
from back.segmentation.SegmentationFallback import build_universal_segments
from typing import List, Dict, Any
import re

from back.extraction.gestionExtraction import DocumentFileSource


class DiaporamaSegmentationError(Exception):
    pass


def validate_text(text: str):
    if not text or not text.strip():
        raise DiaporamaSegmentationError("Texte vide pour le diaporama.")


def normalize_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_by_slides(text: str) -> List[str]:
    """
    Split basé sur :
    --- Slide X ---
    """
    slides = re.split(r"--- Slide \d+ ---", text)
    return [s.strip() for s in slides if s.strip()]


def remove_noise_slides(slides: List[str]) -> List[str]:
    """
    Supprime slides inutiles :
    - trop courtes
    - juste 1 mot
    - numéros
    """
    cleaned = []

    for slide in slides:
        words = slide.split()

        if len(words) < 5:
            continue

        if len(slide) < 30:
            continue

        cleaned.append(slide)

    return cleaned


def merge_small_slides(slides: List[str], min_length: int = 100) -> List[str]:
    merged = []
    buffer = ""

    for slide in slides:
        if len(slide) < min_length:
            if buffer:
                buffer += "\n\n" + slide
            else:
                buffer = slide
        else:
            if buffer:
                merged.append((buffer + "\n\n" + slide).strip())
                buffer = ""
            else:
                merged.append(slide)

    if buffer:
        if merged:
            merged[-1] += "\n\n" + buffer
        else:
            merged.append(buffer)

    return merged


def split_long_slide(slide: str, max_length: int = 1200, overlap: int = 200) -> List[str]:
    if len(slide) <= max_length:
        return [slide]

    chunks = []
    start = 0
    step = max_length - overlap

    while start < len(slide):
        end = min(start + max_length, len(slide))

        if end < len(slide):
            last_break = max(
                slide.rfind("\n\n", start, end),
                slide.rfind(". ", start, end)
            )
            if last_break > start + max_length // 2:
                end = last_break + 1

        chunk = slide[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start += step

    return chunks


def refine_slides(slides: List[str], min_length=100, max_length=1200, overlap=200) -> List[str]:
    slides = merge_small_slides(slides, min_length)

    refined = []
    for slide in slides:
        refined.extend(split_long_slide(slide, max_length, overlap))

    return refined


def segment_diaporama_text(
    text: str,
    min_length: int = 100,
    max_length: int = 1200,
    overlap: int = 200
) -> List[str]:

    validate_text(text)
    text = normalize_text(text)

    slides = split_by_slides(text)

    if not slides:
        raise DiaporamaSegmentationError("Aucune slide détectée.")

    slides = remove_noise_slides(slides)

    if not slides:
        raise DiaporamaSegmentationError("Toutes les slides ont été filtrées.")

    slides = refine_slides(slides, min_length, max_length, overlap)

    return slides


def extract_clean_and_segment_diaporama(
    file_path: str,
    min_length: int = 100,
    max_length: int = 1200,
    overlap: int = 200
) -> List[Dict[str, Any]]:

    try:
        source = DocumentFileSource(file_path, "pdf")
        source.validate()

        extracted_text = source.extract_text()

        source.set_title()
        source.set_sourceID()
        source.set_importedAt()

        try:
            segments = segment_diaporama_text(
                extracted_text,
                min_length,
                max_length,
                overlap
            )

            return [
                {
                    "segment_id": i,
                    "source_type": "diaporama",
                    "title": source.title,
                    "sourceID": source.sourceID,
                    "importedAt": source.importedAt,
                    "text": segment,
                    "length": len(segment),
                }
                for i, segment in enumerate(segments, start=1)
            ]

        except Exception:
            return build_universal_segments(
                text=extracted_text,
                source_type="diaporama",
                title=source.title,
                sourceID=source.sourceID,
                importedAt=source.importedAt,
                min_length=min_length,
                max_length=max_length,
                overlap=overlap
            )

    except Exception as e:
        raise DiaporamaSegmentationError(
            f"Erreur segmentation diaporama : {e}"
        )