# Version5/back/segmentation/Test_Segmentation/test_SegFromExtraction.py
"""
Tests unitaires — SegFromExtraction.py

Ce fichier teste toutes les fonctions du module SegFromExtraction,
qui parse les fichiers markdown générés par extraction_final()
et les segmente ressource par ressource en conservant les métadonnées.
"""
import sys
import os
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

class _FakeDownloadError(Exception):
    pass

sys.modules["yt_dlp"].utils.DownloadError = _FakeDownloadError
sys.modules["yt_dlp.utils"].DownloadError = _FakeDownloadError

import pytest
from back.segmentation.SegFromExtraction import (
    ExtractionMarkdownParseError,
    _normalize_type,
    _extract_field,
    _clean_content,
    _split_paragraphs,
    _chunk_text,
    parse_extraction_markdown,
    segment_from_extraction_markdown,
)


# ===========================================================================
# _normalize_type
# ===========================================================================

class TestNormalizeType:
    def test_pdf(self):
        # ".pdf" doit être normalisé en "pdf" (sans le point)
        # pour uniformiser les types dans les segments.
        assert _normalize_type(".pdf") == "pdf"

    def test_docx(self):
        # ".docx" doit être normalisé en "docx".
        assert _normalize_type(".docx") == "docx"

    def test_txt(self):
        # ".txt" doit être normalisé en "txt".
        assert _normalize_type(".txt") == "txt"

    def test_md(self):
        # ".md" doit être normalisé en "md".
        assert _normalize_type(".md") == "md"

    def test_website(self):
        # "website" doit rester "website" car c'est déjà
        # le format attendu dans le mapping.
        assert _normalize_type("website") == "website"

    def test_youtube(self):
        # "youtube" doit rester "youtube".
        assert _normalize_type("youtube") == "youtube"

    def test_inconnu_retourne_la_valeur(self):
        # Un type inconnu doit être retourné tel quel (en minuscules)
        # plutôt que de lever une exception.
        assert _normalize_type("xyz") == "xyz"

    def test_vide_retourne_unknown(self):
        # Une chaîne vide doit retourner "unknown"
        # car on ne peut pas identifier le type.
        assert _normalize_type("") == "unknown"

    def test_none_retourne_unknown(self):
        # None doit retourner "unknown" sans lever d'exception.
        assert _normalize_type(None) == "unknown"

    def test_majuscules_normalisees(self):
        # Les types en majuscules doivent être normalisés en minuscules
        # avant la recherche dans le mapping.
        assert _normalize_type(".PDF") == "pdf"


# ===========================================================================
# _extract_field
# ===========================================================================

class TestExtractField:
    def test_champ_type_trouve(self):
        # Le pattern pour extraire le type doit trouver "pdf"
        # dans une ligne de tableau markdown formatée correctement.
        block = "| **Type** | `.pdf` |"
        result = _extract_field(
            r"^\|\s+\*\*Type\*\*\s+\|\s+`([^`]+)`\s+\|$", block
        )
        assert result == ".pdf"

    def test_champ_id_trouve(self):
        # Le pattern pour extraire l'ID doit fonctionner
        # de la même façon que pour le type.
        block = "| **ID** | `abc123` |"
        result = _extract_field(
            r"^\|\s+\*\*ID\*\*\s+\|\s+`([^`]+)`\s+\|$", block
        )
        assert result == "abc123"

    def test_champ_absent_retourne_defaut(self):
        # Si le pattern ne trouve rien, la fonction doit retourner
        # la valeur par défaut fournie en paramètre.
        result = _extract_field(
            r"^## Inexistant (.+)$", "contenu sans match", default="fallback"
        )
        assert result == "fallback"

    def test_defaut_vide_par_defaut(self):
        # Sans valeur par défaut explicite, la fonction retourne
        # une chaîne vide quand le pattern ne matche pas.
        result = _extract_field(r"^## Inexistant (.+)$", "contenu")
        assert result == ""


# ===========================================================================
# _clean_content
# ===========================================================================

class TestCleanContent:
    def test_remplace_nbsp(self):
        # Les espaces insécables doivent être remplacés par des espaces normaux
        # pour éviter des problèmes lors du découpage en chunks.
        assert "\xa0" not in _clean_content("a\xa0b")

    def test_normalise_retours_chariot(self):
        # Les retours chariot doivent être convertis en sauts de ligne Unix.
        assert "\r" not in _clean_content("a\r\nb")

    def test_reduit_espaces_multiples(self):
        # Les espaces multiples consécutifs doivent être réduits à un seul.
        assert "  " not in _clean_content("a  b")

    def test_reduit_sauts_de_ligne_multiples(self):
        # Plus de deux sauts de ligne consécutifs doivent être réduits.
        assert "\n\n\n" not in _clean_content("a\n\n\nb")

    def test_vide_retourne_vide(self):
        # Une chaîne vide doit retourner une chaîne vide sans exception.
        assert _clean_content("") == ""

    def test_none_retourne_vide(self):
        # None doit retourner une chaîne vide sans lever d'exception.
        assert _clean_content(None) == ""


