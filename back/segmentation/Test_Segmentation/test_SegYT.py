# Version5/back/segmentation/Test_Segmentation/test_SegYT.py
"""
Tests unitaires — SegmentationYT.py

Ce fichier teste toutes les fonctions du module SegmentationYT,
qui gère la segmentation des transcriptions YouTube.
Les dépendances lourdes (docling, yt_dlp, etc.) sont mockées
pour éviter de charger des librairies inutiles pendant les tests.
"""
import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# On injecte des faux modules dans sys.modules AVANT d'importer SegmentationYT.
# Sans ça, Python essaie de charger docling, pandas, etc. ce qui plante
# car ces librairies ont des dépendances binaires incompatibles dans ce venv.
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

# yt_dlp.utils.DownloadError doit être une vraie classe d'exception
# car Python refuse un MagicMock dans une clause except → TypeError
class _FakeDownloadError(Exception):
    pass

sys.modules["yt_dlp"].utils.DownloadError = _FakeDownloadError
sys.modules["yt_dlp.utils"].DownloadError = _FakeDownloadError

import pytest
from unittest.mock import patch
from back.segmentation.SegmentationYT import (
    YoutubeSegmentationError,
    validate_text,
    normalize_text,
    split_by_markdown_titles,
    split_by_classic_titles,
    split_by_paragraphs,
    split_by_sentences,
    merge_short_segments,
    split_long_segment,
    refine_segments,
    segment_youtube_text,
    extract_clean_and_segment_youtube,
)


# ===========================================================================
# validate_text
# ===========================================================================

class TestValidateText:
    def test_vide_leve_exception(self):
        # Une chaîne vide ne peut pas être segmentée.
        # On vérifie que la fonction lève bien YoutubeSegmentationError
        # pour protéger le reste du pipeline contre un texte invalide.
        with pytest.raises(YoutubeSegmentationError):
            validate_text("")

    def test_espaces_seulement_leve_exception(self):
        # Un texte composé uniquement d'espaces est considéré comme vide.
        # La fonction doit le détecter et lever une exception.
        with pytest.raises(YoutubeSegmentationError):
            validate_text("   ")

    def test_texte_valide_ne_leve_pas(self):
        # Un texte non vide doit passer la validation sans exception.
        # C'est le cas nominal où la transcription est exploitable.
        validate_text("Transcription youtube valide.")


# ===========================================================================
# normalize_text
# ===========================================================================

class TestNormalizeText:
    def test_remplace_nbsp(self):
        # Les espaces insécables (\xa0) viennent souvent de copier-coller
        # ou de pages web. Ils doivent être remplacés par des espaces normaux
        # pour éviter des problèmes de découpage par la suite.
        assert "\xa0" not in normalize_text("a\xa0b")

    def test_normalise_retours_chariot(self):
        # Les retours chariot Windows (\r\n) ou anciens Mac (\r)
        # doivent être convertis en sauts de ligne Unix (\n)
        # pour uniformiser le traitement.
        assert "\r" not in normalize_text("a\r\nb")

    def test_reduit_espaces_multiples(self):
        # Les espaces multiples consécutifs doivent être réduits à un seul
        # pour éviter des segments vides ou mal formés.
        assert "  " not in normalize_text("a  b")

    def test_reduit_sauts_de_ligne(self):
        # Plus de deux sauts de ligne consécutifs sont inutiles.
        # On les réduit à deux maximum pour garder la structure
        # tout en évitant les grands blocs vides.
        assert "\n\n\n" not in normalize_text("a\n\n\nb")


# ===========================================================================
# split_by_markdown_titles
# ===========================================================================

class TestSplitByMarkdownTitles:
    def test_deux_sections(self):
        # Quand le transcript a été structuré avec des titres markdown (# ##),
        # la fonction doit découper le texte en autant de sections que de titres.
        # Ici on attend au moins 2 sections pour # Intro et # Partie 2.
        text = "# Intro\nContenu intro\n\n# Partie 2\nContenu partie"
        result = split_by_markdown_titles(text)
        assert len(result) >= 2

    def test_sans_titres_retourne_un_bloc(self):
        # Si le texte ne contient aucun titre markdown,
        # la fonction retourne le texte entier dans un seul bloc.
        # C'est le comportement attendu pour les transcriptions brutes.
        result = split_by_markdown_titles("Pas de titres ici.")
        assert len(result) == 1


# ===========================================================================
# split_by_classic_titles
# ===========================================================================

class TestSplitByClassicTitles:
    def test_introduction_detectee(self):
        # Les mots clés comme "Introduction" ou "Conclusion" sont des
        # marqueurs courants dans les transcriptions organisées.
        # La fonction doit les détecter et découper en sections.
        text = "Introduction\nContenu intro\n\nConclusion\nContenu conclusion"
        result = split_by_classic_titles(text)
        assert len(result) >= 1

    def test_numerotation_detectee(self):
        # Les titres numérotés (1. Partie, 2. Partie) sont fréquents
        # dans les vidéos pédagogiques. La fonction doit les reconnaître.
        text = "1. Première partie\nContenu\n\n2. Deuxième partie\nContenu"
        result = split_by_classic_titles(text)
        assert len(result) >= 1

    def test_majuscules_detectees(self):
        # Les titres en majuscules (INTRODUCTION, CONCLUSION) sont
        # un autre format courant. La fonction doit les détecter aussi.
        text = "INTRODUCTION\nContenu\n\nCONCLUSION\nContenu"
        result = split_by_classic_titles(text)
        assert len(result) >= 1


