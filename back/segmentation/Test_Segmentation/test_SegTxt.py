# Version5/back/segmentation/Test_Segmentation/test_SegTxt.py
"""
Tests unitaires — SegmentationTxt.py
"""
import sys
import os
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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch
from SegmentationTxt import (
    TextSegmentationError,
    validate_text,
    normalize_text,
    split_by_markdown_titles,
    split_by_classic_titles,
    split_by_paragraphs,
    split_by_sentences,
    merge_short_segments,
    split_long_segment,
    refine_segments,
    segment_clean_text,
    extract_clean_and_segment_text_document,
)


class TestValidateText:
    def test_vide_leve_exception(self):
        # Texte vide → exception car rien à segmenter
        with pytest.raises(TextSegmentationError):
            validate_text("")

    def test_espaces_seulement_leve_exception(self):
        # Espaces seuls équivalent à vide
        with pytest.raises(TextSegmentationError):
            validate_text("   ")

    def test_texte_valide_ne_leve_pas(self):
        # Texte non vide → pas d'exception
        validate_text("Contenu valide")


class TestNormalizeText:
    def test_remplace_nbsp(self):
        # Les espaces insécables doivent devenir des espaces normaux
        assert "\xa0" not in normalize_text("a\xa0b")

    def test_normalise_retours_chariot(self):
        # \r\n Windows → \n Unix
        assert "\r" not in normalize_text("a\r\nb")

    def test_reduit_espaces_multiples(self):
        # Plusieurs espaces → un seul
        assert "  " not in normalize_text("a  b")

    def test_reduit_sauts_de_ligne(self):
        # Plus de 2 sauts de ligne → réduits à 2
        assert "\n\n\n" not in normalize_text("a\n\n\nb")


class TestSplitByMarkdownTitles:
    def test_deux_sections(self):
        # Deux titres markdown → deux sections distinctes
        text = "# Titre 1\nContenu 1\n\n# Titre 2\nContenu 2"
        result = split_by_markdown_titles(text)
        assert len(result) >= 2

    def test_sous_titres_detectes(self):
        # Les sous-titres ## et ### sont aussi des séparateurs
        text = "## Sous-titre\nContenu\n\n### Sous-sous-titre\nContenu"
        result = split_by_markdown_titles(text)
        assert len(result) >= 2

    def test_sans_titres_retourne_un_bloc(self):
        # Sans titres → tout le texte dans un seul bloc
        result = split_by_markdown_titles("Pas de titres ici.")
        assert len(result) == 1


class TestSplitByClassicTitles:
    def test_numerotation_detectee(self):
        # Les titres numérotés (1. Introduction) sont des séparateurs
        text = "1. Introduction\nContenu\n\n2. Méthodes\nContenu"
        result = split_by_classic_titles(text)
        assert len(result) >= 1

    def test_majuscules_detectees(self):
        # Les titres en majuscules (INTRODUCTION) sont aussi détectés
        text = "INTRODUCTION\nContenu intro\n\nCONCLUSION\nContenu conclusion"
        result = split_by_classic_titles(text)
        assert len(result) >= 1


class TestSplitByParagraphs:
    def test_deux_paragraphes(self):
        # Deux blocs séparés par une ligne vide → deux paragraphes
        result = split_by_paragraphs("Para 1\n\nPara 2")
        assert len(result) == 2

    def test_paragraphes_vides_ignores(self):
        # Les blocs vides entre lignes vides sont filtrés
        result = split_by_paragraphs("A\n\n\n\nB")
        assert all(p.strip() for p in result)


class TestSplitBySentences:
    def test_deux_phrases(self):
        # Deux phrases séparées par un point → deux éléments
        result = split_by_sentences("Phrase une. Phrase deux.")
        assert len(result) == 2

    def test_texte_vide(self):
        # Texte vide → liste vide sans exception
        assert split_by_sentences("") == []

    def test_phrase_avec_point_exclamation(self):
        # Le point d'exclamation est aussi un séparateur de phrases
        result = split_by_sentences("Super ! Bien joué.")
        assert len(result) == 2


class TestMergeShortSegments:
    def test_fusion_segments_courts(self):
        # Deux segments sous min_length → fusionnés en un seul
        result = merge_short_segments(["A.", "B."], min_length=100)
        assert len(result) == 1

    def test_ne_fusionne_pas_segments_longs(self):
        # Segments déjà longs → restent indépendants
        result = merge_short_segments(["A" * 150, "B" * 150], min_length=100)
        assert len(result) == 2

    def test_liste_vide(self):
        # Liste vide → liste vide sans exception
        assert merge_short_segments([]) == []

    def test_buffer_ajoute_a_la_fin(self):
        # Segment court restant → fusionné avec le dernier long
        result = merge_short_segments(["A" * 150, "Court."], min_length=100)
        assert len(result) == 1
        assert "Court." in result[0]


class TestSplitLongSegment:
    def test_court_inchange(self):
        # Segment sous max_length → retourné tel quel
        assert split_long_segment("Court", max_length=200, overlap=50) == ["Court"]

    def test_long_decoupe(self):
        # Segment dépassant max_length → découpé en plusieurs chunks
        result = split_long_segment("A" * 500, max_length=200, overlap=20)
        assert len(result) > 1

    def test_max_length_zero_exception(self):
        # max_length=0 invalide → exception
        with pytest.raises(TextSegmentationError):
            split_long_segment("x", max_length=0)

    def test_overlap_negatif_exception(self):
        # overlap négatif → exception
        with pytest.raises(TextSegmentationError):
            split_long_segment("x" * 500, max_length=200, overlap=-1)

    def test_overlap_trop_grand_exception(self):
        # overlap >= max_length → boucle infinie → exception
        with pytest.raises(TextSegmentationError):
            split_long_segment("x" * 500, max_length=100, overlap=150)