# ===========================================================================
# _split_paragraphs
# ===========================================================================

class TestSplitParagraphs:
    def test_deux_paragraphes(self):
        # Deux blocs séparés par une ligne vide doivent produire
        # deux paragraphes distincts.
        result = _split_paragraphs("Para 1\n\nPara 2")
        assert len(result) == 2

    def test_paragraphes_vides_ignores(self):
        # Les paragraphes vides créés par plusieurs lignes vides
        # consécutives doivent être filtrés.
        result = _split_paragraphs("A\n\n\n\nB")
        assert all(p.strip() for p in result)

    def test_vide_retourne_liste_vide(self):
        # Un texte vide doit retourner une liste vide sans exception.
        assert _split_paragraphs("") == []

    def test_un_seul_paragraphe(self):
        # Un texte sans ligne vide doit retourner un seul paragraphe.
        result = _split_paragraphs("Un seul paragraphe sans séparation.")
        assert len(result) == 1


# ===========================================================================
# _chunk_text
# ===========================================================================

class TestChunkText:
    def test_texte_vide_retourne_liste_vide(self):
        # Un texte vide doit retourner une liste vide
        # sans tenter de créer des chunks.
        assert _chunk_text("") == []

    def test_chunks_respectent_max_chars(self):
        # Chaque chunk produit doit respecter approximativement
        # la limite max_chars pour ne pas surcharger le LLM.
        text = "Phrase courte. " * 100
        chunks = _chunk_text(text, max_chars=200, min_chars=50)
        assert all(len(c) <= 200 + 50 for c in chunks)

    def test_paragraphe_tres_long_decoupe_par_phrases(self):
        # Un paragraphe dépassant max_chars doit être découpé
        # phrase par phrase pour respecter la limite.
        long_para = "Mot simple. " * 100
        chunks = _chunk_text(long_para, max_chars=100)
        assert len(chunks) >= 1

    def test_retourne_liste_de_strings(self):
        # Tous les chunks retournés doivent être des chaînes de caractères.
        text = "Premier paragraphe.\n\nDeuxième paragraphe."
        chunks = _chunk_text(text)
        assert all(isinstance(c, str) for c in chunks)

    def test_chunks_non_vides(self):
        # Aucun chunk vide ou composé uniquement d'espaces
        # ne doit apparaître dans le résultat.
        text = "Contenu valide avec plusieurs phrases ici."
        chunks = _chunk_text(text)
        assert all(c.strip() for c in chunks)


# ===========================================================================
# parse_extraction_markdown
# ===========================================================================

class TestParseExtractionMarkdown:
    def test_fichier_introuvable_exception(self):
        # Si le fichier markdown n'existe pas sur le disque,
        # la fonction doit lever ExtractionMarkdownParseError
        # avec un message indiquant que le fichier est introuvable.
        with pytest.raises(ExtractionMarkdownParseError):
            parse_extraction_markdown("/tmp/inexistant_xyz_abc.md")

    def test_parse_ressource_basique(self, tmp_path):
        # Cas nominal : un fichier markdown bien formé avec une ressource.
        # La fonction doit retourner une liste avec un élément contenant
        # les bonnes métadonnées (title, source_type, content).
        md_content = (
            "# Extraction des ressources\n\n"
            "## Ressource 1 — Mon article\n\n"
            "| **Type** | `.pdf` |\n"
            "| **ID** | `abc123` |\n"
            "| **Importé** | 2024-01-01 |\n\n"
            "### Contenu\n\n"
            "Ceci est le contenu de l'article.\n"
        )
        f = tmp_path / "extraction_test.md"
        f.write_text(md_content, encoding="utf-8")

        result = parse_extraction_markdown(str(f))
        assert len(result) == 1
        assert result[0]["title"] == "Mon article"
        assert result[0]["source_type"] == "pdf"
        assert "contenu" in result[0]["content"].lower()

    def test_parse_plusieurs_ressources(self, tmp_path):
        # Un fichier avec plusieurs ressources doit produire
        # une liste avec autant d'éléments que de ressources.
        md_content = (
            "## Ressource 1 — Article A\n\n"
            "| **Type** | `website` |\n"
            "| **ID** | `id1` |\n"
            "| **Importé** | 2024-01-01 |\n\n"
            "### Contenu\n\nContenu A\n\n"
            "## Ressource 2 — Article B\n\n"
            "| **Type** | `.txt` |\n"
            "| **ID** | `id2` |\n"
            "| **Importé** | 2024-01-02 |\n\n"
            "### Contenu\n\nContenu B\n"
        )
        f = tmp_path / "extraction_multi.md"
        f.write_text(md_content, encoding="utf-8")

        result = parse_extraction_markdown(str(f))
        assert len(result) == 2

    def test_source_id_extrait(self, tmp_path):
        # L'ID de la source doit être correctement extrait
        # du tableau markdown et stocké dans le champ "source_id".
        md_content = (
            "## Ressource 1 — Test\n\n"
            "| **Type** | `website` |\n"
            "| **ID** | `monID123` |\n"
            "| **Importé** | 2024-01-01 |\n\n"
            "### Contenu\n\nContenu test.\n"
        )
        f = tmp_path / "extraction_id.md"
        f.write_text(md_content, encoding="utf-8")

        result = parse_extraction_markdown(str(f))
        assert result[0]["source_id"] == "monID123"

    def test_ressource_sans_contenu(self, tmp_path):
        # Une ressource sans section "### Contenu" doit quand même
        # être parsée avec un contenu vide, sans lever d'exception.
        md_content = (
            "## Ressource 1 — Sans contenu\n\n"
            "| **Type** | `txt` |\n"
            "| **ID** | `id1` |\n"
            "| **Importé** | 2024-01-01 |\n\n"
        )
        f = tmp_path / "extraction_sans_contenu.md"
        f.write_text(md_content, encoding="utf-8")

        result = parse_extraction_markdown(str(f))
        assert len(result) == 1
        assert result[0]["content"] == ""


