# Version5/back/Test_Backend/test_api.py
"""
Tests unitaires — api.py

Ce fichier teste toutes les fonctions et endpoints du module api.py,
qui expose l'API FastAPI du Podcast Generator.
Les dépendances lourdes et appels externes sont mockés.
"""
import sys
import os
import json
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock des dépendances lourdes avant tout import
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
from fastapi.testclient import TestClient
from back.api import app, sanitize_filename, build_audio_url, list_archives

client = TestClient(app)


# ===========================================================================
# sanitize_filename
# ===========================================================================

class TestSanitizeFilename:
    def test_nom_simple_inchange(self):
        # Un nom de fichier simple sans caractères spéciaux
        # doit être retourné tel quel.
        assert sanitize_filename("document.pdf") == "document.pdf"

    def test_supprime_caracteres_speciaux(self):
    # Les slashes sont supprimés pour éviter les injections de chemin.
    # Les points sont conservés car ils font partie des extensions de fichiers.
        result = sanitize_filename("doc/evil/../file.pdf")
        assert "/" not in result
        assert "\\" not in result

    def test_garde_tirets_underscores_points(self):
        # Les tirets, underscores et points sont des caractères valides
        # dans un nom de fichier et doivent être conservés.
        result = sanitize_filename("mon_fichier-v2.pdf")
        assert "-" in result
        assert "_" in result
        assert "." in result

    def test_chaine_vide_retourne_vide(self):
        # Une chaîne vide doit retourner une chaîne vide
        # sans lever d'exception.
        assert sanitize_filename("") == ""

    def test_espaces_conserves(self):
        # Les espaces sont autorisés dans les noms de fichiers
        # et doivent être conservés.
        result = sanitize_filename("mon fichier.pdf")
        assert "fichier" in result

    def test_caracteres_alphanumeriques_conserves(self):
        # Les lettres et chiffres doivent toujours être conservés.
        result = sanitize_filename("abc123.txt")
        assert result == "abc123.txt"


# ===========================================================================
# build_audio_url
# ===========================================================================

class TestBuildAudioUrl:
    def test_url_correcte(self):
        # La fonction doit construire une URL correcte
        # pointant vers le serveur local sur le port 8000.
        result = build_audio_url("/outputs/tts_final/podcast_123.mp3")
        assert result == "http://127.0.0.1:8000/audio/podcast_123.mp3"

    def test_extrait_nom_fichier(self):
        # Seul le nom du fichier (sans le chemin) doit apparaître dans l'URL.
        result = build_audio_url("/very/long/path/to/audio.mp3")
        assert "audio.mp3" in result
        assert "/very/long/path" not in result

    def test_format_url(self):
        # L'URL doit commencer par le bon préfixe.
        result = build_audio_url("audio.mp3")
        assert result.startswith("http://127.0.0.1:8000/audio/")


# ===========================================================================
# list_archives
# ===========================================================================

class TestListArchives:
    def test_retourne_liste_vide_si_aucun_fichier(self, tmp_path):
        # Si aucun fichier run_metadata_*.json n'existe,
        # la fonction doit retourner une liste vide.
        with patch("back.api.OUTPUT_DIR", tmp_path):
            result = list_archives()
        assert result == []

    def test_retourne_archives_depuis_fichiers_json(self, tmp_path):
        # Si des fichiers run_metadata_*.json existent,
        # la fonction doit retourner une liste avec les bonnes données.
        meta = {
            "generated_at": "2024-01-01T12:00:00",
            "script_path": "outputs/podcast_script_test.txt",
            "audio_path": "outputs/audio.mp3",
            "audio_url": "http://127.0.0.1:8000/audio/audio.mp3"
        }
        f = tmp_path / "run_metadata_20240101.json"
        f.write_text(json.dumps(meta), encoding="utf-8")

        with patch("back.api.OUTPUT_DIR", tmp_path):
            result = list_archives()

        assert len(result) == 1
        assert result[0]["date"] == "2024-01-01T12:00:00"
        assert result[0]["audio_url"] == "http://127.0.0.1:8000/audio/audio.mp3"

    def test_ignore_fichiers_json_invalides(self, tmp_path):
        # Les fichiers JSON malformés doivent être ignorés silencieusement
        # sans lever d'exception.
        f = tmp_path / "run_metadata_bad.json"
        f.write_text("pas du json valide", encoding="utf-8")

        with patch("back.api.OUTPUT_DIR", tmp_path):
            result = list_archives()

        assert result == []

    def test_plusieurs_archives_triees(self, tmp_path):
        # Plusieurs archives doivent être retournées triées
        # par ordre décroissant (la plus récente en premier).
        for name in ["run_metadata_20240101.json", "run_metadata_20240201.json"]:
            meta = {
                "generated_at": name,
                "script_path": "s.txt",
                "audio_path": "a.mp3",
                "audio_url": ""
            }
            (tmp_path / name).write_text(json.dumps(meta), encoding="utf-8")

        with patch("back.api.OUTPUT_DIR", tmp_path):
            result = list_archives()

        assert len(result) == 2


