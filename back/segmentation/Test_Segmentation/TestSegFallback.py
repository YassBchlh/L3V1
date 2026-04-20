# Version5/back/segmentation/Test_Segmentation/TestSegFallback.py
"""
Tests unitaires — SegmentationFallback.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from SegmentationFallback import (
    UniversalSegmentationError,
    validate_text,
    normalize_text,
    split_by_blocks,
    split_by_sentences,
    merge_short_segments,
    split_long_segment,
    refine_segments,
    segment_universal_text,
    build_universal_segments,
)


# ===========================================================================
# validate_text
# ===========================================================================

class TestValidateText:
    def test_texte_vide_leve_exception(self):
        with pytest.raises(UniversalSegmentationError):
            validate_text("")

    def test_espaces_seulement_leve_exception(self):
        with pytest.raises(UniversalSegmentationError):
            validate_text("   ")

    def test_texte_valide_ne_leve_pas(self):
        validate_text("Bonjour le monde.")


# ===========================================================================
# normalize_text
# ===========================================================================

class TestNormalizeText:
    def test_remplace_nbsp(self):
        assert "\xa0" not in normalize_text("hello\xa0world")

    def test_reduit_sauts_de_ligne_multiples(self):
        assert "\n\n\n" not in normalize_text("a\n\n\n\nb")

    def test_reduit_espaces_multiples(self):
        assert "  " not in normalize_text("a  b  c")

    def test_normalise_retours_chariot(self):
        assert "\r" not in normalize_text("a\r\nb")


# ===========================================================================
# split_by_blocks
# ===========================================================================

class TestSplitByBlocks:
    def test_deux_blocs(self):
        blocks = split_by_blocks("Bloc A\n\nBloc B")
        assert len(blocks) == 2

    def test_blocs_vides_ignores(self):
        blocks = split_by_blocks("A\n\n\n\nB")
        assert all(b.strip() for b in blocks)

    def test_un_seul_bloc(self):
        blocks = split_by_blocks("Un seul bloc sans séparation.")
        assert len(blocks) == 1


# ===========================================================================
# split_by_sentences
# ===========================================================================

class TestSplitBySentences:
    def test_deux_phrases(self):
        result = split_by_sentences("Phrase un. Phrase deux.")
        assert len(result) == 2

    def test_texte_vide(self):
        assert split_by_sentences("") == []

    def test_phrases_avec_exclamation(self):
        result = split_by_sentences("Bravo ! Bien joué.")
        assert len(result) == 2


# ===========================================================================
# merge_short_segments
# ===========================================================================

class TestMergeShortSegments:
    def test_fusionne_segments_courts(self):
        result = merge_short_segments(["Court.", "Aussi court."], min_length=100)
        assert len(result) == 1

    def test_ne_fusionne_pas_segments_longs(self):
        result = merge_short_segments(["A" * 150, "B" * 150], min_length=100)
        assert len(result) == 2

    def test_liste_vide(self):
        assert merge_short_segments([]) == []

    def test_buffer_restant_ajoute_a_la_fin(self):
        # Un segment long + un court → le court se fusionne avec le long
        result = merge_short_segments(["A" * 150, "Court."], min_length=100)
        assert len(result) == 1
        assert "Court." in result[0]


# ===========================================================================
# split_long_segment
# ===========================================================================

class TestSplitLongSegment:
    def test_segment_court_retourne_tel_quel(self):
        result = split_long_segment("Court", max_length=1200)
        assert result == ["Court"]

    def test_decoupe_segment_long(self):
        long_text = "Phrase normale. " * 100
        result = split_long_segment(long_text, max_length=200, overlap=20)
        assert len(result) > 1

    def test_max_length_zero_leve_exception(self):
        with pytest.raises(UniversalSegmentationError):
            split_long_segment("texte", max_length=0)

    def test_overlap_negatif_leve_exception(self):
        with pytest.raises(UniversalSegmentationError):
            split_long_segment("texte", max_length=200, overlap=-1)

    def test_overlap_superieur_max_length_leve_exception(self):
        with pytest.raises(UniversalSegmentationError):
            split_long_segment("texte", max_length=100, overlap=150)

    def test_chunks_non_vides(self):
        result = split_long_segment("A" * 500, max_length=100, overlap=10)
        assert all(c.strip() for c in result)


# ===========================================================================
# refine_segments
# ===========================================================================

class TestRefineSegments:
    def test_raffinement_basique(self):
        segs = ["Court.", "A" * 1500]
        result = refine_segments(segs, min_length=10, max_length=500, overlap=50)
        assert len(result) >= 1

    def test_segments_vides_filtres(self):
        result = refine_segments(["   ", "Contenu valide."], min_length=5)
        assert all(s.strip() for s in result)


# ===========================================================================
# segment_universal_text
# ===========================================================================

class TestSegmentUniversalText:
    def test_texte_vide_leve_exception(self):
        with pytest.raises(UniversalSegmentationError):
            segment_universal_text("")

    def test_segmentation_par_paragraphes(self):
        text = "Premier paragraphe avec assez de contenu.\n\nDeuxième paragraphe avec assez de contenu."
        result = segment_universal_text(text, min_length=5)
        assert len(result) >= 1

    def test_retourne_liste_de_strings(self):
        text = "Texte simple. Avec quelques phrases. Et encore une."
        result = segment_universal_text(text, min_length=5, max_length=500)
        assert all(isinstance(s, str) for s in result)


# ===========================================================================
# build_universal_segments
# ===========================================================================

class TestBuildUniversalSegments:
    def test_structure_sortie(self):
        text = "Premier bloc.\n\nDeuxième bloc avec plus de contenu ici."
        result = build_universal_segments(text, source_type="txt", title="Test",
                                          sourceID="id1", min_length=5)
        assert all("segment_id" in s and "text" in s and "length" in s for s in result)

    def test_ids_incrementaux(self):
        text = "Paragraphe A.\n\nParagraphe B avec du contenu supplémentaire."
        result = build_universal_segments(text, min_length=5)
        ids = [s["segment_id"] for s in result]
        assert ids == list(range(1, len(ids) + 1))

    def test_longueur_coherente(self):
        text = "Un paragraphe unique avec du contenu."
        result = build_universal_segments(text, min_length=5)
        for seg in result:
            assert seg["length"] == len(seg["text"])

    def test_source_type_transmis(self):
        text = "Contenu de test.\n\nDeuxième partie."
        result = build_universal_segments(text, source_type="youtube", min_length=5)
        assert all(s["source_type"] == "youtube" for s in result)