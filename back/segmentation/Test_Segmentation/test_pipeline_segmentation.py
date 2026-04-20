# Version5/back/segmentation/Test_Segmentation/test_pipeline_segmentation.py
"""
Tests unitaires — pipeline_segmentation.py
"""
import sys
import os
import time
from unittest.mock import MagicMock

_MODULES_A_MOCKER = [
    "docling",
    "docling.document_converter",
    "docling.datamodel",
    "docling.datamodel.pipeline_options",
    "docling.datamodel.base_models",
    "trafilatura",
    "yt_dlp",
    "yt_dlp.utils",
    "faster_whisper",
    "cairosvg",
    "fitz",
    "youtube_transcript_api",
]
for _mod in _MODULES_A_MOCKER:
    sys.modules.setdefault(_mod, MagicMock())

class _FakeDownloadError(Exception):
    pass

sys.modules["yt_dlp"].utils.DownloadError = _FakeDownloadError
sys.modules["yt_dlp.utils"].DownloadError = _FakeDownloadError

import pytest
from unittest.mock import patch
from back.segmentation.pipeline_segmentation import (
    PipelineError,
    _get_latest_extraction_markdown,
    run_full_pipeline,
    run_segmentation_only,
)


class TestGetLatestExtractionMarkdown:
    def test_aucun_fichier_leve_exception(self, tmp_path):
        # Dossier vide → PipelineError car rien à segmenter
        with pytest.raises(PipelineError, match="Aucun fichier"):
            _get_latest_extraction_markdown(str(tmp_path))

    def test_retourne_le_seul_fichier(self, tmp_path):
        # Un seul fichier extraction_*.md → retourné directement
        f = tmp_path / "extraction_test.md"
        f.write_text("contenu")
        result = _get_latest_extraction_markdown(str(tmp_path))
        assert str(f) == result

    def test_retourne_le_plus_recent(self, tmp_path):
        # Plusieurs fichiers → le plus récent est retourné
        f1 = tmp_path / "extraction_old.md"
        f1.write_text("ancien")
        time.sleep(0.05)
        f2 = tmp_path / "extraction_new.md"
        f2.write_text("nouveau")
        result = _get_latest_extraction_markdown(str(tmp_path))
        assert "new" in result

    def test_ignore_fichiers_non_extraction(self, tmp_path):
        # Fichiers ne correspondant pas au pattern → ignorés → exception
        f = tmp_path / "autre_fichier.md"
        f.write_text("contenu")
        with pytest.raises(PipelineError):
            _get_latest_extraction_markdown(str(tmp_path))


class TestRunFullPipeline:
    def test_liste_vide_leve_exception(self):
        # Aucune ressource → PipelineError immédiate
        with pytest.raises(PipelineError, match="Aucune ressource"):
            run_full_pipeline([])

    def test_url_web_traitee(self):
        # URL http → traité par extract_clean_and_segment_webpage
        with patch(
            "back.segmentation.pipeline_segmentation.extract_clean_and_segment_webpage",
            return_value=[{"segment_id": 1, "text": "seg", "source_type": "website"}]
        ) as mock_web:
            result = run_full_pipeline(["https://example.com"])
        mock_web.assert_called_once()
        assert len(result) == 1

    def test_url_web_erreur_ignoree_puis_exception(self):
        # Erreur web → loggée mais si aucun segment → PipelineError
        with patch(
            "back.segmentation.pipeline_segmentation.extract_clean_and_segment_webpage",
            side_effect=Exception("Connexion impossible")
        ):
            with pytest.raises(PipelineError, match="Aucun segment"):
                run_full_pipeline(["https://example.com"])

    def test_fichier_local_traite(self):
        # Fichier local → traité par extraction_final + segment_from_extraction_markdown
        with patch("back.segmentation.pipeline_segmentation.extraction_final", return_value="/tmp/fake.md"), \
             patch(
                 "back.segmentation.pipeline_segmentation.segment_from_extraction_markdown",
                 return_value=[{"segment_id": 1, "text": "seg", "source_type": "pdf"}]
             ):
            result = run_full_pipeline(["document.pdf"])
        assert len(result) == 1

    def test_extraction_vide_ignoree(self):
        # extraction_final retourne None → fichier ignoré → PipelineError
        with patch("back.segmentation.pipeline_segmentation.extraction_final", return_value=None):
            with pytest.raises(PipelineError):
                run_full_pipeline(["document.pdf"])

    def test_segmentation_vide_ignoree(self):
        # segment_from_extraction_markdown retourne [] → PipelineError
        with patch("back.segmentation.pipeline_segmentation.extraction_final", return_value="/tmp/fake.md"), \
             patch(
                 "back.segmentation.pipeline_segmentation.segment_from_extraction_markdown",
                 return_value=[]
             ):
            with pytest.raises(PipelineError, match="Aucun segment"):
                run_full_pipeline(["doc.pdf"])

    def test_aucun_segment_leve_exception(self):
        # Aucun segment produit → PipelineError obligatoire
        with patch("back.segmentation.pipeline_segmentation.extraction_final", return_value="/tmp/fake.md"), \
             patch(
                 "back.segmentation.pipeline_segmentation.segment_from_extraction_markdown",
                 return_value=[]
             ):
            with pytest.raises(PipelineError, match="Aucun segment"):
                run_full_pipeline(["doc.pdf"])

    def test_plusieurs_ressources_mixtes(self):
        # URL + fichier local → segments agrégés dans une seule liste
        with patch(
            "back.segmentation.pipeline_segmentation.extract_clean_and_segment_webpage",
            return_value=[{"segment_id": 1, "text": "web", "source_type": "website"}]
        ), patch(
            "back.segmentation.pipeline_segmentation.extraction_final",
            return_value="/tmp/fake.md"
        ), patch(
            "back.segmentation.pipeline_segmentation.segment_from_extraction_markdown",
            return_value=[{"segment_id": 2, "text": "pdf", "source_type": "pdf"}]
        ):
            result = run_full_pipeline(["https://example.com", "doc.pdf"])
        assert len(result) == 2

    def test_ordre_segments_preserve(self):
        # Les segments apparaissent dans l'ordre des ressources
        with patch(
            "back.segmentation.pipeline_segmentation.extract_clean_and_segment_webpage",
            return_value=[{"segment_id": 1, "text": "web", "source_type": "website"}]
        ), patch(
            "back.segmentation.pipeline_segmentation.extraction_final",
            return_value="/tmp/fake.md"
        ), patch(
            "back.segmentation.pipeline_segmentation.segment_from_extraction_markdown",
            return_value=[{"segment_id": 2, "text": "pdf", "source_type": "pdf"}]
        ):
            result = run_full_pipeline(["https://example.com", "doc.pdf"])
        assert result[0]["source_type"] == "website"
        assert result[1]["source_type"] == "pdf"

    def test_retourne_liste_de_dicts(self):
        # Résultat = liste de dictionnaires
        with patch(
            "back.segmentation.pipeline_segmentation.extract_clean_and_segment_webpage",
            return_value=[{"segment_id": 1, "text": "seg", "source_type": "website"}]
        ):
            result = run_full_pipeline(["https://example.com"])
        assert isinstance(result, list)
        assert all(isinstance(s, dict) for s in result)


