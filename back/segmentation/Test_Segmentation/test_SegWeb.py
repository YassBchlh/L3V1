# Version5/back/segmentation/Test_Segmentation/test_SegWeb.py
"""
Tests unitaires — SegmentationWeb.py
"""
import sys
from unittest.mock import MagicMock

# Mock des dépendances lourdes
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
from back.segmentation.SegmentationWeb import (
    WebSegmentationError,
    validate_text,
    normalize_text,
    split_by_markdown_titles,
    split_by_paragraphs,
    split_by_sentences,
    merge_short_segments,
    split_long_segment,
    refine_segments,
    segment_web_text,
    extract_clean_and_segment_webpage,
)


# ===========================================================================
# validate_text
# ===========================================================================

class TestValidateText:
    def test_vide_leve_exception(self):
        with pytest.raises(WebSegmentationError):
            validate_text("")

    def test_espaces_seulement_leve_exception(self):
        with pytest.raises(WebSegmentationError):
            validate_text("   ")

    def test_texte_valide_ne_leve_pas(self):
        validate_text("Contenu web valide.")


# ===========================================================================
# normalize_text
# ===========================================================================

class TestNormalizeText:
    def test_remplace_nbsp(self):
        assert "\xa0" not in normalize_text("a\xa0b")

    def test_normalise_retours_chariot(self):
        assert "\r" not in normalize_text("a\r\nb")

    def test_reduit_espaces_multiples(self):
        assert "  " not in normalize_text("a  b")

    def test_reduit_sauts_de_ligne(self):
        assert "\n\n\n" not in normalize_text("a\n\n\nb")


# ===========================================================================
# split_by_markdown_titles
# ===========================================================================

class TestSplitByMarkdownTitles:
    def test_deux_sections(self):
        text = "# Titre 1\nContenu 1\n\n# Titre 2\nContenu 2"
        result = split_by_markdown_titles(text)
        assert len(result) >= 2

    def test_sous_titres_detectes(self):
        text = "## Section\nContenu\n\n### Sous-section\nContenu"
        result = split_by_markdown_titles(text)
        assert len(result) >= 2

    def test_sans_titres_retourne_un_bloc(self):
        result = split_by_markdown_titles("Pas de titres ici.")
        assert len(result) == 1


# ===========================================================================
# split_by_paragraphs
# ===========================================================================

class TestSplitByParagraphs:
    def test_deux_paragraphes(self):
        result = split_by_paragraphs("Para 1\n\nPara 2")
        assert len(result) == 2

    def test_paragraphes_vides_ignores(self):
        result = split_by_paragraphs("A\n\n\n\nB")
        assert all(p.strip() for p in result)

    def test_un_seul_paragraphe(self):
        result = split_by_paragraphs("Un seul paragraphe.")
        assert len(result) == 1


# ===========================================================================
# split_by_sentences
# ===========================================================================

class TestSplitBySentences:
    def test_deux_phrases(self):
        result = split_by_sentences("Phrase un. Phrase deux.")
        assert len(result) == 2

    def test_texte_vide(self):
        assert split_by_sentences("") == []

    def test_phrase_avec_point_interrogation(self):
        result = split_by_sentences("Ça va ? Oui bien sûr.")
        assert len(result) == 2


# ===========================================================================
# merge_short_segments
# ===========================================================================

class TestMergeShortSegments:
    def test_fusionne_courts(self):
        result = merge_short_segments(["Court.", "Court."], min_length=100)
        assert len(result) == 1

    def test_garde_longs(self):
        result = merge_short_segments(["A" * 150, "B" * 150], min_length=100)
        assert len(result) == 2

    def test_liste_vide(self):
        assert merge_short_segments([]) == []

    def test_buffer_ajoute_a_la_fin(self):
        result = merge_short_segments(["A" * 150, "Court."], min_length=100)
        assert "Court." in result[-1]


# ===========================================================================
# split_long_segment
# ===========================================================================

class TestSplitLongSegment:
    def test_court_inchange(self):
        assert split_long_segment("Court", max_length=200, overlap=50) == ["Court"]

    def test_long_decoupe(self):
        result = split_long_segment("A" * 500, max_length=200, overlap=20)
        assert len(result) > 1

    def test_chunks_non_vides(self):
        result = split_long_segment("A" * 500, max_length=100, overlap=10)
        assert all(c.strip() for c in result)


