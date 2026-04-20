# Version5/back/segmentation/pipeline_segmentation.py
from typing import List, Dict, Any
from pathlib import Path

from back.extraction.gestionExtraction import extraction_final
from back.segmentation.SegFromExtraction import segment_from_extraction_markdown
from back.segmentation.SegmentationWeb import extract_clean_and_segment_webpage

class PipelineError(Exception):
    pass


def _get_latest_extraction_markdown(search_dir: str = ".") -> str:
    """
    Retourne automatiquement le fichier extraction_*.md le plus récent.
    """
    md_files = list(Path(search_dir).glob("extraction_*.md"))

    if not md_files:
        raise PipelineError("Aucun fichier extraction_*.md trouvé.")

    latest_file = max(md_files, key=lambda p: p.stat().st_mtime)
    return str(latest_file)


def run_full_pipeline(resources: List[str]) -> List[Dict[str, Any]]:
    if not resources:
        raise PipelineError("Aucune ressource fournie.")

    all_segments = []

    for res in resources:
        # 🔗 CAS 1 : lien web
        if isinstance(res, str) and res.startswith("http"):
            try:
                web_segments = extract_clean_and_segment_webpage(res)
                print(f"[WEB] {len(web_segments)} segments générés pour {res}")
                all_segments.extend(web_segments)
            except Exception as e:
                print(f"[WEB ERROR] {res} -> {e}")

        # 📄 CAS 2 : fichier
        else:
            try:
                md_path = extraction_final([res])

                if not md_path:
                    print(f"[FILE ERROR] extraction vide pour {res}")
                    continue

                file_segments = segment_from_extraction_markdown(md_path)

                if not file_segments:
                    print(f"[FILE ERROR] aucun segment pour {res}")
                    continue

                print(f"[FILE] {len(file_segments)} segments pour {res}")
                all_segments.extend(file_segments)

            except Exception as e:
                print(f"[FILE ERROR] {res} -> {e}")

    if not all_segments:
        raise PipelineError("Aucun segment généré après segmentation.")

    return all_segments

def run_segmentation_only(md_path: str = None) -> List[Dict[str, Any]]:
    """
    Si md_path est fourni : segmente ce fichier.
    Sinon : prend automatiquement le dernier extraction_*.md.
    """
    if md_path is None:
        md_path = _get_latest_extraction_markdown()

    segments = segment_from_extraction_markdown(md_path)

    if not segments:
        raise PipelineError("Aucun segment généré à partir du markdown.")

    return segments