class TestRefineSegments:
    def test_decoupe_et_fusionne(self):
        # Courts fusionnés + longs découpés → résultat valide
        segs = ["Petit.", "B" * 1500]
        result = refine_segments(segs, min_length=10, max_length=500, overlap=50)
        assert len(result) >= 1

    def test_segments_vides_filtres(self):
        # Segments vides → filtrés du résultat
        result = refine_segments(["   ", "Contenu valide."], min_length=5)
        assert all(s.strip() for s in result)


class TestSegmentCleanText:
    def test_texte_vide_exception(self):
        # Texte vide → exception immédiate
        with pytest.raises(TextSegmentationError):
            segment_clean_text("")

    def test_segmentation_markdown(self):
        # Titres markdown utilisés comme points de découpe
        text = "# Section A\nContenu A.\n\n# Section B\nContenu B."
        result = segment_clean_text(text, min_length=5)
        assert len(result) >= 1

    def test_segmentation_paragraphes(self):
        # En l'absence de titres, découpage par paragraphes
        text = "Premier paragraphe bien rempli.\n\nDeuxième paragraphe bien rempli."
        result = segment_clean_text(text, min_length=5)
        assert len(result) >= 1

    def test_segmentation_phrases(self):
        # En dernier recours, découpage par phrases
        text = "Phrase une. Phrase deux. Phrase trois."
        result = segment_clean_text(text, min_length=5, max_length=500)
        assert len(result) >= 1

    def test_retourne_liste_de_strings(self):
        # Tous les segments retournés sont des chaînes
        text = "Contenu simple avec plusieurs phrases ici."
        result = segment_clean_text(text, min_length=5)
        assert all(isinstance(s, str) for s in result)


class TestExtractCleanAndSegmentTextDocument:
    def test_format_non_supporte_exception(self):
        # Format inconnu → exception immédiate
        with pytest.raises(TextSegmentationError):
            extract_clean_and_segment_text_document("file.xyz", "xyz")

    def test_format_pdf_non_supporte_exception(self):
        # PDF non supporté par ce module → exception
        with pytest.raises(TextSegmentationError):
            extract_clean_and_segment_text_document("file.pdf", "pdf")

    @patch("SegmentationTxt.DocumentFileSource")
    def test_pipeline_complet_txt(self, mock_cls):
        # Pipeline complet simulé : validate + extract + clean → segments
        instance = mock_cls.return_value
        instance.validate.return_value = None
        instance.extract_text.return_value = "Contenu.\n\nDeuxième paragraphe."
        instance.clean_text.return_value = "Contenu.\n\nDeuxième paragraphe."
        instance.title = "Titre"
        instance.sourceID = "id123"
        instance.importedAt = "2024-01-01"

        result = extract_clean_and_segment_text_document("doc.txt", "txt", min_length=5)
        assert isinstance(result, list)
        assert all("text" in s for s in result)

    @patch("SegmentationTxt.DocumentFileSource")
    def test_pipeline_complet_md(self, mock_cls):
        # Même pipeline pour un fichier markdown
        instance = mock_cls.return_value
        instance.validate.return_value = None
        instance.extract_text.return_value = "# Titre\nContenu md."
        instance.clean_text.return_value = "# Titre\nContenu md."
        instance.title = "Titre"
        instance.sourceID = "id123"
        instance.importedAt = "2024-01-01"

        result = extract_clean_and_segment_text_document("doc.md", "md", min_length=5)
        assert isinstance(result, list)

    @patch("SegmentationTxt.DocumentFileSource")
    def test_source_type_dans_segments(self, mock_cls):
        # Le source_type de chaque segment doit valoir ".txt"
        instance = mock_cls.return_value
        instance.validate.return_value = None
        instance.extract_text.return_value = "Contenu.\n\nDeuxième paragraphe."
        instance.clean_text.return_value = "Contenu.\n\nDeuxième paragraphe."
        instance.title = "T"
        instance.sourceID = "x"
        instance.importedAt = None

        result = extract_clean_and_segment_text_document("doc.txt", "txt", min_length=5)
        assert all(s["source_type"] == ".txt" for s in result)

    @patch("SegmentationTxt.DocumentFileSource")
    def test_fallback_si_erreur_segmentation(self, mock_cls):
        # Si segment_clean_text échoue → fallback sur build_universal_segments
        instance = mock_cls.return_value
        instance.validate.return_value = None
        instance.extract_text.return_value = "Texte court."
        instance.clean_text.return_value = "Texte court."
        instance.title = "T"
        instance.sourceID = "x"
        instance.importedAt = None

        with patch("SegmentationTxt.segment_clean_text", side_effect=TextSegmentationError("err")), \
             patch("SegmentationTxt.build_universal_segments", return_value=[{"segment_id": 1, "text": "ok", "length": 2}]):
            result = extract_clean_and_segment_text_document("doc.txt", "txt")
        assert result[0]["text"] == "ok"