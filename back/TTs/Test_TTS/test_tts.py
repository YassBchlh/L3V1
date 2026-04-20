# Version5/back/Test_Backend/test_tts.py
"""
Tests unitaires — tts.py

Ce fichier teste les fonctions du module tts,
qui s'occupe de la synthèse vocale pour les podcasts.
Les dépendances matérielles telles que PyTorch, Coqui TTS, 
et les appels externes comme ffmpeg sont mockés pour les tests unitaires.
"""
import sys
from pathlib import Path

# On ajoute le dossier racine "Version n°6" (parent de parent de parent de parent de test_tts.py) au PATH
# path actuel: back/TTs/Test_TTS/test_tts.py
root_dir = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(root_dir))

import pytest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Mock des dépendances lourdes avant tout import (y compris torch pour éviter les soucis de cache)
# ---------------------------------------------------------------------------
_MODULES_A_MOCKER = [
    "torch",
    "torch.serialization",
    "TTS",
    "TTS.tts",
    "TTS.tts.configs",
    "TTS.tts.configs.xtts_config",
    "TTS.api",
]

for _mod in _MODULES_A_MOCKER:
    sys.modules.setdefault(_mod, MagicMock())

# Pour éviter l'erreur sur torch.serialization.add_safe_globals
sys.modules["TTS.tts.configs.xtts_config"].XttsConfig = MagicMock()

# Import du module à tester
from back.TTs.tts import (
    TTSError,
    normalize_speaker_name,
    parse_dialogue_script,
    get_language_code,
    merge_consecutive_lines,
    get_pause_duration_ms,
    prepare_text_for_tts,
    script_to_speech,
)


# ===========================================================================
# normalize_speaker_name
# ===========================================================================

class TestNormalizeSpeakerName:
    def test_normalize_aliases(self):
        # L'alias classique doit être matché
        assert normalize_speaker_name("Host") == "Voix_01"
        assert normalize_speaker_name("Expert") == "Voix_02"
        assert normalize_speaker_name("Speaker 1") == "Voix_01"
        assert normalize_speaker_name("Speaker 2") == "Voix_02"
        assert normalize_speaker_name("Intervenant 4") == "Voix_04"
        assert normalize_speaker_name("Voix 03") == "Voix_03"
    

# ===========================================================================
# parse_dialogue_script
# ===========================================================================

class TestParseDialogueScript:
    def test_parse_valid_script(self):
        # Si le format est bon, la méthode retourne une liste de tuples
        script = "Voix_01: Bonjour à tous.\nVoix_02: Salut, ça va.\n"
        dialogue = parse_dialogue_script(script)
        assert len(dialogue) == 2
        assert dialogue[0] == ("Voix_01", "Bonjour à tous.")
        assert dialogue[1] == ("Voix_02", "Salut, ça va.")

    def test_parse_with_aliases(self):
        # Les alias doivent être normalisés directement
        script = "Host: Bienvenue.\nExpert: Merci.\n"
        dialogue = parse_dialogue_script(script)
        assert len(dialogue) == 2
        assert dialogue[0] == ("Voix_01", "Bienvenue.")
        assert dialogue[1] == ("Voix_02", "Merci.")

    def test_parse_empty_script(self):
        # Un script vide doit planter avec une erreur de TTS
        with pytest.raises(TTSError, match="Le script est vide."):
            parse_dialogue_script("   \n  ")
            
    def test_parse_no_valid_lines(self):
        # Un texte sans formattage locuteur (ex: sans ':') doit planter
        with pytest.raises(TTSError, match="Aucune ligne valide trouvée."):
            parse_dialogue_script("Ceci est un texte sans dialogue.\nRien du tout à la fin de la ligne")


# ===========================================================================
# get_language_code
# ===========================================================================

class TestGetLanguageCode:
    def test_langue_fr(self):
        assert get_language_code("Français") == "fr"
        assert get_language_code("fr") == "fr"
        assert get_language_code("french") == "fr"

    def test_langue_en(self):
        assert get_language_code("English") == "en"
        assert get_language_code("anglais") == "en"

    def test_langue_default(self):
        # Si on ne donne rien ou un truc inconnu, fallback au français
        assert get_language_code("") == "fr"
        assert get_language_code("Inconnu") == "fr"