class TestRunSegmentationOnly:
    def test_avec_md_path_fourni(self, tmp_path):
        # Chemin fourni explicitement → segmente ce fichier directement
        md_content = (
            "## Ressource 1 — Article\n\n"
            "| **Type** | `website` |\n"
            "| **ID** | `src1` |\n"
            "| **Importé** | 2024-01-01 |\n\n"
            "### Contenu\n\n"
            + ("Contenu suffisant. " * 30) + "\n"
        )
        f = tmp_path / "extraction_test.md"
        f.write_text(md_content, encoding="utf-8")
        result = run_segmentation_only(str(f))
        assert len(result) >= 1

    def test_sans_md_path_prend_le_dernier(self, tmp_path):
        # Sans chemin → appelle _get_latest_extraction_markdown automatiquement
        md_content = (
            "## Ressource 1 — Article\n\n"
            "| **Type** | `txt` |\n"
            "| **ID** | `src1` |\n"
            "| **Importé** | 2024-01-01 |\n\n"
            "### Contenu\n\n"
            + ("Contenu suffisant. " * 30) + "\n"
        )
        f = tmp_path / "extraction_auto.md"
        f.write_text(md_content, encoding="utf-8")

        with patch(
            "back.segmentation.pipeline_segmentation._get_latest_extraction_markdown",
            return_value=str(f)
        ):
            result = run_segmentation_only()
        assert len(result) >= 1

    def test_aucun_segment_leve_exception(self, tmp_path):
        # Contenu vide → PipelineError
        md_content = (
            "## Ressource 1 — Vide\n\n"
            "| **Type** | `txt` |\n"
            "| **ID** | `id1` |\n"
            "| **Importé** | 2024-01-01 |\n\n"
            "### Contenu\n\n"
        )
        f = tmp_path / "extraction_vide.md"
        f.write_text(md_content, encoding="utf-8")
        with pytest.raises(PipelineError, match="Aucun segment"):
            run_segmentation_only(str(f))

    def test_retourne_liste_de_dicts(self, tmp_path):
        # Résultat = liste de dictionnaires
        md_content = (
            "## Ressource 1 — Article\n\n"
            "| **Type** | `website` |\n"
            "| **ID** | `src1` |\n"
            "| **Importé** | 2024-01-01 |\n\n"
            "### Contenu\n\n"
            + ("Contenu suffisant. " * 30) + "\n"
        )
        f = tmp_path / "extraction_test2.md"
        f.write_text(md_content, encoding="utf-8")
        result = run_segmentation_only(str(f))
        assert isinstance(result, list)
        assert all(isinstance(s, dict) for s in result)

    def test_segments_ont_clés_requises(self, tmp_path):
        # Chaque segment contient les clés essentielles
        md_content = (
            "## Ressource 1 — Article\n\n"
            "| **Type** | `website` |\n"
            "| **ID** | `src1` |\n"
            "| **Importé** | 2024-01-01 |\n\n"
            "### Contenu\n\n"
            + ("Contenu suffisant. " * 30) + "\n"
        )
        f = tmp_path / "extraction_keys.md"
        f.write_text(md_content, encoding="utf-8")
        result = run_segmentation_only(str(f))
        for seg in result:
            assert "segment_id" in seg
            assert "text" in seg
            assert "source_type" in seg
            assert "length" in seg