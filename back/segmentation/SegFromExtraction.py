# Version5/back/segmentation/SegFromExtraction.py
from typing import List, Dict, Any
import re


class ExtractionMarkdownParseError(Exception):
    pass


def _normalize_type(raw_type: str) -> str:
    if not raw_type:
        return "unknown"

    raw = raw_type.strip().lower().strip("`")

    mapping = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".txt": "txt",
        ".md": "md",
        "website": "website",
        "youtube": "youtube",
        "image": "image",
    }

    return mapping.get(raw, raw)


def _extract_field(pattern: str, block: str, default: str = "") -> str:
    match = re.search(pattern, block, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    return default


def _clean_content(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_paragraphs(text: str) -> List[str]:
    text = _clean_content(text)
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return paragraphs


def _chunk_text(
    text: str,
    max_chars: int = 900,
    min_chars: int = 220
) -> List[str]:
    """
    Découpe le contenu en chunks raisonnables pour le LLM.
    - garde les paragraphes si possible
    - recoupe les très gros paragraphes par phrases
    """
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return []

    chunks: List[str] = []
    current = ""

    def flush():
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Si le paragraphe est trop gros, on le coupe par phrases
        if len(para) > max_chars:
            sentences = re.split(r"(?<=[.!?])\s+", para)
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue

                candidate = f"{current}\n{sentence}".strip() if current else sentence

                if len(candidate) <= max_chars:
                    current = candidate
                else:
                    flush()
                    current = sentence

            continue

        candidate = f"{current}\n\n{para}".strip() if current else para

        if len(candidate) <= max_chars:
            current = candidate
        else:
            if len(current) >= min_chars:
                flush()
                current = para
            else:
                # si current est trop petit, on force l’ajout
                current = candidate

    flush()
    return [c for c in chunks if c.strip()]


def parse_extraction_markdown(md_path: str) -> List[Dict[str, Any]]:
    """
    Parse extraction_*.md écrit par extraction_final().
    Retourne une liste de ressources avec métadonnées + contenu.
    """
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        raise ExtractionMarkdownParseError(f"Fichier introuvable : {md_path}")
    except Exception as e:
        raise ExtractionMarkdownParseError(
            f"Impossible de lire le fichier markdown d'extraction : {e}"
        )

    # Chaque bloc commence par "## Ressource X — ..."
    blocks = re.split(r"(?=^##\s+Ressource\s+\d+\s+—\s+)", content, flags=re.MULTILINE)

    resources: List[Dict[str, Any]] = []

    for block in blocks:
        block = block.strip()
        if not block.startswith("## Ressource"):
            continue

        title = _extract_field(
            r"^##\s+Ressource\s+\d+\s+—\s+(.+)$",
            block,
            default="Sans titre"
        )

        source_type = _extract_field(
            r"^\|\s+\*\*Type\*\*\s+\|\s+`([^`]+)`\s+\|$",
            block,
            default="unknown"
        )
        source_type = _normalize_type(source_type)

        source_id = _extract_field(
            r"^\|\s+\*\*ID\*\*\s+\|\s+`([^`]+)`\s+\|$",
            block,
            default=""
        )

        imported_at = _extract_field(
            r"^\|\s+\*\*Importé\*\*\s+\|\s+(.+?)\s+\|$",
            block,
            default=""
        )

        content_match = re.search(
            r"###\s+Contenu\s*\n+(.*)$",
            block,
            flags=re.MULTILINE | re.DOTALL
        )
        resource_content = content_match.group(1).strip() if content_match else ""
        resource_content = _clean_content(resource_content)

        resources.append({
            "title": title,
            "source_type": source_type,
            "source": source_id or title,
            "source_id": source_id,
            "imported_at": imported_at,
            "content": resource_content,
        })

    return resources


def segment_from_extraction_markdown(md_path: str) -> List[Dict[str, Any]]:
    """
    Segmente le markdown ressource par ressource
    et conserve les métadonnées d’origine.
    """
    resources = parse_extraction_markdown(md_path)

    all_segments: List[Dict[str, Any]] = []
    global_segment_id = 1

    for resource in resources:
        content = resource.get("content", "").strip()
        if not content:
            continue

        chunks = _chunk_text(content)

        for local_index, chunk in enumerate(chunks, start=1):
            chunk = chunk.strip()
            if not chunk:
                continue

            all_segments.append({
                "segment_id": global_segment_id,
                "resource_segment_id": local_index,
                "source": resource.get("source", "unknown_source"),
                "source_type": resource.get("source_type", "unknown"),
                "title": resource.get("title", "Sans titre"),
                "length": len(chunk),
                "text": chunk,
            })
            global_segment_id += 1

    return all_segments