# ===========================================================================
# refine_segments
# ===========================================================================

class TestRefineSegments:
    def test_raffinement_basique(self):
        segs = ["Court.", "B" * 1500]
        result = refine_segments(segs, min_length=10, max_length=500, overlap=50)
        assert len(result) >= 1

    def test_segments_vides_filtres(self):
        result = refine_segments(["   ", "Contenu valide."], min_length=5)
        assert all(s.strip() for s in result)


# ===========================================================================
# segment_web_text
# ===========================================================================

class TestSegmentWebText:
    def test_texte_vide_exception(self):
        with pytest.raises(WebSegmentationError):
            segment_web_text("")

    def test_segmentation_markdown(self):
        text = "# Titre\nContenu section.\n\n## Sous-titre\nAutre contenu."
        result = segment_web_text(text, min_length=5)
        assert len(result) >= 1

    def test_segmentation_paragraphes(self):
        text = "Un premier paragraphe.\n\nUn second paragraphe avec du contenu."
        result = segment_web_text(text, min_length=5)
        assert len(result) >= 1

    def test_segmentation_phrases(self):
        text = "Phrase une. Phrase deux. Phrase trois."
        result = segment_web_text(text, min_length=5)
        assert len(result) >= 1

    def test_retourne_liste_de_strings(self):
        text = "Contenu web simple avec du texte."
        result = segment_web_text(text, min_length=5)
        assert all(isinstance(s, str) for s in result)


# ===========================================================================
# extract_clean_and_segment_webpage
# ===========================================================================

class TestExtractCleanAndSegmentWebpage:
    @patch("back.segmentation.SegmentationWeb.WebLinkSource")
    def test_pipeline_complet(self, mock_cls):
        instance = mock_cls.return_value
        instance.validate.return_value = None
        instance.extract_text.return_value = "Contenu web.\n\nDeuxième paragraphe."
        instance.clean_text.return_value = "Contenu web.\n\nDeuxième paragraphe."
        instance.title = "Page"
        instance.sourceID = "abc"
        instance.importedAt = "2024-01-01"

        result = extract_clean_and_segment_webpage("https://example.com", min_length=5)
        assert isinstance(result, list)
        assert all("url" in s for s in result)

    @patch("back.segmentation.SegmentationWeb.WebLinkSource")
    def test_url_dans_segments(self, mock_cls):
        instance = mock_cls.return_value
        instance.validate.return_value = None
        instance.extract_text.return_value = "Contenu.\n\nDeuxième paragraphe."
        instance.clean_text.return_value = "Contenu.\n\nDeuxième paragraphe."
        instance.title = "Page"
        instance.sourceID = "abc"
        instance.importedAt = "2024-01-01"

        result = extract_clean_and_segment_webpage("https://example.com", min_length=5)
        assert all(s["url"] == "https://example.com" for s in result)

    @patch("back.segmentation.SegmentationWeb.WebLinkSource")
    def test_fallback_si_erreur_segmentation(self, mock_cls):
        instance = mock_cls.return_value
        instance.validate.return_value = None
        instance.extract_text.return_value = "Texte."
        instance.clean_text.return_value = "Texte."
        instance.title = "T"
        instance.sourceID = "x"
        instance.importedAt = None

        with patch("back.segmentation.SegmentationWeb.segment_web_text", side_effect=WebSegmentationError("err")), \
             patch("back.segmentation.SegmentationWeb.build_universal_segments", return_value=[{"segment_id": 1, "text": "ok", "length": 2}]):
            result = extract_clean_and_segment_webpage("https://example.com")
        assert result[0]["text"] == "ok"

    @patch("back.segmentation.SegmentationWeb.WebLinkSource")
    def test_erreur_leve_websegmentationerror(self, mock_cls):
        mock_cls.return_value.validate.side_effect = Exception("Connexion impossible")
        with pytest.raises(WebSegmentationError):
            extract_clean_and_segment_webpage("https://fail.com")
            