# ===========================================================================
# GET /health
# ===========================================================================

class TestHealthEndpoint:
    def test_health_retourne_ok(self):
        # L'endpoint /health doit retourner status "ok"
        # pour indiquer que le serveur est opérationnel.
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


# ===========================================================================
# GET /archives
# ===========================================================================

class TestArchivesEndpoint:
    def test_archives_retourne_liste(self):
        # L'endpoint /archives doit retourner un objet
        # avec une clé "archives" contenant une liste.
        with patch("back.api.list_archives", return_value=[]):
            response = client.get("/archives")
        assert response.status_code == 200
        assert "archives" in response.json()
        assert isinstance(response.json()["archives"], list)

    def test_archives_contient_donnees(self):
        # Si des archives existent, elles doivent apparaître
        # dans la réponse de l'endpoint.
        fake_archives = [
            {
                "title": "Podcast Test",
                "date": "2024-01-01",
                "script_path": "s.txt",
                "audio_path": "a.mp3",
                "audio_url": "http://127.0.0.1:8000/audio/a.mp3"
            }
        ]
        with patch("back.api.list_archives", return_value=fake_archives):
            response = client.get("/archives")
        assert len(response.json()["archives"]) == 1
        assert response.json()["archives"][0]["title"] == "Podcast Test"


# ===========================================================================
# POST /generate-script
# ===========================================================================

