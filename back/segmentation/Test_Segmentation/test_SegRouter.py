# Version5/back/segmentation/Test_Segmentation/test_SegRouter.py
"""
Tests unitaires — SegRouter.py

Ce fichier teste toutes les fonctions du module SegRouter,
qui joue le rôle d'aiguilleur : il reçoit une ressource extraite
et appelle le bon module de segmentation selon le type de source.
En cas d'erreur, il se rabat automatiquement sur le fallback universel.
"""
import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock des dépendances lourdes avant tout import du module testé.
# ---------------------------------------------------------------------------
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
from back.segmentation.SegRouter import (
    _wrap_segments,
    segment_extracted_resource,
)


# ===========================================================================
# _wrap_segments
# ===========================================================================

class TestWrapSegments:
    def test_structure_complete(self):
        # Chaque segment doit contenir toutes les clés attendues :
        # segment_id, source_type, title, sourceID, importedAt, text, length.
        result = _wrap_segments(["seg1", "seg2"], "txt", "Titre", "id1", "2024")
        assert len(result) == 2
        for seg in result:
            assert "segment_id" in seg
            assert "source_type" in seg
            assert "title" in seg
            assert "sourceID" in seg
            assert "text" in seg
            assert "length" in seg

    def test_ids_incrementaux(self):
        # Les segment_id doivent être incrémentaux en commençant à 1.
        # Cela permet d'identifier chaque segment de façon unique.
        result = _wrap_segments(["a", "b", "c"], "web", "T", "x", None)
        assert [s["segment_id"] for s in result] == [1, 2, 3]

    def test_source_type_transmis(self):
        # Le source_type fourni doit être correctement transmis
        # à chaque segment pour permettre la traçabilité.
        result = _wrap_segments(["texte"], "youtube", "Titre", "id1", None)
        assert result[0]["source_type"] == "youtube"

    def test_longueur_coherente(self):
        # Le champ "length" doit correspondre exactement
        # à la longueur réelle du texte de chaque segment.
        result = _wrap_segments(["Bonjour"], "txt", "T", "x", None)
        assert result[0]["length"] == len("Bonjour")

    def test_liste_vide(self):
        # Une liste de segments vide doit retourner une liste vide
        # sans lever d'exception.
        result = _wrap_segments([], "txt", "T", "x", None)
        assert result == []


# ===========================================================================
# segment_extracted_resource
# ===========================================================================

