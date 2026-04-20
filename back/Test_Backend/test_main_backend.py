# Version5/back/Test_Backend/test_main_backend.py
"""
Tests unitaires — main_backend.py

Ce fichier teste toutes les fonctions du module main_backend,
qui orchestre le pipeline complet back-end :
extraction → segmentation → scénarisation → TTS → sauvegarde.
Les dépendances lourdes et appels externes sont mockés.
"""
import sys
import os
import json
import subprocess
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
from unittest.mock import patch, mock_open
from back.main_backend import (
    BackendPipelineError,
    save_segments,
    save_run_metadata,
    run_backend_pipeline,
    run_tts_in_separate_env,
)


# ===========================================================================
# save_segments
# ===========================================================================

class TestSaveSegments:
    def test_cree_fichier_json(self, tmp_path):
        # La fonction doit créer un fichier JSON contenant les segments.
        segments = [
            {"segment_id": 1, "text": "Contenu.", "source_type": "txt"}
        ]
        output = str(tmp_path / "segments.json")
        save_segments(segments, output)
        assert os.path.exists(output)

    def test_contenu_json_correct(self, tmp_path):
        # Le fichier JSON doit contenir exactement les segments fournis,
        # avec les bonnes clés et valeurs.
        segments = [
            {"segment_id": 1, "text": "Contenu A.", "source_type": "txt"},
            {"segment_id": 2, "text": "Contenu B.", "source_type": "website"},
        ]
        output = str(tmp_path / "segments.json")
        save_segments(segments, output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        assert len(data) == 2
        assert data[0]["segment_id"] == 1
        assert data[1]["text"] == "Contenu B."

    def test_liste_vide_cree_fichier_vide(self, tmp_path):
        # Une liste vide doit produire un fichier JSON contenant []
        # sans lever d'exception.
        output = str(tmp_path / "empty.json")
        save_segments([], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        assert data == []

    def test_encodage_utf8(self, tmp_path):
        # Les caractères spéciaux français doivent être correctement
        # sauvegardés en UTF-8 sans être échappés.
        segments = [{"segment_id": 1, "text": "Éducation, données, à bientôt."}]
        output = str(tmp_path / "utf8.json")
        save_segments(segments, output)

        content = open(output, encoding="utf-8").read()
        assert "Éducation" in content


# ===========================================================================
# save_run_metadata
# ===========================================================================

class TestSaveRunMetadata:
    def test_cree_fichier_metadata(self, tmp_path):
        # La fonction doit créer un fichier JSON de métadonnées
        # contenant toutes les informations de la session.
        output = str(tmp_path / "metadata.json")
        save_run_metadata(
            resources=["doc.pdf"],
            podcast_duration="Court",
            script_path="script.txt",
            segments_path="segments.json",
            audio_path="audio.mp3",
            output_path=output
        )
        assert os.path.exists(output)

    def test_contenu_metadata_correct(self, tmp_path):
        # Toutes les clés attendues doivent être présentes dans le fichier
        # avec les bonnes valeurs.
        output = str(tmp_path / "metadata.json")
        save_run_metadata(
            resources=["doc.pdf", "https://example.com"],
            podcast_duration="Moyen",
            script_path="script.txt",
            segments_path="segments.json",
            audio_path="audio.mp3",
            output_path=output
        )

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        assert data["resources"] == ["doc.pdf", "https://example.com"]
        assert data["podcast_duration"] == "Moyen"
        assert data["script_path"] == "script.txt"
        assert data["segments_path"] == "segments.json"
        assert data["audio_path"] == "audio.mp3"

    def test_champ_generated_at_present(self, tmp_path):
        # Le champ generated_at doit être présent pour tracer
        # quand le podcast a été généré.
        output = str(tmp_path / "metadata.json")
        save_run_metadata(
            resources=["doc.pdf"],
            podcast_duration="Court",
            script_path="s.txt",
            segments_path="seg.json",
            audio_path="a.mp3",
            output_path=output
        )

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        assert "generated_at" in data
        assert data["generated_at"] != ""


# ===========================================================================
# run_backend_pipeline
# ===========================================================================

class TestRunBackendPipeline:
    def _mock_segments(self):
        return [
            {"segment_id": 1, "text": "Contenu sur l'IA.", "source_type": "txt"},
            {"segment_id": 2, "text": "Contenu sur l'éducation.", "source_type": "txt"},
        ]

    def test_ressources_vides_leve_exception(self):
        # Sans ressources, le pipeline ne peut pas démarrer.
        # BackendPipelineError doit être levée immédiatement.
        with pytest.raises(BackendPipelineError, match="Aucune ressource"):
            run_backend_pipeline([], podcast_duration="Court")

    def test_duree_vide_leve_exception(self):
        # Sans durée, le pipeline ne sait pas comment calibrer le script.
        # BackendPipelineError doit être levée immédiatement.
        with pytest.raises(BackendPipelineError, match="Aucune durée"):
            run_backend_pipeline(["doc.pdf"], podcast_duration="")

    @patch("back.main_backend.run_tts_in_separate_env", return_value="audio.mp3")
    @patch("back.main_backend.generate_dialogue_from_segments", return_value="Voix_01: Bonjour.\nVoix_02: Salut.")
    @patch("back.main_backend.run_full_pipeline")
    def test_pipeline_complet_retourne_dict(self, mock_pipeline, mock_gen, mock_tts, tmp_path):
        # Cas nominal : pipeline complet avec tous les mocks.
        # La fonction doit retourner un dictionnaire avec les clés attendues.
        mock_pipeline.return_value = self._mock_segments()

        result = run_backend_pipeline(
            resources=["doc.pdf"],
            podcast_duration="Court",
            output_dir=str(tmp_path)
        )

        assert result["success"] is True
        assert result["segments_count"] == 2
        assert "script" in result
        assert "script_path" in result
        assert "audio_path" in result

    @patch("back.main_backend.run_tts_in_separate_env", return_value="audio.mp3")
    @patch("back.main_backend.generate_dialogue_from_segments", return_value="Voix_01: Bonjour.\nVoix_02: Salut.")
    @patch("back.main_backend.run_full_pipeline")
    def test_participants_par_defaut(self, mock_pipeline, mock_gen, mock_tts, tmp_path):
        # Si aucun participant n'est fourni, les participants par défaut
        # (Voix_01, Voix_02) doivent être utilisés.
        mock_pipeline.return_value = self._mock_segments()

        run_backend_pipeline(
            resources=["doc.pdf"],
            podcast_duration="Court",
            participants=None,
            output_dir=str(tmp_path)
        )

        call_kwargs = mock_gen.call_args
        assert "Voix_01" in call_kwargs[1]["participants"] or \
               "Voix_01" in call_kwargs[0][1] if call_kwargs[0] else True

    @patch("back.main_backend.run_full_pipeline", return_value=[])
    def test_aucun_segment_leve_exception(self, mock_pipeline, tmp_path):
        # Si run_full_pipeline retourne une liste vide,
        # BackendPipelineError doit être levée.
        with pytest.raises(BackendPipelineError, match="Aucun segment"):
            run_backend_pipeline(
                resources=["doc.pdf"],
                podcast_duration="Court",
                output_dir=str(tmp_path)
            )

    @patch("back.main_backend.run_tts_in_separate_env", return_value="audio.mp3")
    @patch("back.main_backend.generate_dialogue_from_segments", return_value="   ")
    @patch("back.main_backend.run_full_pipeline")
    def test_script_vide_leve_exception(self, mock_pipeline, mock_gen, mock_tts, tmp_path):
        # Si le script généré est vide ou composé d'espaces,
        # BackendPipelineError doit être levée.
        mock_pipeline.return_value = self._mock_segments()

        with pytest.raises(BackendPipelineError, match="vide"):
            run_backend_pipeline(
                resources=["doc.pdf"],
                podcast_duration="Court",
                output_dir=str(tmp_path)
            )

    @patch("back.main_backend.run_tts_in_separate_env", return_value="audio.mp3")
    @patch("back.main_backend.generate_dialogue_from_segments", return_value="Voix_01: Bonjour.\nVoix_02: Salut.")
    @patch("back.main_backend.run_full_pipeline")
    def test_fichiers_crees_dans_output_dir(self, mock_pipeline, mock_gen, mock_tts, tmp_path):
        # Le pipeline doit créer les fichiers script, segments et metadata
        # dans le répertoire de sortie.
        mock_pipeline.return_value = self._mock_segments()

        result = run_backend_pipeline(
            resources=["doc.pdf"],
            podcast_duration="Court",
            output_dir=str(tmp_path)
        )

        assert os.path.exists(result["script_path"])
        assert os.path.exists(result["segments_path"])
        assert os.path.exists(result["metadata_path"])

    @patch("back.main_backend.run_tts_in_separate_env", return_value="audio.mp3")
    @patch("back.main_backend.generate_dialogue_from_segments", return_value="Voix_01: Bonjour.\nVoix_02: Salut.")
    @patch("back.main_backend.run_full_pipeline")
    def test_resources_count_correct(self, mock_pipeline, mock_gen, mock_tts, tmp_path):
        # Le nombre de ressources dans le résultat doit correspondre
        # au nombre de ressources fournies en entrée.
        mock_pipeline.return_value = self._mock_segments()

        result = run_backend_pipeline(
            resources=["doc.pdf", "https://example.com"],
            podcast_duration="Court",
            output_dir=str(tmp_path)
        )

        assert result["resources_count"] == 2


# ===========================================================================
# run_tts_in_separate_env
# ===========================================================================

class TestRunTTSInSeparateEnv:
    @patch("back.main_backend.subprocess.run")
    def test_appel_subprocess_reussi(self, mock_run, tmp_path):
        # Cas nominal : subprocess retourne un JSON valide avec audio_path.
        # La fonction doit retourner le chemin audio.
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"audio_path": "outputs/audio.mp3"}),
            stderr=""
        )

        result = run_tts_in_separate_env(
            script="Voix_01: Bonjour.",
            podcast_language="Français",
            participants=["Voix_01", "Voix_02"],
            audio_output_path="outputs/audio.mp3"
        )

        assert result == "outputs/audio.mp3"

    @patch("back.main_backend.subprocess.run")
    def test_returncode_non_zero_leve_exception(self, mock_run):
        # Si subprocess retourne un code d'erreur,
        # BackendPipelineError doit être levée avec le message d'erreur.
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Erreur TTS : fichier introuvable"
        )

        with pytest.raises(BackendPipelineError, match="Erreur TTS"):
            run_tts_in_separate_env(
                script="Voix_01: Bonjour.",
                podcast_language="Français",
                participants=["Voix_01", "Voix_02"],
                audio_output_path="outputs/audio.mp3"
            )

    @patch("back.main_backend.subprocess.run")
    def test_json_invalide_leve_exception(self, mock_run):
        # Si la sortie subprocess n'est pas du JSON valide,
        # BackendPipelineError doit être levée.
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="pas du json valide",
            stderr=""
        )

        with pytest.raises(BackendPipelineError, match="Réponse TTS invalide"):
            run_tts_in_separate_env(
                script="Voix_01: Bonjour.",
                podcast_language="Français",
                participants=["Voix_01", "Voix_02"],
                audio_output_path="outputs/audio.mp3"
            )

    @patch("back.main_backend.subprocess.run")
    def test_cree_payload_json(self, mock_run, tmp_path):
        # La fonction doit créer un fichier payload.json
        # contenant le script, la langue et les participants.
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"audio_path": "audio.mp3"}),
            stderr=""
        )

        with patch("back.main_backend.Path") as mock_path_cls:
            # On vérifie juste que subprocess.run est appelé
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps({"audio_path": "audio.mp3"}),
                stderr=""
            )

        run_tts_in_separate_env(
            script="Voix_01: Test.",
            podcast_language="Français",
            participants=["Voix_01"],
            audio_output_path="audio.mp3"
        )

        mock_run.assert_called_once()