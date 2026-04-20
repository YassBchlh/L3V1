# Version5/back/extraction/Test_Extraction/test_gestionExtraction.py
"""
BOUCHLEH Yassine
Tests unitaires pour gestionExtraction.py
Couvre : fonctions de validation, WebLinkSource, ImageSource,
         YoutubeSource, DocumentFileSource, extraction_final
"""

import os
import sys
import hashlib
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open, call
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Les mocks doivent rester dans sys.modules TOUTE la durée de la session.
# Un `with patch.dict(...)` est un contexte temporaire : les mocks disparaissent
# après le bloc, ce qui force un re-import réel lors de chaque `patch(...)` dans
# les tests → ModuleNotFoundError. On injecte donc directement dans sys.modules.
# ---------------------------------------------------------------------------

_MODULES_A_MOCKER = [
    "trafilatura",
    "yt_dlp",
    "yt_dlp.utils",
    "faster_whisper",
    "docling",
    "docling.document_converter",
    "docling.datamodel",
    "docling.datamodel.pipeline_options",
    "docling.datamodel.base_models",
    "cairosvg",
    "fitz",
    "youtube_transcript_api",
]

for _mod in _MODULES_A_MOCKER:
    sys.modules[_mod] = MagicMock()

# yt_dlp.utils.DownloadError DOIT être une vraie classe d'exception.
# Python refuse un MagicMock dans une clause `except` → TypeError.
# On crée une classe factice et on l'injecte dans les deux endroits
# où le code y accède : `yt_dlp.utils.DownloadError` et le module `yt_dlp.utils`.
class _FakeDownloadError(Exception):
    pass

sys.modules["yt_dlp"].utils.DownloadError = _FakeDownloadError
sys.modules["yt_dlp.utils"].DownloadError = _FakeDownloadError

# Ajout du répertoire courant au path pour importer le module

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Import du module testé — toutes les dépendances lourdes sont déjà mockées
import gestionExtraction as ge
from gestionExtraction import (
    valider_fichier_local,
    valider_url,
    valider_url_youtube,
    WebLinkSource,
    ImageSource,
    YoutubeSource,
    DocumentFileSource,
    ResourceValidationError,
    ExtractionError,
    extraction_final,
)


# ===========================================================================
# ░░░  SECTION 1 – Fonctions de validation standalone  ░░░
# ===========================================================================