# ===========================================================================
# split_by_paragraphs
# ===========================================================================

class TestSplitByParagraphs:
    def test_deux_blocs(self):
        # Deux blocs séparés par une ligne vide doivent produire
        # deux paragraphes distincts.
        result = split_by_paragraphs("Bloc A\n\nBloc B")
        assert len(result) == 2

    def test_blocs_vides_ignores(self):
        # Les blocs vides créés par plusieurs lignes vides consécutives
        # doivent être ignorés pour éviter des segments sans contenu.
        result = split_by_paragraphs("A\n\n\n\nB")
        assert all(p.strip() for p in result)


# ===========================================================================
# split_by_sentences
# ===========================================================================

class TestSplitBySentences:
    def test_deux_phrases(self):
        # Le découpage par phrases doit séparer correctement
        # deux phrases terminées par un point.
        result = split_by_sentences("Phrase une. Phrase deux.")
        assert len(result) == 2

    def test_texte_vide(self):
        # Un texte vide doit retourner une liste vide
        # sans lever d'exception.
        assert split_by_sentences("") == []

    def test_phrase_avec_point_interrogation(self):
        # Le découpage doit aussi fonctionner avec les points
        # d'interrogation comme séparateurs de phrases.
        result = split_by_sentences("Vraiment ? Oui tout à fait.")
        assert len(result) == 2


# ===========================================================================
# merge_short_segments
# ===========================================================================

class TestMergeShortSegments:
    def test_fusionne_segments_courts(self):
        # Deux segments trop courts (sous le min_length) doivent être
        # fusionnés en un seul pour éviter des segments trop pauvres
        # en contenu pour le LLM.
        result = merge_short_segments(["A.", "B."], min_length=200)
        assert len(result) == 1

    def test_garde_segments_longs(self):
        # Les segments déjà suffisamment longs ne doivent pas être fusionnés.
        # Chaque segment doit rester indépendant.
        result = merge_short_segments(["A" * 250, "B" * 250], min_length=200)
        assert len(result) == 2

    def test_liste_vide(self):
        # Une liste vide en entrée doit retourner une liste vide
        # sans lever d'exception.
        assert merge_short_segments([]) == []

    def test_buffer_ajoute_a_la_fin(self):
        # Si un segment court reste dans le buffer à la fin du parcours,
        # il doit être fusionné avec le dernier segment long existant.
        result = merge_short_segments(["A" * 250, "Court."], min_length=200)
        assert "Court." in result[-1]


# ===========================================================================
# split_long_segment
# ===========================================================================

class TestSplitLongSegment:
    def test_court_inchange(self):
        # Un segment plus court que max_length ne doit pas être découpé.
        # Il doit être retourné tel quel dans une liste d'un seul élément.
        assert split_long_segment("Court", max_length=1500, overlap=50) == ["Court"]

    def test_long_decoupe(self):
        # Un segment dépassant max_length doit être découpé en plusieurs
        # chunks. On vérifie qu'on obtient bien plus d'un chunk.
        result = split_long_segment("A" * 2000, max_length=500, overlap=50)
        assert len(result) > 1

    def test_max_length_zero_exception(self):
        # max_length=0 est invalide car on ne peut pas créer des chunks
        # de taille nulle. La fonction doit lever une exception.
        with pytest.raises(YoutubeSegmentationError):
            split_long_segment("x", max_length=0)

    def test_overlap_negatif_exception(self):
        # Un overlap négatif n'a pas de sens métier.
        # La fonction doit le rejeter avec une exception claire.
        with pytest.raises(YoutubeSegmentationError):
            split_long_segment("x" * 500, max_length=500, overlap=-1)

    def test_overlap_trop_grand_exception(self):
        # Si overlap >= max_length, le step devient nul ou négatif,
        # ce qui crée une boucle infinie. La fonction doit l'interdire.
        with pytest.raises(YoutubeSegmentationError):
            split_long_segment("x" * 500, max_length=100, overlap=200)

    def test_chunks_non_vides(self):
        # Tous les chunks produits doivent contenir du contenu réel.
        # Aucun chunk vide ou composé uniquement d'espaces ne doit apparaître.
        result = split_long_segment("A" * 1000, max_length=200, overlap=20)
        assert all(c.strip() for c in result)


# ===========================================================================
# refine_segments
# ===========================================================================

class TestRefineSegments:
    def test_raffinement_basique(self):
        # refine_segments combine merge et split :
        # les courts sont fusionnés et les longs sont découpés.
        # On vérifie qu'on obtient au moins un segment valide en sortie.
        segs = ["Court.", "B" * 2000]
        result = refine_segments(segs, min_length=10, max_length=600, overlap=50)
        assert len(result) >= 1

    def test_segments_vides_filtres(self):
        # Les segments composés uniquement d'espaces doivent être
        # filtrés et ne pas apparaître dans le résultat final.
        result = refine_segments(["   ", "Contenu valide."], min_length=5)
        assert all(s.strip() for s in result)