# ===========================================================================
# segment_from_extraction_markdown
# ===========================================================================

class TestSegmentFromExtractionMarkdown:
    def test_segmente_contenu(self, tmp_path):
        # Cas nominal : un fichier markdown avec du contenu suffisant.
        # La fonction doit retourner une liste de segments avec
        # les clés "segment_id" et "text" présentes dans chaque segment.
        md_content = (
            "## Ressource 1 — Article\n\n"
            "| **Type** | `website` |\n"
            "| **ID** | `src1` |\n"
            "| **Importé** | 2024-01-01 |\n\n"
            "### Contenu\n\n"
            + ("Contenu suffisant. " * 30) + "\n"
        )
        f = tmp_path / "extraction.md"
        f.write_text(md_content, encoding="utf-8")

        result = segment_from_extraction_markdown(str(f))
        assert len(result) >= 1
        assert all("segment_id" in s for s in result)
        assert all("text" in s for s in result)

    def test_ids_incrementaux(self, tmp_path):
        # Les segment_id doivent être incrémentaux en commençant à 1
        # pour permettre l'identification unique de chaque segment.
        md_content = (
            "## Ressource 1 — Article\n\n"
            "| **Type** | `txt` |\n"
            "| **ID** | `src1` |\n"
            "| **Importé** | 2024-01-01 |\n\n"
            "### Contenu\n\n"
            + ("Contenu suffisant. " * 30) + "\n"
        )
        f = tmp_path / "extraction_ids.md"
        f.write_text(md_content, encoding="utf-8")

        result = segment_from_extraction_markdown(str(f))
        ids = [s["segment_id"] for s in result]
        assert ids[0] == 1
        assert ids == list(range(1, len(ids) + 1))

    def test_ressource_sans_contenu_ignoree(self, tmp_path):
        # Une ressource avec un contenu vide doit être ignorée.
        # La fonction retourne une liste vide sans lever d'exception.
        md_content = (
            "## Ressource 1 — Vide\n\n"
            "| **Type** | `txt` |\n"
            "| **ID** | `id1` |\n"
            "| **Importé** | 2024-01-01 |\n\n"
            "### Contenu\n\n"
        )
        f = tmp_path / "extraction_vide.md"
        f.write_text(md_content, encoding="utf-8")

        result = segment_from_extraction_markdown(str(f))
        assert result == []

    def test_metadonnees_transmises(self, tmp_path):
        # Les métadonnées (source, source_type, title) doivent être
        # correctement transmises depuis la ressource vers chaque segment.
        md_content = (
            "## Ressource 1 — Mon Article\n\n"
            "| **Type** | `website` |\n"
            "| **ID** | `monSource` |\n"
            "| **Importé** | 2024-01-01 |\n\n"
            "### Contenu\n\n"
            + ("Contenu suffisant. " * 30) + "\n"
        )
        f = tmp_path / "extraction_meta.md"
        f.write_text(md_content, encoding="utf-8")

        result = segment_from_extraction_markdown(str(f))
        assert all(s["source_type"] == "website" for s in result)
        assert all(s["title"] == "Mon Article" for s in result)

    def test_longueur_coherente(self, tmp_path):
        # Le champ "length" de chaque segment doit correspondre
        # exactement à la longueur réelle du texte du segment.
        md_content = (
            "## Ressource 1 — Article\n\n"
            "| **Type** | `txt` |\n"
            "| **ID** | `src1` |\n"
            "| **Importé** | 2024-01-01 |\n\n"
            "### Contenu\n\n"
            + ("Contenu suffisant. " * 30) + "\n"
        )
        f = tmp_path / "extraction_length.md"
        f.write_text(md_content, encoding="utf-8")

        result = segment_from_extraction_markdown(str(f))
        for seg in result:
            assert seg["length"] == len(seg["text"])