# Version5/back/segmentation/SegmentationYT.py
from back.segmentation.SegmentationFallback import build_universal_segments
from typing import List, Dict, Any
import re

from back.extraction.gestionExtraction import YoutubeSource


class YoutubeSegmentationError(Exception):
    """
    Exception levée lorsqu'une erreur survient pendant la segmentation d'un contenu YouTube.
    """
    pass


def validate_text(text: str) -> None:
    """
    Vérifie que le texte n'est pas vide.
    """
    if not text or not text.strip():
        raise YoutubeSegmentationError("Le texte YouTube à segmenter est vide.")


def normalize_text(text: str) -> str:
    """
    Normalisation légère du texte.
    """
    text = text.replace("\xa0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_by_markdown_titles(text: str) -> List[str]:
    """
    Découpe par titres markdown éventuels :
    # Titre
    ## Partie
    """
    sections = re.split(r"(?=^#{1,6}\s+)", text, flags=re.MULTILINE)
    return [section.strip() for section in sections if section.strip()]


def split_by_classic_titles(text: str) -> List[str]:
    """
    Découpe par titres classiques si le LLM a organisé le transcript :
    - Introduction
    - Partie 1
    - Conclusion
    - TITRE EN MAJUSCULES
    """
    pattern = (
        r"(?=^(?:"
        r"\d+(?:\.\d+)*[.)]?\s+.+"
        r"|(?:introduction|conclusion|résumé|partie|chapitre)\b.*"
        r"|[A-ZÀ-ÖÙ-ÛÜÇ][A-ZÀ-ÖÙ-ÛÜÇ\s'’\-]{4,}"
        r")$)"
    )
    sections = re.split(pattern, text, flags=re.MULTILINE | re.IGNORECASE)
    return [section.strip() for section in sections if section.strip()]


def split_by_paragraphs(text: str) -> List[str]:
    """
    Découpe par paragraphes.
    """
    paragraphs = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paragraphs if p.strip()]


def split_by_sentences(text: str) -> List[str]:
    """
    Découpe par phrases.
    """
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def merge_short_segments(segments: List[str], min_length: int = 180) -> List[str]:
    """
    Fusionne les segments trop courts.
    Pour YouTube, on peut prendre un min_length un peu plus grand
    car les phrases seules sont souvent trop pauvres.
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
                buffer += " " + segment
            else:
                buffer = segment
        else:
            if buffer:
                merged.append((buffer + " " + segment).strip())
                buffer = ""
            else:
                merged.append(segment)

    if buffer:
        if merged:
            merged[-1] = (merged[-1] + " " + buffer).strip()
        else:
            merged.append(buffer)

    return merged


def split_long_segment(segment: str, max_length: int = 1500, overlap: int = 250) -> List[str]:
    """
    Découpe un segment trop long avec overlap.
    """
    if max_length <= 0:
        raise YoutubeSegmentationError("max_length doit être strictement positif.")
    if overlap < 0:
        raise YoutubeSegmentationError("overlap doit être positif ou nul.")
    if overlap >= max_length:
        raise YoutubeSegmentationError("overlap doit être strictement inférieur à max_length.")

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
    min_length: int = 180,
    max_length: int = 1500,
    overlap: int = 250
) -> List[str]:
    """
    Raffine la segmentation :
    1. fusionne les segments trop courts
    2. découpe les segments trop longs
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


def segment_youtube_text(
    text: str,
    min_length: int = 180,
    max_length: int = 1500,
    overlap: int = 250
) -> List[str]:
    """
    Segmentation principale pour YouTube :
    1. titres markdown
    2. titres classiques
    3. paragraphes
    4. phrases
    """
    validate_text(text)
    text = normalize_text(text)

    markdown_segments = split_by_markdown_titles(text)
    if len(markdown_segments) >= 2:
        return refine_segments(markdown_segments, min_length, max_length, overlap)

    classic_segments = split_by_classic_titles(text)
    if len(classic_segments) >= 2:
        return refine_segments(classic_segments, min_length, max_length, overlap)

    paragraph_segments = split_by_paragraphs(text)
    if len(paragraph_segments) >= 2:
        return refine_segments(paragraph_segments, min_length, max_length, overlap)

    sentence_segments = split_by_sentences(text)
    if sentence_segments:
        return refine_segments(sentence_segments, min_length, max_length, overlap)

    raise YoutubeSegmentationError("Aucun segment exploitable n'a été trouvé.")


def extract_clean_and_segment_youtube(
    video_url: str,
    transcript_language: str = "fr",
    min_length: int = 180,
    max_length: int = 1500,
    overlap: int = 250
) -> List[Dict[str, Any]]:
    """
    Pipeline complet pour YouTube :
    1. validation
    2. extraction transcript / whisper
    3. nettoyage
    4. segmentation
    """
    try:
        source = YoutubeSource(video_url, transcript_language)
        source.validate()

        extracted_text = source.extract_text()
        cleaned_text = source.clean_text(extracted_text)

        source.set_title()
        source.set_sourceID()
        source.set_importedAt()

        try:
            segments = segment_youtube_text(
                cleaned_text,
                min_length=min_length,
                max_length=max_length,
                overlap=overlap
            )

            return [
                {
                    "segment_id": i,
                    "source_type": "youtube",
                    "title": source.title,
                    "sourceID": source.sourceID,
                    "importedAt": source.importedAt,
                    "text": segment,
                    "length": len(segment),
                    "video_url": video_url
                }
                for i, segment in enumerate(segments, start=1)
            ]

        except Exception:
            return build_universal_segments(
                text=cleaned_text,
                source_type="youtube",
                title=source.title,
                sourceID=source.sourceID,
                importedAt=source.importedAt,
                min_length=min_length,
                max_length=max_length,
                overlap=overlap
            )

    except Exception as e:
        raise YoutubeSegmentationError(
            f"Erreur pendant extraction + nettoyage + segmentation YouTube : {e}"
        )