# ===========================================================================
# segment_youtube_text
# ===========================================================================

class TestSegmentYoutubeText:
    def test_vide_exception(self):
        # Un texte vide ne peut pas être segmenté.
        # La fonction doit lever YoutubeSegmentationError immédiatement.
        with pytest.raises(YoutubeSegmentationError):
            segment_youtube_text("")

    def test_segmentation_markdown(self):
        # Quand le texte a des titres markdown, la segmentation
        # doit les utiliser comme points de découpe principaux.
        text = "# Intro\nContenu intro.\n\n# Partie\nContenu partie."
        result = segment_youtube_text(text, min_length=5)
        assert len(result) >= 1

    def test_segmentation_paragraphes(self):
        # En l'absence de titres, la segmentation doit se rabattre
        # sur les paragraphes séparés par des lignes vides.
        text = "Paragraphe un bien rempli.\n\nParagraphe deux bien rempli."
        result = segment_youtube_text(text, min_length=5)
        assert len(result) >= 1

    def test_segmentation_phrases(self):
        # En dernier recours, la segmentation par phrases doit fonctionner
        # même si le texte n'a ni titres ni paragraphes distincts.
        text = "Phrase une. Phrase deux. Phrase trois."
        result = segment_youtube_text(text, min_length=5)
        assert len(result) >= 1

    def test_retourne_liste_de_strings(self):
        # Tous les segments retournés doivent être des chaînes de caractères.
        # On vérifie le type de chaque élément de la liste.
        text = "Contenu transcription simple."
        result = segment_youtube_text(text, min_length=5)
        assert all(isinstance(s, str) for s in result)


# ===========================================================================
# extract_clean_and_segment_youtube
# ===========================================================================

class TestExtractCleanAndSegmentYoutube:
    @patch("back.segmentation.SegmentationYT.YoutubeSource")
    def test_pipeline_complet(self, mock_cls):
        # On mocke YoutubeSource pour simuler une extraction réussie
        # sans appel réseau réel. On vérifie que le pipeline complet
        # retourne une liste de segments bien formés avec la clé "video_url".
        instance = mock_cls.return_value
        instance.validate.return_value = None
        instance.extract_text.return_value = "Transcription.\n\nDeuxième partie."
        instance.clean_text.return_value = "Transcription.\n\nDeuxième partie."
        instance.title = "Vidéo"
        instance.sourceID = "vid123"
        instance.importedAt = "2024-01-01"

        result = extract_clean_and_segment_youtube("https://youtu.be/abc", min_length=5)
        assert isinstance(result, list)
        assert all("video_url" in s for s in result)

    @patch("back.segmentation.SegmentationYT.YoutubeSource")
    def test_video_url_dans_segments(self, mock_cls):
        # L'URL de la vidéo doit être correctement transmise
        # dans chaque segment pour assurer la traçabilité de la source.
        instance = mock_cls.return_value
        instance.validate.return_value = None
        instance.extract_text.return_value = "Transcription.\n\nDeuxième partie."
        instance.clean_text.return_value = "Transcription.\n\nDeuxième partie."
        instance.title = "Vidéo"
        instance.sourceID = "vid123"
        instance.importedAt = "2024-01-01"

        url = "https://youtu.be/abc123"
        result = extract_clean_and_segment_youtube(url, min_length=5)
        assert all(s["video_url"] == url for s in result)

    @patch("back.segmentation.SegmentationYT.YoutubeSource")
    def test_fallback_si_erreur_segmentation(self, mock_cls):
        # Si segment_youtube_text échoue, le pipeline doit se rabattre
        # sur build_universal_segments plutôt que de planter complètement.
        # C'est le mécanisme de robustesse du pipeline.
        instance = mock_cls.return_value
        instance.validate.return_value = None
        instance.extract_text.return_value = "Texte."
        instance.clean_text.return_value = "Texte."
        instance.title = "T"
        instance.sourceID = "x"
        instance.importedAt = None

        with patch("back.segmentation.SegmentationYT.segment_youtube_text", side_effect=YoutubeSegmentationError("err")), \
             patch("back.segmentation.SegmentationYT.build_universal_segments", return_value=[{"segment_id": 1, "text": "ok", "length": 2}]):
            result = extract_clean_and_segment_youtube("https://youtu.be/abc")
        assert result[0]["text"] == "ok"

    @patch("back.segmentation.SegmentationYT.YoutubeSource")
    def test_erreur_leve_exception(self, mock_cls):
        # Si une erreur survient pendant la validation ou l'extraction,
        # la fonction doit lever YoutubeSegmentationError avec un message
        # explicite plutôt que de laisser remonter une exception générique.
        mock_cls.return_value.validate.side_effect = Exception("Erreur YT")
        with pytest.raises(YoutubeSegmentationError):
            extract_clean_and_segment_youtube("https://youtu.be/fail")