# ===========================================================================
# merge_consecutive_lines
# ===========================================================================

class TestMergeConsecutiveLines:
    def test_merge_same_speaker_under_limit(self):
        # Si la longueur cumulée est sous la limite, on fusionne
        dialogue = [
            ("Voix_01", "Ceci est la première phrase."),
            ("Voix_01", "Ceci est la seconde.")
        ]
        merged = merge_consecutive_lines(dialogue, max_chars_per_block=100)
        assert len(merged) == 1
        assert merged[0] == ("Voix_01", "Ceci est la première phrase. Ceci est la seconde.")

    def test_no_merge_if_too_long(self):
        # Si la longueur cumulée est trop grande, on force un découpage
        dialogue = [
            ("Voix_01", "A" * 50),
            ("Voix_01", "B" * 60)
        ]
        merged = merge_consecutive_lines(dialogue, max_chars_per_block=100)
        assert len(merged) == 2

    def test_different_speakers(self):
        # On ne fusionne pas deux locuteurs différents
        dialogue = [
            ("Voix_01", "Ceci est la première phrase."),
            ("Voix_02", "Ceci est la seconde.")
        ]
        merged = merge_consecutive_lines(dialogue)
        assert len(merged) == 2


# ===========================================================================
# get_pause_duration_ms
# ===========================================================================

class TestGetPauseDurationMs:
    def test_different_speakers(self):
        # Un changement de voix implique une plus grande pause
        assert get_pause_duration_ms("Voix_01", "Voix_02") == 280

    def test_same_speaker(self):
        # Le silence est plus faible en plein milieu du locuteur
        assert get_pause_duration_ms("Voix_01", "Voix_01") == 180

    def test_next_is_none(self):
        # Pas de pause attendue si c'est la fin
        assert get_pause_duration_ms("Voix_01", None) == 0


# ===========================================================================
# prepare_text_for_tts
# ===========================================================================

class TestPrepareTextForTts:
    def test_remove_parentheses_and_quotes(self):
        assert prepare_text_for_tts("Bonjour (ca va) l'ami \"!") == "Bonjour  l'ami !"
        
    def test_simplify_punctuation(self):
        assert prepare_text_for_tts("Quoi ???") == "Quoi ?"
        assert prepare_text_for_tts("OK...") == "OK."
        
    def test_ajustement_respiration(self):
        # Test sur la division ou découpage d'un texte plus long
        assert " . " not in prepare_text_for_tts("Bonjour.") # Pas d'espace en trop


# ===========================================================================
# script_to_speech
# ===========================================================================

class TestScriptToSpeech:
    @patch("back.TTs.tts.get_all_voices")
    @patch("back.TTs.tts.synthesize_line_with_coqui")
    @patch("back.TTs.tts.create_silence_wav")
    @patch("back.TTs.tts.combine_audio_files_with_ffmpeg", return_value="output.mp3")
    def test_script_to_speech_full_run(self, mock_combine, mock_silence, mock_synth, mock_voices, tmp_path):
        # On mocke le retour du mapping des voix wav
        mock_voices.return_value = {
            "Voix_01": "path/v1.wav",
            "Voix_02": "path/v2.wav",
            "Voix_03": "path/v3.wav",
            "Voix_04": "path/v4.wav",
        }
        
        script = "Voix_01: Salut l'ami.\nVoix_02: Ca va très bien."
        
        # Ce test assure que script_to_speech orchestre bien : extraction de texte, la synthèse de chaque ligne puis FFmpeg
        result = script_to_speech(script, podcast_language="Français", temp_dir=str(tmp_path))
        
        assert result == "output.mp3"
        # On doit avoir synthétisé au moins les 2 répliques
        assert mock_synth.call_count == 2
        # La combinaison doit avoir été faite à la fin
        mock_combine.assert_called_once()
        # On valide la recherche des voix
        mock_voices.assert_called_once_with("Français")
