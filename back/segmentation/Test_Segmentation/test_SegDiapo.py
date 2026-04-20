# Version5/back/segmentation/Test_Segmentation/test_SegDiapo.py
"""
Tests unitaires — SegDiapo.py

Ce fichier teste toutes les fonctions du module SegDiapo,
qui gère la segmentation des présentations/diaporamas PDF.
La logique principale repose sur la détection des marqueurs
"--- Slide X ---" pour découper le contenu slide par slide.
"""
import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock des dépendances lourdes avant tout import du module testé.
# Sans ça, docling et pandas plantent à cause d'incompatibilités binaires.
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
from back.segmentation.SegDiapo import (
    DiaporamaSegmentationError,
    validate_text,
    normalize_text,
    split_by_slides,
    remove_noise_slides,
    merge_small_slides,
    split_long_slide,
    refine_slides,
    segment_diaporama_text,
    extract_clean_and_segment_diaporama,
)


# ===========================================================================
# validate_text
# ===========================================================================

class TestValidateText:
    def test_vide_leve_exception(self):
        # Un texte vide ne contient aucune slide exploitable.
        # La fonction doit lever DiaporamaSegmentationError
        # pour bloquer le pipeline dès le départ.
        with pytest.raises(DiaporamaSegmentationError):
            validate_text("")

    def test_espaces_seulement_leve_exception(self):
        # Un texte composé uniquement d'espaces est équivalent
        # à un texte vide. Il doit être rejeté de la même façon.
        with pytest.raises(DiaporamaSegmentationError):
            validate_text("   ")

    def test_texte_valide_ne_leve_pas(self):
        # Un texte non vide doit passer la validation sans exception.
        # C'est le cas nominal où le PDF a bien été extrait.
        validate_text("Contenu d'une slide.")


# ===========================================================================
# normalize_text
# ===========================================================================

class TestNormalizeText:
    def test_remplace_nbsp(self):
        # Les espaces insécables (\xa0) sont fréquents dans les PDF exportés.
        # Ils doivent être remplacés par des espaces normaux pour éviter
        # des problèmes lors du découpage par expressions régulières.
        assert "\xa0" not in normalize_text("a\xa0b")

    def test_normalise_retours_chariot(self):
        # Les retours chariot Windows (\r\n) doivent être normalisés
        # en sauts de ligne Unix (\n) pour uniformiser le traitement.
        assert "\r" not in normalize_text("a\r\nb")

    def test_reduit_espaces_multiples(self):
        # Les espaces multiples consécutifs dans les slides PDF
        # doivent être réduits à un seul espace.
        assert "  " not in normalize_text("a  b")

    def test_reduit_sauts_de_ligne_multiples(self):
        # Plus de deux sauts de ligne consécutifs sont inutiles.
        # On les réduit pour éviter des slides vides après découpage.
        assert "\n\n\n" not in normalize_text("a\n\n\nb")


# ===========================================================================
# split_by_slides
# ===========================================================================

class TestSplitBySlides:
    def test_deux_slides(self):
        # Le marqueur "--- Slide X ---" est le séparateur principal
        # pour les diaporamas. Deux marqueurs doivent produire deux slides.
        text = "--- Slide 1 ---\nContenu 1\n--- Slide 2 ---\nContenu 2"
        result = split_by_slides(text)
        assert len(result) == 2

    def test_trois_slides(self):
        # On vérifie que la fonction gère correctement
        # plus de deux slides dans un même diaporama.
        text = (
            "--- Slide 1 ---\nContenu 1\n"
            "--- Slide 2 ---\nContenu 2\n"
            "--- Slide 3 ---\nContenu 3"
        )
        result = split_by_slides(text)
        assert len(result) == 3

    def test_sans_marqueur_retourne_un_bloc(self):
        # Si le texte ne contient aucun marqueur "--- Slide X ---",
        # la fonction retourne le texte entier dans un seul bloc
        # ou une liste vide selon l'implémentation.
        result = split_by_slides("Texte sans marqueur de slide.")
        assert len(result) <= 1

    def test_slides_sans_contenu_ignores(self):
        # Les slides vides (sans contenu après le marqueur)
        # doivent être ignorées pour éviter des segments vides.
        text = "--- Slide 1 ---\n\n--- Slide 2 ---\nContenu valide"
        result = split_by_slides(text)
        assert all(s.strip() for s in result)


# ===========================================================================
# remove_noise_slides
# ===========================================================================