class TestSegmentExtractedResource:

    def _base_resource(self, source_type, text="Contenu.\n\nDeuxième paragraphe avec contenu."):
        # Helper pour créer une ressource de base avec les champs requis.
        return {
            "type": source_type,
            "text": text,
            "title": "Test",
            "sourceID": "id1",
            "importedAt": "2024-01-01",
        }

    def test_texte_vide_retourne_liste_vide(self):
        # Une ressource sans texte ne peut pas être segmentée.
        # La fonction doit retourner une liste vide immédiatement
        # sans appeler aucun module de segmentation.
        resource = self._base_resource("txt", text="")
        result = segment_extracted_resource(resource)
        assert result == []

    def test_type_txt(self):
        # Pour un fichier texte, le router doit appeler segment_clean_text
        # et retourner des segments avec source_type "txt".
        resource = self._base_resource("txt")
        result = segment_extracted_resource(resource, min_length=5)
        assert len(result) >= 1
        assert all(s["source_type"] == "txt" for s in result)

    def test_type_md(self):
        # Pour un fichier markdown, le router doit appeler segment_clean_text
        # (même traitement que txt) et retourner des segments valides.
        resource = self._base_resource(
            "md", "# Titre\nContenu.\n\n# Autre\nAutre contenu."
        )
        result = segment_extracted_resource(resource, min_length=5)
        assert len(result) >= 1

    def test_type_docx(self):
        # Pour un fichier Word, le router doit appeler segment_clean_text
        # et retourner des segments avec source_type "docx".
        resource = self._base_resource("docx")
        result = segment_extracted_resource(resource, min_length=5)
        assert len(result) >= 1
        assert all(s["source_type"] == "docx" for s in result)

    def test_type_website(self):
        # Pour une page web, le router doit appeler segment_web_text
        # et retourner des segments avec source_type "website".
        resource = self._base_resource("website")
        result = segment_extracted_resource(resource, min_length=5)
        assert len(result) >= 1
        assert all(s["source_type"] == "website" for s in result)

    def test_type_youtube(self):
        # Pour une vidéo YouTube, le router doit appeler segment_youtube_text
        # avec des paramètres adaptés (min_length=180, max_length=1500).
        resource = self._base_resource("youtube")
        result = segment_extracted_resource(resource, min_length=5)
        assert len(result) >= 1
        assert all(s["source_type"] == "youtube" for s in result)

    def test_type_pdf_diaporama_avec_subtype(self):
        # Pour un PDF de type diaporama (subtype="diaporama"),
        # le router doit appeler segment_diaporama_text.
        resource = {
            "type": "pdf",
            "subtype": "diaporama",
            "text": (
                "--- Slide 1 ---\nContenu long et valide pour la slide un ici.\n"
                "--- Slide 2 ---\nContenu long et valide pour la slide deux aussi."
            ),
            "title": "Diapo",
            "sourceID": "d1",
            "importedAt": None,
        }
        result = segment_extracted_resource(resource, min_length=5)
        assert len(result) >= 1
        assert all(s["source_type"] == "diaporama" for s in result)

    def test_type_pdf_diaporama_avec_marqueur_slide(self):
        # Si le texte contient "--- Slide" même sans subtype explicite,
        # le router doit détecter que c'est un diaporama et le traiter
        # comme tel.
        resource = {
            "type": "pdf",
            "text": (
                "--- Slide 1 ---\nContenu long et valide pour la slide un ici.\n"
                "--- Slide 2 ---\nContenu long et valide pour la slide deux aussi."
            ),
            "title": "Diapo",
            "sourceID": "d1",
            "importedAt": None,
        }
        result = segment_extracted_resource(resource, min_length=5)
        assert len(result) >= 1

    def test_type_pdf_normal(self):
        # Pour un PDF normal (sans marqueurs de slides),
        # le router doit utiliser build_universal_segments.
        resource = self._base_resource("pdf")
        result = segment_extracted_resource(resource, min_length=5)
        assert len(result) >= 1
        assert all(s["source_type"] == "pdf" for s in result)

    def test_type_inconnu_utilise_fallback(self):
        # Pour un type non reconnu, le router doit utiliser
        # build_universal_segments comme fallback universel
        # plutôt que de lever une exception.
        resource = self._base_resource("xyz")
        result = segment_extracted_resource(resource, min_length=5)
        assert len(result) >= 1

    def test_erreur_interne_utilise_fallback(self):
        # Si le module de segmentation appelé lève une exception,
        # le router doit se rabattre sur build_universal_segments
        # pour garantir la robustesse du pipeline.
        resource = self._base_resource("txt")
        with patch("SegRouter.segment_clean_text", side_effect=Exception("Crash inattendu")):
            result = segment_extracted_resource(resource, min_length=5)
        assert isinstance(result, list)

    def test_metadonnees_transmises(self):
        # Les métadonnées (title, sourceID, importedAt) doivent être
        # correctement transmises depuis la ressource vers chaque segment.
        resource = {
            "type": "txt",
            "text": "Contenu.\n\nDeuxième paragraphe.",
            "title": "Mon Titre",
            "sourceID": "monID",
            "importedAt": "2024-06-01",
        }
        result = segment_extracted_resource(resource, min_length=5)
        assert all(s["title"] == "Mon Titre" for s in result)
        assert all(s["sourceID"] == "monID" for s in result)

    def test_segment_id_commence_a_1(self):
        # Le premier segment_id doit toujours valoir 1
        # pour respecter la convention de numérotation.
        resource = self._base_resource("txt")
        result = segment_extracted_resource(resource, min_length=5)
        assert result[0]["segment_id"] == 1

    def test_longueur_coherente(self):
        # Le champ "length" de chaque segment doit correspondre
        # exactement à la longueur réelle du texte.
        resource = self._base_resource("txt")
        result = segment_extracted_resource(resource, min_length=5)
        for seg in result:
            assert seg["length"] == len(seg["text"])