class TestValiderFichierLocal:
    """Tests pour valider_fichier_local()"""

    def test_fichier_inexistant(self, tmp_path):
        with pytest.raises(ResourceValidationError, match="introuvable"):
            valider_fichier_local(str(tmp_path / "ghost.pdf"), (".pdf",))

    def test_chemin_est_un_dossier(self, tmp_path):
        with pytest.raises(ResourceValidationError, match="ne pointe pas"):
            valider_fichier_local(str(tmp_path), (".pdf",))

    def test_extension_non_autorisee(self, tmp_path):
        f = tmp_path / "doc.xyz"
        f.write_text("contenu")
        with pytest.raises(ResourceValidationError, match="non supportée"):
            valider_fichier_local(str(f), (".pdf", ".docx"))

    def test_fichier_valide(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-")
        # Ne doit lever aucune exception
        valider_fichier_local(str(f), (".pdf",))

    def test_extension_case_insensitive(self, tmp_path):
        """L'extension est normalisée en minuscules."""
        f = tmp_path / "IMAGE.PNG"
        f.write_bytes(b"\x89PNG")
        valider_fichier_local(str(f), (".png",))


class TestValiderUrl:
    """Tests pour valider_url()"""

    @patch("gestionExtraction.requests.head")
    def test_url_valide_200(self, mock_head):
        mock_head.return_value = MagicMock(status_code=200)
        valider_url("https://example.com/page")  # pas d'exception

    @patch("gestionExtraction.requests.head")
    @patch("gestionExtraction.requests.get")
    def test_url_403_fallback_get_200(self, mock_get, mock_head):
        """Si HEAD retourne 403, on retente avec GET."""
        mock_head.return_value = MagicMock(status_code=403)
        mock_get.return_value = MagicMock(status_code=200)
        valider_url("https://example.com/page")  # pas d'exception
        mock_get.assert_called_once()

    @patch("gestionExtraction.requests.head")
    @patch("gestionExtraction.requests.get")
    def test_url_403_fallback_get_aussi_erreur(self, mock_get, mock_head):
        """Si HEAD retourne 403 et GET retourne aussi une erreur."""
        mock_head.return_value = MagicMock(status_code=403)
        mock_get.return_value = MagicMock(status_code=500)
        with pytest.raises(ResourceValidationError, match="inaccessible"):
            valider_url("https://example.com/page")

    @patch("gestionExtraction.requests.head")
    def test_url_404(self, mock_head):
        mock_head.return_value = MagicMock(status_code=404)
        with pytest.raises(ResourceValidationError, match="inaccessible"):
            valider_url("https://example.com/not-found")

    def test_schema_http_invalide(self):
        with pytest.raises(ResourceValidationError, match="schéma incorrect"):
            valider_url("ftp://example.com/file")

    def test_url_sans_domaine(self):
        with pytest.raises(ResourceValidationError, match="domaine manquant"):
            valider_url("https://")

    @patch("gestionExtraction.requests.head", side_effect=__import__("requests").exceptions.ConnectionError)
    def test_connexion_impossible(self, _):
        with pytest.raises(ResourceValidationError, match="Impossible de se connecter"):
            valider_url("https://site-inexistant-xyz.io")

    @patch("gestionExtraction.requests.head", side_effect=__import__("requests").exceptions.Timeout)
    def test_timeout(self, _):
        with pytest.raises(ResourceValidationError, match="Timeout"):
            valider_url("https://slow-site.io")

    @patch("gestionExtraction.requests.head", side_effect=__import__("requests").exceptions.RequestException("erreur réseau"))
    def test_request_exception_generique(self, _):
        """Les RequestException non spécifiques sont aussi attrapées."""
        with pytest.raises(ResourceValidationError, match="Erreur HTTP"):
            valider_url("https://broken-site.io")


class TestValiderUrlYoutube:
    """Tests pour valider_url_youtube()"""

    def test_url_sans_id_video(self):
        with pytest.raises(ResourceValidationError, match="identifiant vidéo"):
            valider_url_youtube("https://www.youtube.com/watch")

    def test_url_youtu_be_valide(self):
        """URL courte youtu.be reconnue comme potentiellement valide (format ok)."""
        mock_info = {"id": "abc123", "title": "Test"}
        with patch("gestionExtraction.yt_dlp.YoutubeDL") as mock_ydl:
            mock_ydl.return_value.__enter__.return_value.extract_info.return_value = mock_info
            valider_url_youtube("https://youtu.be/abc123")  # pas d'exception

    def test_video_introuvable(self):
        ge.yt_dlp.utils.DownloadError = _FakeDownloadError
        with patch("gestionExtraction.yt_dlp.YoutubeDL") as mock_ydl:
            mock_ydl.return_value.__enter__.return_value.extract_info.return_value = None
            with pytest.raises(ResourceValidationError, match="introuvable"):
                valider_url_youtube("https://www.youtube.com/watch?v=FAKEID")

    def test_yt_dlp_download_error(self):
        ge.yt_dlp.utils.DownloadError = _FakeDownloadError
        with patch("gestionExtraction.yt_dlp.YoutubeDL") as mock_ydl:
            mock_ydl.return_value.__enter__.return_value.extract_info.side_effect = \
                _FakeDownloadError("not found")
            with pytest.raises(ResourceValidationError, match="inaccessible"):
                valider_url_youtube("https://www.youtube.com/watch?v=FAKEID")


# ===========================================================================
# ░░░  SECTION 2 – WebLinkSource  ░░░
# ===========================================================================

class TestWebLinkSource:
    """Tests pour la classe WebLinkSource"""

    URL = "https://example.com/article"

    def _source(self):
        return WebLinkSource(self.URL)

    # --- set_sourceID ---

    def test_set_source_id_est_md5_stable(self):
        src = self._source()
        src.set_sourceID()
        # Deux appels sur la même URL → même ID
        src2 = WebLinkSource(self.URL)
        src2.set_sourceID()
        assert src.sourceID == src2.sourceID

    def test_set_source_id_normalise_url(self):
        """Les URLs identiques avec trailing slash ou casse différente donnent le même ID."""
        src1 = WebLinkSource("https://EXAMPLE.COM/article/")
        src2 = WebLinkSource("https://example.com/article/")
        src1.set_sourceID()
        src2.set_sourceID()
        assert src1.sourceID == src2.sourceID

    # --- set_title ---

    @patch("gestionExtraction.trafilatura.fetch_url", return_value="<html>…</html>")
    @patch("gestionExtraction.trafilatura.extract_metadata")
    def test_set_title(self, mock_meta, _):
        mock_meta.return_value = MagicMock(title="Mon Article")
        src = self._source()
        src.set_title()
        assert src.title == "Mon Article"

    @patch("gestionExtraction.trafilatura.fetch_url", return_value="<html>…</html>")
    @patch("gestionExtraction.trafilatura.extract_metadata")
    def test_set_title_metadata_none(self, mock_meta, _):
        """Si les métadonnées sont None, le titre est l'URL."""
        mock_meta.return_value = None
        src = self._source()
        src.set_title()
        assert src.title == self.URL

    @patch("gestionExtraction.trafilatura.fetch_url", return_value="<html>…</html>")
    @patch("gestionExtraction.trafilatura.extract_metadata")
    def test_set_title_metadata_sans_titre(self, mock_meta, _):
        """Si metadata.title est None, le titre est l'URL."""
        mock_meta.return_value = MagicMock(title=None)
        src = self._source()
        src.set_title()
        assert src.title == self.URL

    # --- validate ---

    @patch("gestionExtraction.valider_url")
    def test_validate_appelle_valider_url(self, mock_val):
        src = self._source()
        src.validate()
        mock_val.assert_called_once_with(self.URL)

    # --- extract_text ---

    @patch("gestionExtraction.trafilatura.fetch_url", return_value="<html>contenu</html>")
    @patch("gestionExtraction.trafilatura.extract", return_value="## Titre\nContenu de l'article")
    def test_extract_text_retourne_markdown(self, _, __):
        src = self._source()
        result = src.extract_text()
        assert "Contenu de l'article" in result

    @patch("gestionExtraction.trafilatura.fetch_url", return_value=None)
    def test_extract_text_echec_telechargement_leve_exception(self, _):
        """Le téléchargement échoué lève désormais une ExtractionError."""
        src = self._source()
        with pytest.raises(ExtractionError, match="Échec du téléchargement"):
            src.extract_text()

    @patch("gestionExtraction.trafilatura.fetch_url", return_value="<html></html>")
    @patch("gestionExtraction.trafilatura.extract", return_value=None)
    def test_extract_text_contenu_vide(self, _, __):
        src = self._source()
        assert src.extract_text() == "Contenu illisible ou vide"

    # --- clean_text ---

    def test_clean_text_reduit_sauts_de_ligne(self):
        src = self._source()
        texte = "Ligne A\n\n\n\nLigne B"
        assert "\n\n\n" not in src.clean_text(texte)

    def test_clean_text_reduit_espaces(self):
        src = self._source()
        assert src.clean_text("mot   mot") == "mot mot"

    def test_clean_text_strip(self):
        src = self._source()
        assert src.clean_text("  texte  ") == "texte"

    def test_clean_text_chaine_vide(self):
        """Une chaîne vide ou None retourne une chaîne vide."""
        src = self._source()
        assert src.clean_text("") == ""
        assert src.clean_text(None) == ""

    # --- final_info ---

    @patch.object(WebLinkSource, "set_title")
    @patch.object(WebLinkSource, "set_sourceID")
    @patch.object(WebLinkSource, "set_importedAt")
    @patch.object(WebLinkSource, "extract_text", return_value="contenu")
    @patch.object(WebLinkSource, "clean_text", return_value="contenu propre")
    def test_final_info_structure(self, *_):
        src = self._source()
        info = src.final_info()
        assert info["type"] == "website"
        assert "title" in info
        assert "sourceID" in info
        assert "importedAt" in info
        assert info["text"] == "contenu propre"


# ===========================================================================
# ░░░  SECTION 3 – ImageSource  ░░░
# ===========================================================================

class TestImageSource:
    """Tests pour la classe ImageSource"""

    def _source(self, path="photo.jpg"):
        return ImageSource(path)

    # --- set_title ---

    def test_set_title_fichier_local(self):
        src = self._source("mon_image.jpg")
        src.set_title()
        assert src.title == "mon_image"

    def test_set_title_url(self):
        """Le code corrigé utilise "https://" et fait .replace("-", " ")."""
        src = self._source("https://example.com/banner-hero.png")
        src.set_title()
        assert src.title == "banner hero"

    def test_set_title_url_sans_nom_fichier(self):
        """Si l'URL n'a pas de nom de fichier lisible, on obtient un fallback."""
        src = self._source("https://example.com/")
        src.set_title()
        assert src.title == "image distante"

    # --- set_sourceID ---

    def test_set_source_id_local_est_md5(self):
        """Pour un fichier local, le sourceID est le MD5 du chemin absolu."""
        src = self._source("photo.jpg")
        src.set_sourceID()
        expected = hashlib.md5(os.path.abspath("photo.jpg").encode()).hexdigest()
        assert src.sourceID == expected
        assert len(src.sourceID) == 32

    def test_set_source_id_url_est_md5(self):
        """Pour une URL, le sourceID est le MD5 de l'URL nettoyée."""
        src = self._source("https://example.com/img.jpg")
        src.set_sourceID()
        expected = hashlib.md5("https://example.com/img.jpg".encode()).hexdigest()
        assert src.sourceID == expected

    # --- validate ---

    @patch("gestionExtraction.valider_url")
    def test_validate_url(self, mock_val):
        src = self._source("https://example.com/img.jpg")
        src.validate()
        mock_val.assert_called_once()

    @patch("gestionExtraction.valider_fichier_local")
    def test_validate_fichier_local(self, mock_val):
        src = self._source("local/photo.png")
        src.validate()
        mock_val.assert_called_once()

    # --- extract_text ---

    def test_extract_text_retourne_fallback(self):
        """Sans modèle multimodal, extract_text retourne un texte descriptif."""
        src = self._source("photo.jpg")
        result = src.extract_text()
        assert "photo.jpg" in result
        assert "indisponible" in result.lower() or "Image importée" in result

    def test_extract_text_url_distante(self):
        """Même pour une URL, le fallback fonctionne."""
        src = self._source("https://example.com/banner.png")
        result = src.extract_text()
        assert "banner.png" in result

    # --- clean_text ---

    def test_clean_text_strip(self):
        src = self._source()
        assert src.clean_text("  texte  ") == "texte"

    def test_clean_text_chaine_vide(self):
        src = self._source()
        assert src.clean_text("") == ""
        assert src.clean_text(None) == ""

    # --- final_info ---

    @patch.object(ImageSource, "set_title")
    @patch.object(ImageSource, "set_sourceID")
    @patch.object(ImageSource, "set_importedAt")
    @patch.object(ImageSource, "extract_text", return_value="desc image")
    def test_final_info_type_image(self, *_):
        src = self._source()
        info = src.final_info()
        assert info["type"] == "image"
        assert info["text"] == "desc image"


# ===========================================================================
# ░░░  SECTION 4 – YoutubeSource  ░░░
# ===========================================================================

class TestYoutubeSource:
    """Tests pour la classe YoutubeSource"""

    URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def _source(self):
        return YoutubeSource(self.URL, "fr")

    # --- set_title ---

    def test_set_title(self):
        with patch("gestionExtraction.yt_dlp.YoutubeDL") as mock_ydl:
            mock_ydl.return_value.__enter__.return_value.extract_info.return_value = \
                {"title": "Never Gonna Give You Up"}
            src = self._source()
            src.set_title()
            assert src.title == "Never Gonna Give You Up"

    def test_set_title_sans_cle_title(self):
        """Si la clé 'title' est absente, on obtient le fallback."""
        with patch("gestionExtraction.yt_dlp.YoutubeDL") as mock_ydl:
            mock_ydl.return_value.__enter__.return_value.extract_info.return_value = {}
            src = self._source()
            src.set_title()
            assert src.title == "Vidéo YouTube"

    # --- set_sourceID ---

    def test_set_source_id_extrait_video_id(self):
        src = self._source()
        src.set_sourceID()
        assert src.sourceID == "dQw4w9WgXcQ"

    def test_set_source_id_url_avec_parametres_extra(self):
        src = YoutubeSource(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s", "fr"
        )
        src.set_sourceID()
        assert src.sourceID == "dQw4w9WgXcQ"

    def test_set_source_id_url_youtu_be(self):
        """Les URLs courtes youtu.be sont aussi supportées."""
        src = YoutubeSource("https://youtu.be/abc123?t=10", "fr")
        src.set_sourceID()
        assert src.sourceID == "abc123"

    def test_set_source_id_url_inconnue_fallback_md5(self):
        """Si ni v= ni youtu.be/ n'est trouvé, on utilise un MD5."""
        src = YoutubeSource("https://unknown-format.com/video", "fr")
        src.set_sourceID()
        expected = hashlib.md5("https://unknown-format.com/video".encode()).hexdigest()
        assert src.sourceID == expected

    # --- validate ---

    @patch("gestionExtraction.valider_url_youtube")
    def test_validate_appelle_valider_url_youtube(self, mock_val):
        src = self._source()
        src.validate()
        mock_val.assert_called_once_with(self.URL)

    # --- extract_text via sous-titres ---

    def test_extract_text_sous_titres_disponibles(self):
        snippet = MagicMock()
        snippet.text = "Bonjour"
        snippet2 = MagicMock()
        snippet2.text = "le monde"

        mock_ytt = MagicMock()
        mock_transcript = MagicMock()
        mock_transcript.fetch.return_value = [snippet, snippet2]
        mock_ytt.list.return_value.find_transcript.return_value = mock_transcript

        with patch("gestionExtraction.YouTubeTranscriptApi", return_value=mock_ytt):
            src = self._source()
            result = src.extract_text()
        assert "Bonjour" in result
        assert "le monde" in result

    def test_extract_text_fallback_whisper(self):
        """Si les sous-titres échouent, on appelle extract_with_whisper."""
        with patch("gestionExtraction.YouTubeTranscriptApi", side_effect=Exception("no transcript")):
            with patch.object(YoutubeSource, "extract_with_whisper", return_value="transcription whisper") as mock_w:
                src = self._source()
                result = src.extract_text()
        mock_w.assert_called_once()
        assert result == "transcription whisper"

    # --- clean_text (regex, plus de LLM) ---

    def test_clean_text_supprime_espaces_insecables(self):
        src = self._source()
        result = src.clean_text("mot\xa0mot")
        assert "\xa0" not in result

    def test_clean_text_reduit_espaces_multiples(self):
        src = self._source()
        result = src.clean_text("mot    mot")
        # Après regex \s+ → " " et ponctuation → newline
        assert "    " not in result

    def test_clean_text_ajoute_newline_apres_ponctuation(self):
        src = self._source()
        result = src.clean_text("Phrase un. Phrase deux.")
        assert "\n" in result

    def test_clean_text_chaine_vide(self):
        src = self._source()
        assert src.clean_text("") == ""
        assert src.clean_text(None) == ""

    # --- final_info ---

    @patch.object(YoutubeSource, "set_title")
    @patch.object(YoutubeSource, "set_sourceID")
    @patch.object(YoutubeSource, "set_importedAt")
    @patch.object(YoutubeSource, "extract_text", return_value="transcription")
    @patch.object(YoutubeSource, "clean_text", return_value="transcription nettoyée")
    def test_final_info_type_youtube(self, *_):
        src = self._source()
        info = src.final_info()
        assert info["type"] == "Youtube"
        assert info["text"] == "transcription nettoyée"


# ===========================================================================
# ░░░  SECTION 5 – DocumentFileSource  ░░░
# ===========================================================================

class TestDocumentFileSource:
    """Tests pour la classe DocumentFileSource"""

    def _source(self, path="doc.pdf", fmt=".pdf"):
        return DocumentFileSource(path, fmt)

    # --- set_title ---

    def test_set_title_sans_extension(self):
        src = self._source("rapport_annuel.pdf")
        src.set_title()
        assert src.title == "rapport_annuel"

    # --- set_sourceID ---

    def test_set_source_id_est_md5_du_contenu(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_bytes(b"hello")
        src = DocumentFileSource(str(f), ".txt")
        src.set_sourceID()
        expected = hashlib.md5(b"hello").hexdigest()
        assert src.sourceID == expected

    # --- validate ---

    @patch("gestionExtraction.valider_fichier_local")
    def test_validate_appelle_valider_fichier_local(self, mock_val):
        src = self._source("doc.pdf")
        src.validate()
        mock_val.assert_called_once()

    # --- extract_text : .txt / .md ---

    def test_extract_text_txt(self, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("Contenu texte", encoding="utf-8")
        src = DocumentFileSource(str(f), ".txt")
        assert src.extract_text() == "Contenu texte"

    def test_extract_text_md(self, tmp_path):
        f = tmp_path / "readme.md"
        f.write_text("# Titre\nContenu", encoding="utf-8")
        src = DocumentFileSource(str(f), ".md")
        assert "# Titre" in src.extract_text()

    def test_extract_text_fichier_introuvable(self):
        src = self._source("/chemin/inexistant.txt", ".txt")
        with pytest.raises(FileNotFoundError):
            src.extract_text()

    def test_extract_text_extension_non_supportee(self, tmp_path):
        f = tmp_path / "archive.zip"
        f.write_bytes(b"PK")
        src = DocumentFileSource(str(f), ".zip")
        with pytest.raises(ValueError, match="non supporté"):
            src.extract_text()

    # --- extract_text : PDF texte ---

    def test_extract_text_pdf_texte(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4")
        src = DocumentFileSource(str(f), ".pdf")

        mock_result = MagicMock()
        mock_result.document.export_to_markdown.return_value = "# PDF Markdown"

        with patch.object(src, "detecter_type_pdf", return_value="texte"), \
             patch("gestionExtraction.DocumentConverter") as mock_conv:
            mock_conv.return_value.convert.return_value = mock_result
            result = src.extract_text()
        assert "# PDF Markdown" in result

    # --- extract_text : PDF scanné ---

    def test_extract_text_pdf_scanne(self, tmp_path):
        f = tmp_path / "scan.pdf"
        f.write_bytes(b"%PDF-1.4")
        src = DocumentFileSource(str(f), ".pdf")

        mock_result = MagicMock()
        mock_result.document.export_to_text.return_value = "texte OCR brut"

        with patch.object(src, "detecter_type_pdf", return_value="scanne"), \
             patch("gestionExtraction.DocumentConverter") as mock_conv:
            mock_conv.return_value.convert.return_value = mock_result
            result = src.extract_text()
        assert result == "texte OCR brut"

    # --- extract_text : PDF diaporama ---

    def test_extract_text_pdf_diaporama(self, tmp_path):
        f = tmp_path / "slides.pdf"
        f.write_bytes(b"%PDF-1.4")
        src = DocumentFileSource(str(f), ".pdf")

        with patch.object(src, "detecter_type_pdf", return_value="diaporama"), \
             patch.object(src, "_extraire_diaporama", return_value="--- Slide 1 ---\nTitre") as mock_dia:
            result = src.extract_text()
        mock_dia.assert_called_once()
        assert "Slide 1" in result

    # --- detecter_type_pdf ---

    def _mock_fitz_doc(self, texte_par_page, is_landscape=False, creator=""):
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=len(texte_par_page))
        mock_doc.metadata = {"creator": creator, "producer": ""}

        pages = []
        for texte in texte_par_page:
            p = MagicMock()
            p.get_text.return_value = texte
            p.rect.width = 842 if is_landscape else 595
            p.rect.height = 595 if is_landscape else 842
            pages.append(p)

        mock_doc.__iter__ = MagicMock(return_value=iter(pages))
        return mock_doc

    def test_detecter_type_pdf_scanne(self, tmp_path):
        f = tmp_path / "scan.pdf"
        f.write_bytes(b"%PDF")
        src = DocumentFileSource(str(f), ".pdf")
        doc = self._mock_fitz_doc(["", "  "])
        with patch("gestionExtraction.fitz.open", return_value=doc):
            assert src.detecter_type_pdf() == "scanne"

    def test_detecter_type_pdf_texte(self, tmp_path):
        f = tmp_path / "texte.pdf"
        f.write_bytes(b"%PDF")
        src = DocumentFileSource(str(f), ".pdf")
        doc = self._mock_fitz_doc(["Paragraphe " * 30, "Autre contenu " * 30])
        with patch("gestionExtraction.fitz.open", return_value=doc):
            assert src.detecter_type_pdf() == "texte"

    def test_detecter_type_pdf_diaporama_par_createur(self, tmp_path):
        f = tmp_path / "slides.pdf"
        f.write_bytes(b"%PDF")
        src = DocumentFileSource(str(f), ".pdf")
        doc = self._mock_fitz_doc(["Slide content. " * 8], creator="Microsoft PowerPoint")
        with patch("gestionExtraction.fitz.open", return_value=doc):
            assert src.detecter_type_pdf() == "diaporama"

    # --- clean_text (regex pur, plus de LLM) ---

    def test_clean_text_supprime_numeros_page(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF")
        src = DocumentFileSource(str(f), ".pdf")
        texte = "Paragraphe.\n\n42\n\nSuite."
        with patch.object(src, "detecter_type_pdf", return_value="scanne"):
            result = src.clean_text(texte)
        # Le numéro de page seul sur une ligne est supprimé
        assert "42" not in result.split("\n")

    def test_clean_text_reduit_espaces(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF")
        src = DocumentFileSource(str(f), ".pdf")
        with patch.object(src, "detecter_type_pdf", return_value="texte"):
            result = src.clean_text("mot   mot")
        assert "   " not in result

    def test_clean_text_supprime_commentaires_html(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF")
        src = DocumentFileSource(str(f), ".pdf")
        with patch.object(src, "detecter_type_pdf", return_value="texte"):
            result = src.clean_text("Texte <!-- image --> suite")
        assert "<!--" not in result
        assert "-->" not in result

    def test_clean_text_supprime_cases_a_cocher(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF")
        src = DocumentFileSource(str(f), ".pdf")
        with patch.object(src, "detecter_type_pdf", return_value="texte"):
            result = src.clean_text("- [ ] Tâche\n- [x] Fait")
        assert "[ ]" not in result
        assert "[x]" not in result

    def test_clean_text_chaine_vide(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF")
        src = DocumentFileSource(str(f), ".pdf")
        assert src.clean_text("") == ""
        assert src.clean_text(None) == ""

    def test_clean_text_fichier_non_pdf(self, tmp_path):
        """Pour un .docx, clean_text fonctionne aussi (typePDF='texte')."""
        f = tmp_path / "doc.docx"
        f.write_bytes(b"PK")
        src = DocumentFileSource(str(f), ".docx")
        result = src.clean_text("Contenu\xa0avec espace insécable")
        assert "\xa0" not in result

    # --- final_info ---

    @patch.object(DocumentFileSource, "set_title")
    @patch.object(DocumentFileSource, "set_sourceID")
    @patch.object(DocumentFileSource, "set_importedAt")
    @patch.object(DocumentFileSource, "extract_text", return_value="texte pdf")
    @patch.object(DocumentFileSource, "clean_text", return_value="texte pdf nettoyé")
    def test_final_info_type_pdf(self, *_):
        src = DocumentFileSource("rapport.pdf", ".pdf")
        info = src.final_info()
        assert info["type"] == ".pdf"
        assert info["text"] == "texte pdf nettoyé"

    @patch.object(DocumentFileSource, "set_title")
    @patch.object(DocumentFileSource, "set_sourceID")
    @patch.object(DocumentFileSource, "set_importedAt")
    @patch.object(DocumentFileSource, "extract_text", return_value="texte docx")
    @patch.object(DocumentFileSource, "clean_text", return_value="texte docx nettoyé")
    def test_final_info_type_docx(self, *_):
        src = DocumentFileSource("note.docx", ".docx")
        info = src.final_info()
        assert info["type"] == ".docx"


# ===========================================================================
# ░░░  SECTION 6 – extraction_final  ░░░
# ===========================================================================

class TestExtractionFinal:
    """Tests pour la fonction extraction_final()"""

    FAKE_INFO_WEB = {
        "type": "website", "title": "Article", "sourceID": "abc123",
        "importedAt": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        "text": "Contenu web"
    }
    FAKE_INFO_YT = {
        "type": "Youtube", "title": "Vidéo", "sourceID": "dQw4w9WgXcQ",
        "importedAt": datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc),
        "text": "Transcription"
    }

    def test_liste_vide_retourne_chaine_vide(self):
        result = extraction_final([])
        assert result == ""

    def test_fichier_cree_par_defaut(self, tmp_path):
        with patch("gestionExtraction.WebLinkSource") as mock_cls, \
             patch("gestionExtraction.valider_url"), \
             patch("os.getcwd", return_value=str(tmp_path)):
            instance = mock_cls.return_value
            instance.validate.return_value = None
            instance.final_info.return_value = self.FAKE_INFO_WEB

            sortie = extraction_final(
                ["https://example.com"],
                fichier_sortie=str(tmp_path / "out.md")
            )
        assert sortie.endswith(".md")
        assert os.path.exists(sortie)

    def test_contenu_fichier_markdown(self, tmp_path):
        sortie = str(tmp_path / "result.md")
        with patch("gestionExtraction.WebLinkSource") as mock_cls:
            instance = mock_cls.return_value
            instance.validate.return_value = None
            instance.final_info.return_value = self.FAKE_INFO_WEB

            extraction_final(["https://example.com"], fichier_sortie=sortie)

        contenu = Path(sortie).read_text(encoding="utf-8")
        assert "# Extraction des ressources" in contenu
        assert "Article" in contenu
        assert "Contenu web" in contenu

    def test_ressource_non_supportee_genere_erreur(self, tmp_path):
        sortie = str(tmp_path / "result.md")
        # Une ressource non reconnue doit être ignorée (avec message d'erreur)
        result = extraction_final(["fichier.xyz"], fichier_sortie=sortie)
        # Le fichier est quand même créé (avec 0 ressources)
        contenu = Path(sortie).read_text(encoding="utf-8")
        assert "**Nombre de ressources :** 0" in contenu

    def test_plusieurs_ressources_dans_ordre(self, tmp_path):
        sortie = str(tmp_path / "result.md")

        with patch("gestionExtraction.WebLinkSource") as mock_web, \
             patch("gestionExtraction.YoutubeSource") as mock_yt:

            mock_web.return_value.validate.return_value = None
            mock_web.return_value.final_info.return_value = self.FAKE_INFO_WEB

            mock_yt.return_value.validate.return_value = None
            mock_yt.return_value.final_info.return_value = self.FAKE_INFO_YT

            extraction_final(
                ["https://example.com", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
                fichier_sortie=sortie
            )

        contenu = Path(sortie).read_text(encoding="utf-8")
        pos_web = contenu.find("Article")
        pos_yt = contenu.find("Vidéo")
        assert pos_web < pos_yt  # ordre respecté

    def test_erreur_validation_nempêche_pas_les_autres(self, tmp_path):
        """Une ressource invalide ne doit pas bloquer les autres."""
        sortie = str(tmp_path / "result.md")

        with patch("gestionExtraction.WebLinkSource") as mock_web:
            mock_web.return_value.validate.side_effect = ResourceValidationError("URL invalide")
            mock_web.return_value.final_info.return_value = self.FAKE_INFO_WEB

            result = extraction_final(
                ["https://bad-url", "fichier.unsupported"],
                fichier_sortie=sortie
            )
        # Le fichier est créé malgré les erreurs
        assert os.path.exists(sortie)


# ===========================================================================
# ░░░  SECTION 7 – Tests d'intégration légère (sans API externe)  ░░░
# ===========================================================================

class TestIntegration:
    """Tests de bout en bout avec fichiers réels mais sans API externes."""

    def test_workflow_complet_txt(self, tmp_path):
        """Extraction complète d'un fichier .txt sans mock d'API."""
        f = tmp_path / "article.txt"
        f.write_text("Titre\n\nContenu de test pour le podcast.", encoding="utf-8")

        sortie = str(tmp_path / "extraction.md")

        # On mock uniquement valider_fichier_local pour éviter la vérification d'extension
        with patch("gestionExtraction.valider_fichier_local"):
            result = extraction_final([str(f)], fichier_sortie=sortie)

        assert os.path.exists(sortie)
        contenu = Path(sortie).read_text(encoding="utf-8")
        assert "Contenu de test pour le podcast." in contenu

    def test_workflow_complet_md(self, tmp_path):
        f = tmp_path / "notes.md"
        f.write_text("# Section 1\nInfo importante.", encoding="utf-8")
        sortie = str(tmp_path / "extraction.md")

        with patch("gestionExtraction.valider_fichier_local"):
            extraction_final([str(f)], fichier_sortie=sortie)

        contenu = Path(sortie).read_text(encoding="utf-8")
        assert "# Section 1" in contenu


# ===========================================================================
# Point d'entrée
# ===========================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])