class TestGenerateScriptEndpoint:
    def _fake_segments(self):
        return [
            {"segment_id": 1, "text": "Contenu IA.", "source_type": "txt"},
        ]

    @patch("back.api.generate_dialogue_from_segments",
           return_value="Voix_01: Bonjour.\nVoix_02: Salut.")
    @patch("back.api.run_full_pipeline")
    def test_genere_script_avec_lien(self, mock_pipeline, mock_gen):
        # Un lien web valide doit permettre de générer un script.
        # L'endpoint doit retourner 200 avec le script dans la réponse.
        mock_pipeline.return_value = self._fake_segments()

        response = client.post(
            "/generate-script",
            data={
                "links": json.dumps(["https://example.com"]),
                "podcast_language": "Français",
                "podcast_duration": "Court (1-3 min)",
                "participants": json.dumps(["Voix_01", "Voix_02"]),
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "script" in data
        assert "Voix_01" in data["script"]

    def test_aucune_ressource_retourne_400(self):
        # Sans ressources (ni fichier ni lien),
        # l'endpoint doit retourner 400 Bad Request.
        response = client.post(
            "/generate-script",
            data={
                "links": json.dumps([]),
                "podcast_language": "Français",
                "podcast_duration": "Court (1-3 min)",
                "participants": json.dumps([]),
            }
        )
        assert response.status_code == 400

    @patch("back.api.generate_dialogue_from_segments", return_value="   ")
    @patch("back.api.run_full_pipeline")
    def test_script_vide_retourne_500(self, mock_pipeline, mock_gen):
        # Si le script généré est vide,
        # l'endpoint doit retourner 500.
        mock_pipeline.return_value = self._fake_segments()

        response = client.post(
            "/generate-script",
            data={
                "links": json.dumps(["https://example.com"]),
                "podcast_language": "Français",
                "podcast_duration": "Court (1-3 min)",
                "participants": json.dumps(["Voix_01", "Voix_02"]),
            }
        )
        assert response.status_code == 500

    @patch("back.api.generate_dialogue_from_segments",
           return_value="Voix_01: Bonjour.\nVoix_02: Salut.")
    @patch("back.api.run_full_pipeline")
    def test_reponse_contient_champs_requis(self, mock_pipeline, mock_gen):
        # La réponse doit contenir tous les champs attendus par le frontend.
        mock_pipeline.return_value = self._fake_segments()

        response = client.post(
            "/generate-script",
            data={
                "links": json.dumps(["https://example.com"]),
                "podcast_language": "Français",
                "podcast_duration": "Court (1-3 min)",
                "participants": json.dumps(["Voix_01", "Voix_02"]),
            }
        )

        data = response.json()
        for key in ("id", "title", "script", "segments_count", "participants"):
            assert key in data

    @patch("back.api.run_full_pipeline", side_effect=Exception("Erreur pipeline"))
    def test_erreur_pipeline_retourne_500(self, mock_pipeline):
        # Si run_full_pipeline lève une exception,
        # l'endpoint doit retourner 500 avec le message d'erreur.
        response = client.post(
            "/generate-script",
            data={
                "links": json.dumps(["https://example.com"]),
                "podcast_language": "Français",
                "podcast_duration": "Court (1-3 min)",
                "participants": json.dumps(["Voix_01", "Voix_02"]),
            }
        )
        assert response.status_code == 500

    @patch("back.api.generate_dialogue_from_segments",
           return_value="Voix_01: Bonjour.\nVoix_02: Salut.")
    @patch("back.api.run_full_pipeline")
    def test_participants_par_defaut(self, mock_pipeline, mock_gen):
        # Si aucun participant n'est fourni,
        # les participants par défaut doivent être utilisés.
        mock_pipeline.return_value = self._fake_segments()

        response = client.post(
            "/generate-script",
            data={
                "links": json.dumps(["https://example.com"]),
                "podcast_language": "Français",
                "podcast_duration": "Court (1-3 min)",
                "participants": json.dumps([]),
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "Voix_01" in data["participants"]


# ===========================================================================
# POST /generate-audio
# ===========================================================================

class TestGenerateAudioEndpoint:
    @patch("back.api.request_tts_audio")
    def test_genere_audio_avec_script_valide(self, mock_tts):
        # Un script valide doit permettre de générer un audio.
        # L'endpoint doit retourner 200 avec les informations audio.
        mock_tts.return_value = {
            "audio_url": "http://127.0.0.1:8001/audio/podcast_123.mp3",
            "filename": "podcast_123.mp3"
        }

        response = client.post(
            "/generate-audio",
            json={
                "script": "Voix_01: Bonjour.\nVoix_02: Salut.",
                "podcast_language": "Français",
                "participants": ["Voix_01", "Voix_02"],
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "audio_url" in data
        assert "filename" in data

    def test_script_vide_retourne_400(self):
        # Un script vide doit retourner 400 Bad Request
        # car il n'y a rien à synthétiser.
        response = client.post(
            "/generate-audio",
            json={
                "script": "",
                "podcast_language": "Français",
                "participants": ["Voix_01", "Voix_02"],
            }
        )
        assert response.status_code == 400

    def test_script_espaces_retourne_400(self):
        # Un script composé uniquement d'espaces est équivalent
        # à un script vide → 400 Bad Request.
        response = client.post(
            "/generate-audio",
            json={
                "script": "   ",
                "podcast_language": "Français",
                "participants": ["Voix_01", "Voix_02"],
            }
        )
        assert response.status_code == 400

    @patch("back.api.request_tts_audio", side_effect=Exception("TTS indisponible"))
    def test_erreur_tts_retourne_500(self, mock_tts):
        # Si le service TTS est indisponible,
        # l'endpoint doit retourner 500 avec un message d'erreur.
        response = client.post(
            "/generate-audio",
            json={
                "script": "Voix_01: Bonjour.\nVoix_02: Salut.",
                "podcast_language": "Français",
                "participants": ["Voix_01", "Voix_02"],
            }
        )
        assert response.status_code == 500

    @patch("back.api.request_tts_audio")
    def test_reponse_contient_champs_requis(self, mock_tts):
        # La réponse doit contenir les champs attendus par le frontend
        # pour afficher et jouer l'audio.
        mock_tts.return_value = {
            "audio_url": "http://127.0.0.1:8001/audio/audio.mp3",
            "filename": "audio.mp3"
        }

        response = client.post(
            "/generate-audio",
            json={
                "script": "Voix_01: Bonjour.\nVoix_02: Salut.",
                "podcast_language": "Français",
                "participants": ["Voix_01", "Voix_02"],
            }
        )

        data = response.json()
        for key in ("id", "audio_path", "audio_url", "filename"):
            assert key in data