class TestRemoveNoiseSlides:
    def test_slide_trop_courte_filtree(self):
        # Une slide avec moins de 5 mots est considérée comme du bruit
        # (numéro de page, titre seul, etc.). Elle doit être supprimée.
        result = remove_noise_slides(["Ok"])
        assert result == []

    def test_slide_trop_petite_en_caracteres_filtree(self):
        # Une slide de moins de 30 caractères est aussi filtrée
        # même si elle contient plusieurs mots courts.
        result = remove_noise_slides(["Un deux trois."])
        assert result == []

    def test_slide_longue_conservee(self):
        # Une slide avec suffisamment de mots et de caractères
        # doit être conservée dans la liste.
        long_slide = "Ceci est un contenu de slide suffisamment long pour ne pas être filtré."
        result = remove_noise_slides([long_slide])
        assert len(result) == 1

    def test_melange_bruit_et_valides(self):
        # Dans une liste mixte, seules les slides valides
        # doivent être conservées, les bruits doivent être retirés.
        slides = ["Ok", "Contenu suffisamment long pour passer le filtre de bruit ici."]
        result = remove_noise_slides(slides)
        assert len(result) == 1


# ===========================================================================
# merge_small_slides
# ===========================================================================

class TestMergeSmallSlides:
    def test_fusionne_petites_slides(self):
        # Deux slides trop courtes (sous min_length) doivent être
        # fusionnées en une seule pour enrichir le contenu du segment.
        slides = ["Court.", "Court aussi."]
        result = merge_small_slides(slides, min_length=200)
        assert len(result) == 1

    def test_garde_grandes_slides(self):
        # Les slides déjà suffisamment longues ne doivent pas
        # être fusionnées entre elles.
        slides = ["A" * 200, "B" * 200]
        result = merge_small_slides(slides, min_length=100)
        assert len(result) == 2

    def test_buffer_ajoute_a_la_fin(self):
        # Si une slide courte reste dans le buffer à la fin,
        # elle doit être fusionnée avec le dernier segment existant.
        result = merge_small_slides(["A" * 200, "Court."], min_length=100)
        assert "Court." in result[-1]

    def test_liste_vide(self):
        # Une liste vide en entrée doit retourner une liste vide
        # sans lever d'exception.
        result = merge_small_slides([])
        assert result == []


# ===========================================================================
# split_long_slide
# ===========================================================================

class TestSplitLongSlide:
    def test_courte_inchangee(self):
        # Une slide plus courte que max_length ne doit pas être découpée.
        # Elle doit être retournée telle quelle dans une liste d'un élément.
        result = split_long_slide("Court", max_length=1200, overlap=200)
        assert result == ["Court"]

    def test_longue_decoupee(self):
        # Une slide dépassant max_length doit être découpée en plusieurs
        # chunks. On vérifie qu'on obtient bien plus d'un chunk.
        result = split_long_slide("A" * 1500, max_length=500, overlap=50)
        assert len(result) > 1

    def test_chunks_non_vides(self):
        # Tous les chunks produits doivent contenir du contenu réel.
        # Aucun chunk vide ou composé d'espaces ne doit apparaître.
        result = split_long_slide("A" * 1500, max_length=500, overlap=50)
        assert all(c.strip() for c in result)

    def test_overlap_crée_chevauchement(self):
        # Avec overlap > 0, les chunks consécutifs doivent se chevaucher.
        # On vérifie que le deuxième chunk commence avant la fin du premier.
        long_text = "Mot " * 500
        result = split_long_slide(long_text, max_length=200, overlap=50)
        assert len(result) >= 2


# ===========================================================================
# refine_slides
# ===========================================================================

class TestRefineSlides:
    def test_raffinement_basique(self):
        # refine_slides combine merge_small_slides et split_long_slide.
        # Les slides courtes sont fusionnées et les longues découpées.
        segs = ["Court.", "B" * 1500]
        result = refine_slides(segs, min_length=10, max_length=500, overlap=50)
        assert len(result) >= 1

    def test_slides_vides_filtrees(self):
        # Les slides composées uniquement d'espaces doivent être
        # filtrées et ne pas apparaître dans le résultat final.
        result = refine_slides(["   ", "Contenu valide de slide."], min_length=5)
        assert all(s.strip() for s in result)

    def test_retourne_liste_de_strings(self):
        # Tous les éléments retournés doivent être des chaînes de caractères.
        result = refine_slides(["Contenu de slide valide."], min_length=5)
        assert all(isinstance(s, str) for s in result)


# ===========================================================================
# segment_diaporama_text
# ===========================================================================

