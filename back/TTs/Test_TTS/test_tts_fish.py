# Version n°6/back/TTs/Test_TTS/test_tts_fish.py
"""
Tests unitaires — TTS_FISH_AUDIO.py

Vérifie que les fonctions de structuration locale (parsing, fusion de lignes) marchent.
Contient également des Mocks sur l'API Fish Audio et FFmpeg 
pour ne tester que la logique sans consommer de quota réel ni nécessiter FFmpeg installé.
"""
import sys
from pathlib import Path

# On ajoute le dossier racine "Version n°6" au PATH pour que "back.TTs..." fonctionne
root_dir = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(root_dir))

import pytest
from unittest.mock import MagicMock, patch

# Import du module à tester
from back.TTs.TTS_FISH_AUDIO import (
    TTSError,
    parse_dialogue_script,
    merge_consecutive_lines,
    get_pause_duration_ms,
    prepare_text_for_tts,
    script_to_speech,
    synthesize_line_fish_audio
)

# ===========================================================================
# parse_dialogue_script
# ===========================================================================

class TestParseDialogueScript:
    def test_parse_valid_script(self):
        script = "Paul: Bonjour à tous.\nEva: Salut, ça va.\n"
        dialogue = parse_dialogue_script(script, available_names=["Paul", "Eva"])
        assert len(dialogue) == 2
        assert dialogue[0] == ("Paul", "Bonjour à tous.")
        assert dialogue[1] == ("Eva", "Salut, ça va.")

    def test_parse_empty_script(self):
        with pytest.raises(TTSError, match="Le script est vide."):
            parse_dialogue_script("   \n  ", available_names=["Paul"])
            
    def test_parse_no_valid_lines(self):
        with pytest.raises(TTSError, match="Aucune ligne valide trouvée."):
            parse_dialogue_script("Ceci est un texte sans dialogue.\nRien du tout", available_names=["Paul"])

    def test_parse_ignore_unknown_speakers(self):
        # Si un speaker est introuvable dans la liste permise, il est ignoré
        script = "Paul: Bonjour.\nInconnu: Ce script devrait m'ignorer.\nEva: Tout à fait."
        dialogue = parse_dialogue_script(script, available_names=["Paul", "Eva"])
        assert len(dialogue) == 2
        assert dialogue[0] == ("Paul", "Bonjour.")
        assert dialogue[1] == ("Eva", "Tout à fait.")


# ===========================================================================
# merge_consecutive_lines
# ===========================================================================

class TestMergeConsecutiveLines:
    def test_merge_same_speaker_under_limit(self):
        dialogue = [
            ("Paul", "Ceci est la première phrase."),
            ("Paul", "Ceci est la seconde.")
        ]
        merged = merge_consecutive_lines(dialogue, max_chars_per_block=100)
        assert len(merged) == 1
        assert merged[0] == ("Paul", "Ceci est la première phrase. Ceci est la seconde.")

    def test_no_merge_if_too_long(self):
        dialogue = [
            ("Paul", "A" * 50),
            ("Paul", "B" * 60)
        ]
        merged = merge_consecutive_lines(dialogue, max_chars_per_block=100)
        assert len(merged) == 2

    def test_different_speakers(self):
        dialogue = [
            ("Paul", "Ceci est la première phrase."),
            ("Eva", "Ceci est la seconde.")
        ]
        merged = merge_consecutive_lines(dialogue)
        assert len(merged) == 2


# ===========================================================================
# get_pause_duration_ms
# ===========================================================================

class TestGetPauseDurationMs:
    def test_different_speakers(self):
        assert get_pause_duration_ms("Paul", "Eva") == 280

    def test_same_speaker(self):
        assert get_pause_duration_ms("Paul", "Paul") == 180

    def test_next_is_none(self):
        assert get_pause_duration_ms("Paul", None) == 0


# ===========================================================================
# prepare_text_for_tts
# ===========================================================================

class TestPrepareTextForTts:
    def test_remove_parentheses_and_quotes(self):
        assert prepare_text_for_tts('Bonjour (sourire) l\'ami " !') == "Bonjour l'ami !"
        
    def test_simplify_punctuation(self):
        assert prepare_text_for_tts("Quoi ???") == "Quoi ?"
        assert prepare_text_for_tts("Wow !!!") == "Wow !"


# ===========================================================================
# API Mock - synthesize_line_fish_audio
# ===========================================================================

class TestSynthesizeLineFishAudio:
    @patch("back.TTs.TTS_FISH_AUDIO.requests.post")
    def test_synthesize_success(self, mock_post, tmp_path):
        # On simule un retour propre de l'API avec status_code 200
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"fake MP3 bytes"
        mock_post.return_value = mock_response
        
        output_file = tmp_path / "test.mp3"
        
        # Patch FISH_AUDIO_API_KEY pour éviter l'erreur surclé vierge
        with patch("back.TTs.TTS_FISH_AUDIO.FISH_AUDIO_API_KEY", "FAKE_KEY"):
            synthesize_line_fish_audio("Texte test", "id_123", str(output_file))
            
        assert output_file.exists()
        assert output_file.read_bytes() == b"fake MP3 bytes"
        
        # Vérifions que le POST contient bien les bonnes infos d'appel
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["text"] == "Texte test"
        assert kwargs["json"]["reference_id"] == "id_123"

    @patch("back.TTs.TTS_FISH_AUDIO.requests.post")
    def test_synthesize_fail(self, mock_post, tmp_path):
        # On simule une erreur 500 API
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        output_file = tmp_path / "test.mp3"
        
        with patch("back.TTs.TTS_FISH_AUDIO.FISH_AUDIO_API_KEY", "FAKE_KEY"):
            with pytest.raises(TTSError, match="Code 500"):
                synthesize_line_fish_audio("Texte test", "id_123", str(output_file))


# ===========================================================================
# script_to_speech (Integration Complete mockée)
# ===========================================================================

class TestScriptToSpeech:
    @patch("back.TTs.TTS_FISH_AUDIO.load_voices_map")
    @patch("back.TTs.TTS_FISH_AUDIO.synthesize_line_fish_audio")
    @patch("back.TTs.TTS_FISH_AUDIO.create_silence_mp3")
    @patch("back.TTs.TTS_FISH_AUDIO.combine_audio_files_with_ffmpeg", return_value="output.mp3")
    def test_script_to_speech_full_run(self, mock_combine, mock_silence, mock_synth, mock_load, tmp_path):
        # On mocke le json.load des voix pour fausser la détection
        mock_load.return_value = {
            "Paul": "id_paul",
            "Eva": "id_eva"
        }
        
        script = "Paul: Salut l'amie.\nEva: Ca va très bien."
        
        result = script_to_speech(script, Temp_dir=str(tmp_path), temp_dir=str(tmp_path))
        
        assert result == "output.mp3"
        
        # On doit avoir synthétisé au moins les 2 répliques
        assert mock_synth.call_count == 2
        
        # La combinaison FFmpeg doit avoir été appelée à la fin
        mock_combine.assert_called_once()
        
        # La map a bien été chargée
        mock_load.assert_called_once()
