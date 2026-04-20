# Version5/back/segmentation/SegmentationTxt.py
from back.segmentation.SegmentationFallback import build_universal_segments
from typing import List, Dict, Any
import re

from back.extraction.gestionExtraction import DocumentFileSource


class TextSegmentationError(Exception):
    """
    Exception levée lorsqu'une erreur survient pendant la segmentation du texte.
    """
    pass


def validate_text(text: str) -> None:
    """
    Vérifie que le texte n'est pas vide.
    """
    if not text or not text.strip():
        raise TextSegmentationError("Le texte à segmenter est vide.")


def normalize_text(text: str) -> str:
    """
    Normalisation légère du texte après extraction et nettoyage.
    On garde la structure générale du document.
    """
    text = text.replace("\xa0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_by_markdown_titles(text: str) -> List[str]:
    """
    Découpe par titres markdown :
    # Titre
    ## Sous-titre
    ### Partie
    """
    sections = re.split(r"(?=^#{1,6}\s+)", text, flags=re.MULTILINE)
    return [section.strip() for section in sections if section.strip()]


def split_by_classic_titles(text: str) -> List[str]:
    """
    Découpe par titres classiques souvent trouvés dans des documents extraits :
    - 1 Introduction
    - 1. Introduction
    - 1.1 Méthodes
    - INTRODUCTION
    - CONCLUSION
    """
    pattern = (
        r"(?=^(?:"
        r"\d+(?:\.\d+)*[.)]?\s+.+"
        r"|[A-ZÀ-ÖÙ-ÛÜÇ][A-ZÀ-ÖÙ-ÛÜÇ\s'’\-]{4,}"
        r")$)"
    )
    sections = re.split(pattern, text, flags=re.MULTILINE)
    return [section.strip() for section in sections if section.strip()]


def split_by_paragraphs(text: str) -> List[str]:
    """
    Découpe par paragraphes séparés par une ou plusieurs lignes vides.
    """
    paragraphs = re.split(r"\n\s*\n", text)
    return [paragraph.strip() for paragraph in paragraphs if paragraph.strip()]


def split_by_sentences(text: str) -> List[str]:
    """
    Découpe grossière par phrases.
    Sert de fallback si le document est peu structuré.
    """
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def merge_short_segments(segments: List[str], min_length: int = 120) -> List[str]:
    """
    Fusionne les segments trop courts afin d'éviter des fragments peu exploitables.
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
    Découpe un segment trop long en sous-segments avec overlap.
    On essaie de couper proprement sur une fin de phrase ou un saut de ligne.
    """
    if max_length <= 0:
        raise TextSegmentationError("max_length doit être strictement positif.")
    if overlap < 0:
        raise TextSegmentationError("overlap doit être positif ou nul.")
    if overlap >= max_length:
        raise TextSegmentationError("overlap doit être strictement inférieur à max_length.")

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
    """
    Raffine la segmentation :
    1. fusion des segments trop courts
    2. découpage des segments trop longs
    """
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


def segment_clean_text(
    text: str,
    min_length: int = 120,
    max_length: int = 1200,
    overlap: int = 200
) -> List[str]:
    """
    Segmentation principale pour DOCX / MD / TXT :
    1. titres markdown
    2. titres classiques
    3. paragraphes
    4. phrases en fallback
    """
    validate_text(text)
    text = normalize_text(text)

    markdown_segments = split_by_markdown_titles(text)
    if len(markdown_segments) >= 2:
        return refine_segments(
            markdown_segments,
            min_length=min_length,
            max_length=max_length,
            overlap=overlap
        )

    classic_segments = split_by_classic_titles(text)
    if len(classic_segments) >= 2:
        return refine_segments(
            classic_segments,
            min_length=min_length,
            max_length=max_length,
            overlap=overlap
        )

    paragraph_segments = split_by_paragraphs(text)
    if len(paragraph_segments) >= 2:
        return refine_segments(
            paragraph_segments,
            min_length=min_length,
            max_length=max_length,
            overlap=overlap
        )

    sentence_segments = split_by_sentences(text)
    if sentence_segments:
        return refine_segments(
            sentence_segments,
            min_length=min_length,
            max_length=max_length,
            overlap=overlap
        )

    raise TextSegmentationError("Aucun segment exploitable n'a été trouvé.")


def extract_clean_and_segment_text_document(
    file_path: str,
    file_format: str,
    min_length: int = 120,
    max_length: int = 1200,
    overlap: int = 200
) -> List[Dict[str, Any]]:
    """
    Pipeline complet pour DOCX / MD / TXT :
    1. récupération via DocumentFileSource
    2. validation
    3. extraction
    4. nettoyage
    5. segmentation
    """
    normalized_format = file_format.lower().strip()
    if normalized_format.startswith("."):
        normalized_format = normalized_format[1:]

    if normalized_format not in {"docx", "md", "txt"}:
        raise TextSegmentationError(
            "Ce module gère uniquement les formats DOCX, MD et TXT."
        )

    try:
        source = DocumentFileSource(file_path, normalized_format)
        source.validate()

        extracted_text = source.extract_text()
        cleaned_text = source.clean_text(extracted_text)

        source.set_title()
        source.set_sourceID()
        source.set_importedAt()

        try:
            segments = segment_clean_text(
                cleaned_text,
                min_length=min_length,
                max_length=max_length,
                overlap=overlap
            )

            return [
                {
                    "segment_id": i,
                    "source_type": f".{normalized_format}",
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
                text=cleaned_text,
                source_type=f".{normalized_format}",
                title=source.title,
                sourceID=source.sourceID,
                importedAt=source.importedAt,
                min_length=min_length,
                max_length=max_length,
                overlap=overlap
            )

    except Exception as e:
        raise TextSegmentationError(
            f"Erreur pendant extraction + nettoyage + segmentation : {e}"
        )