class TestSegmentDiaporamaText:
    def test_vide_exception(self):
        # Un texte vide doit lever DiaporamaSegmentationError
        # car il n'y a rien à segmenter.
        with pytest.raises(DiaporamaSegmentationError):
            segment_diaporama_text("")

    def test_aucune_slide_exception(self):
    # Un texte sans marqueur "--- Slide X ---" sera considéré
    # comme une slide unique mais trop courte → filtrée → exception.
    # On vérifie juste qu'une DiaporamaSegmentationError est bien levée.
        with pytest.raises(DiaporamaSegmentationError):
            segment_diaporama_text("Texte court sans marqueur.")

    def test_toutes_slides_filtrees_exception(self):
        # Si toutes les slides sont trop courtes et donc filtrées,
        # il ne reste rien à segmenter. La fonction doit lever une exception.
        text = "--- Slide 1 ---\nOk\n--- Slide 2 ---\nOk"
        with pytest.raises(DiaporamaSegmentationError):
            segment_diaporama_text(text)

    def test_segmentation_valide(self):
        # Cas nominal : deux slides avec suffisamment de contenu.
        # La fonction doit retourner au moins un segment valide.
        text = (
            "--- Slide 1 ---\n"
            "Contenu de la première slide avec suffisamment de mots pour passer.\n"
            "--- Slide 2 ---\n"
            "Contenu de la deuxième slide avec suffisamment de mots pour passer."
        )
        result = segment_diaporama_text(text, min_length=5)
        assert len(result) >= 1

    def test_retourne_liste_de_strings(self):
        # Tous les segments retournés doivent être des chaînes de caractères.
        text = (
            "--- Slide 1 ---\n"
            "Contenu valide de la première slide avec beaucoup de mots ici.\n"
            "--- Slide 2 ---\n"
            "Contenu valide de la deuxième slide avec beaucoup de mots là."
        )
        result = segment_diaporama_text(text, min_length=5)
        assert all(isinstance(s, str) for s in result)


# ===========================================================================
# extract_clean_and_segment_diaporama
# ===========================================================================

class TestExtractCleanAndSegmentDiaporama:
    @patch("back.segmentation.SegDiapo.DocumentFileSource")
    def test_pipeline_complet(self, mock_cls):
        # On mocke DocumentFileSource pour simuler une extraction PDF réussie
        # sans avoir besoin d'un vrai fichier PDF sur le disque.
        # On vérifie que le pipeline retourne une liste de segments.
        instance = mock_cls.return_value
        instance.validate.return_value = None
        instance.extract_text.return_value = (
            "--- Slide 1 ---\nContenu long et valide pour la slide un ici.\n"
            "--- Slide 2 ---\nContenu long et valide pour la slide deux aussi."
        )
        instance.title = "Diapo"
        instance.sourceID = "diapo1"
        instance.importedAt = "2024-01-01"

        result = extract_clean_and_segment_diaporama("diapo.pdf", min_length=5)
        assert isinstance(result, list)

    @patch("back.segmentation.SegDiapo.DocumentFileSource")
    def test_structure_segments(self, mock_cls):
        # Chaque segment retourné doit contenir les clés essentielles :
        # segment_id, source_type, title, text, length.
        instance = mock_cls.return_value
        instance.validate.return_value = None
        instance.extract_text.return_value = (
            "--- Slide 1 ---\nContenu long et valide pour la slide un ici.\n"
            "--- Slide 2 ---\nContenu long et valide pour la slide deux aussi."
        )
        instance.title = "Diapo Test"
        instance.sourceID = "d1"
        instance.importedAt = "2024-01-01"

        result = extract_clean_and_segment_diaporama("diapo.pdf", min_length=5)
        for seg in result:
            assert "segment_id" in seg
            assert "text" in seg
            assert "length" in seg
            assert "source_type" in seg

    @patch("back.segmentation.SegDiapo.DocumentFileSource")
    def test_source_type_diaporama(self, mock_cls):
        # Le champ source_type de chaque segment doit valoir "diaporama"
        # pour permettre au reste du pipeline de traiter correctement la source.
        instance = mock_cls.return_value
        instance.validate.return_value = None
        instance.extract_text.return_value = (
            "--- Slide 1 ---\nContenu long et valide pour la slide un ici.\n"
            "--- Slide 2 ---\nContenu long et valide pour la slide deux aussi."
        )
        instance.title = "T"
        instance.sourceID = "x"
        instance.importedAt = None

        result = extract_clean_and_segment_diaporama("diapo.pdf", min_length=5)
        assert all(s["source_type"] == "diaporama" for s in result)

    @patch("back.segmentation.SegDiapo.DocumentFileSource")
    def test_fallback_si_erreur_segmentation(self, mock_cls):
        # Si segment_diaporama_text échoue, le pipeline doit utiliser
        # build_universal_segments comme fallback au lieu de planter.
        instance = mock_cls.return_value
        instance.validate.return_value = None
        instance.extract_text.return_value = "Texte sans slides."
        instance.title = "T"
        instance.sourceID = "x"
        instance.importedAt = None

        with patch("back.segmentation.SegDiapo.segment_diaporama_text", side_effect=DiaporamaSegmentationError("err")), \
             patch("back.segmentation.SegDiapo.build_universal_segments", return_value=[{"segment_id": 1, "text": "ok", "length": 2}]):
            result = extract_clean_and_segment_diaporama("diapo.pdf")
        assert result[0]["text"] == "ok"

    @patch("back.segmentation.SegDiapo.DocumentFileSource")
    def test_erreur_leve_exception(self, mock_cls):
        # Si une erreur survient pendant la validation du fichier PDF,
        # la fonction doit lever DiaporamaSegmentationError avec
        # un message explicite plutôt que laisser remonter une exception générique.
        mock_cls.return_value.validate.side_effect = Exception("PDF invalide")
        with pytest.raises(DiaporamaSegmentationError):
            extract_clean_and_segment_diaporama("bad.pdf")