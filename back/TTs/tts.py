
# Version5/back/TTs/tts.py
# type: ignore
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import re
 
 
import torch
import torch.serialization
 
from TTS.tts.configs.xtts_config import XttsConfig
 
# Patch PyTorch 2.6+ / Coqui XTTS
torch.serialization.add_safe_globals([XttsConfig])
 
_original_torch_load = torch.load
 
def _patched_torch_load(*args, **kwargs):
    if "weights_only" not in kwargs:
        kwargs["weights_only"] = False
    return _original_torch_load(*args, **kwargs)
 
torch.load = _patched_torch_load
 
from TTS.api import TTS
 
# ============================================================
# CONFIGURATION COQUI TTS
# ============================================================
 
TTS_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
 
BASE_DIR = Path(__file__).resolve().parent
VOICES_DIR = BASE_DIR / "Voices_wav"
 
 
class TTSError(Exception):
    pass
 
 
_tts_instance: Optional[TTS] = None
 
 
def get_tts_model() -> TTS:
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = TTS(TTS_MODEL_NAME)
    return _tts_instance
 
 
def normalize_speaker_name(raw_speaker: str) -> str:
    speaker = raw_speaker.strip()
 
    aliases = {
        "Host": "Voix_01",
        "Expert": "Voix_02",
        "Speaker 1": "Voix_01",
        "Speaker 2": "Voix_02",
        "Speaker 3": "Voix_03",
        "Speaker 4": "Voix_04",
        "Intervenant 1": "Voix_01",
        "Intervenant 2": "Voix_02",
        "Intervenant 3": "Voix_03",
        "Intervenant 4": "Voix_04",
        "Voix 01": "Voix_01",
        "Voix 02": "Voix_02",
        "Voix 03": "Voix_03",
        "Voix 04": "Voix_04",
    }
 
    return aliases.get(speaker, speaker)
 
 
def parse_dialogue_script(script_text: str) -> List[Tuple[str, str]]:
    if not script_text or not script_text.strip():
        raise TTSError("Le script est vide.")
 
    dialogue: List[Tuple[str, str]] = []
 
    for raw_line in script_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
 
        match = re.match(r"^([^:]+):\s*(.+)$", line)
        if not match:
            continue
 
        raw_speaker = match.group(1).strip()
        text = match.group(2).strip()
 
        if not text:
            continue
 
        speaker = normalize_speaker_name(raw_speaker)
 
        if speaker not in {"Voix_01", "Voix_02", "Voix_03", "Voix_04"}:
            continue
 
        dialogue.append((speaker, text))
 
    if not dialogue:
        raise TTSError(
            "Aucune ligne valide trouvée. "
            "Le script doit contenir des lignes commençant par "
            "'Voix_01:', 'Voix_02:', 'Voix_03:' ou 'Voix_04:'."
        )
 
    return dialogue
 
 
def get_language_code(podcast_language: str = "Français") -> str:
    lang = (podcast_language or "").strip().lower()
 
    if lang in {"fr", "français", "francais", "french"}:
        return "fr"
    if lang in {"en", "english", "anglais"}:
        return "en"
 
    return "fr"
 
 
def get_all_voices(podcast_language: str, voices_override: Dict[str, str] = None) -> Dict[str, str]:
    """
    Retourne un mapping speaker -> fichier wav.
    Si voices_override est fourni, utilise ces WAV directement.
    Sinon, utilise les WAV par défaut selon la langue.
    """
    if voices_override:
        result = {}
        for key, wav_filename in voices_override.items():
            wav_path = VOICES_DIR / wav_filename
            if not wav_path.exists():
                raise TTSError(f"Voix introuvable : {wav_path}")
            result[key] = str(wav_path)
        print(f"[TTS] Voices override utilisé : {result}")
        return result
 
    lang = (podcast_language or "").strip().lower()
 
    if lang in {"fr", "français", "francais", "french"}:
        voices = {
            "Voix_01": str(VOICES_DIR / "fr_female_01.wav"),
            "Voix_02": str(VOICES_DIR / "fr_male_03.wav"),
            "Voix_03": str(VOICES_DIR / "fr_female_02.wav"),
            "Voix_04": str(VOICES_DIR / "fr_male_02.wav"),
        }
    else:
        voices = {
            "Voix_01": str(VOICES_DIR / "en_female_01.wav"),
            "Voix_02": str(VOICES_DIR / "en_male_01.wav"),
            "Voix_03": str(VOICES_DIR / "en_female_02.wav"),
            "Voix_04": str(VOICES_DIR / "en_male_02.wav"),
        }
 
    for speaker, wav_path in voices.items():
        if not Path(wav_path).exists():
            raise TTSError(
                f"Voix introuvable pour {speaker} : {wav_path}\n"
                f"Vérifie que le fichier existe bien dans voices_wav."
            )
 
    return voices
 
 
def synthesize_line_with_coqui(
    text: str,
    speaker_wav: str,
    language: str,
    output_file: str,
) -> None:
    if not text or not text.strip():
        raise TTSError("Texte vide pour la synthèse.")
 
    tts = get_tts_model()
 
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
 
    try:
        tts.tts_to_file(
            text=text,
            speaker_wav=speaker_wav,
            language=language,
            file_path=str(output_path),
            speed=1.15
        )
    except Exception as e:
        raise TTSError(f"Erreur Coqui TTS : {e}")
 
 
def combine_audio_files_with_ffmpeg(audio_files: List[str], output_file: str) -> str:
    if not audio_files:
        raise TTSError("Aucun fichier audio à concaténer.")
 
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
 
    list_file = output_path.parent / "tts_concat_list.txt"
 
    with open(list_file, "w", encoding="utf-8") as f:
        for audio in audio_files:
            f.write(f"file '{Path(audio).resolve()}'\n")
 
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-ar", "22050",
        "-ac", "1",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(output_path),
    ]
 
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        error_msg = (e.stderr or e.stdout or str(e)).strip()
        raise TTSError(f"Erreur ffmpeg concat : {error_msg}")
 
    return str(output_path)
 
 
def script_to_speech(
    script_text: str,
    podcast_language: str = "Français",
    output_file: str = "speech.mp3",
    temp_dir: str = "outputs/tts_tmp",
    voices_override: Dict[str, str] = None,
) -> str:
    dialogue = parse_dialogue_script(script_text)
    dialogue = merge_consecutive_lines(dialogue, max_chars_per_block=260)
 
    print(f"[TTS] Nombre de blocs après fusion : {len(dialogue)}")
 
    language = get_language_code(podcast_language)
    voices = get_all_voices(podcast_language, voices_override=voices_override)
 
    tmp_path = Path(temp_dir)
    tmp_path.mkdir(parents=True, exist_ok=True)
 
    generated_files: List[str] = []
 
    for i, (speaker, text) in enumerate(dialogue, start=1):
        speaker_wav = voices.get(speaker)
        if not speaker_wav:
            print(f"[TTS] Voix non trouvée pour {speaker}, skip.")
            continue
 
        prepared_text = prepare_text_for_tts(text)
        raw_output = tmp_path / f"line_{i:03d}_raw.wav"
 
        print(f"[TTS {i}/{len(dialogue)}] {speaker} | {len(prepared_text)} caractères")
 
        synthesize_line_with_coqui(
            text=prepared_text,
            speaker_wav=speaker_wav,
            language=language,
            output_file=str(raw_output),
        )
 
        generated_files.append(str(raw_output))
 
        next_speaker = dialogue[i][0] if i < len(dialogue) else None
        pause_ms = get_pause_duration_ms(speaker, next_speaker)
 
        if pause_ms > 0:
            silence_file = tmp_path / f"pause_{i:03d}.wav"
            create_silence_wav(str(silence_file), duration_ms=pause_ms)
            generated_files.append(str(silence_file))
 
    final_audio_path = combine_audio_files_with_ffmpeg(
        audio_files=generated_files,
        output_file=output_file
    )
 
    print(f"\nAudio final généré : {final_audio_path}")
    return final_audio_path
 
 
def merge_consecutive_lines(
    dialogue: List[Tuple[str, str]],
    max_chars_per_block: int = 400
) -> List[Tuple[str, str]]:
    if not dialogue:
        return []
 
    merged: List[Tuple[str, str]] = []
    current_speaker, current_text = dialogue[0]
 
    for speaker, text in dialogue[1:]:
        candidate = current_text + " " + text
        if speaker == current_speaker and len(candidate) <= max_chars_per_block:
            current_text = candidate
        else:
            merged.append((current_speaker, current_text.strip()))
            current_speaker, current_text = speaker, text
 
    merged.append((current_speaker, current_text.strip()))
    return merged
 
 
def create_silence_wav(output_file: str, duration_ms: int = 220) -> str:
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
 
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=mono:sample_rate=22050",
        "-t", str(duration_ms / 1000),
        "-ar", "22050",
        "-ac", "1",
        str(output_path),
    ]
 
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        error_msg = (e.stderr or e.stdout or str(e)).strip()
        raise TTSError(f"Erreur création silence : {error_msg}")
 
    return str(output_path)
 
 
def get_pause_duration_ms(current_speaker: str, next_speaker: str | None) -> int:
    if next_speaker is None:
        return 0
    if current_speaker != next_speaker:
        return 280
    return 180
 
 
def prepare_text_for_tts(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"[\"""]", "", text)
    text = re.sub(r"([!?]){2,}", r"\1", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r",", ", ", text)
    text = re.sub(r"\.", ". ", text)
 
    sentences = re.split(r"(?<=[.!?])\s+", text)
    new_sentences = []
 
    for s in sentences:
        words = s.split()
        if len(words) > 20:
            mid = len(words) // 2
            new_sentences.append(" ".join(words[:mid]) + ".")
            new_sentences.append(" ".join(words[mid:]))
        else:
            new_sentences.append(s)
 
    return " ".join(new_sentences).strip()
 
 
if __name__ == "__main__":
    sample_script = """
Voix_01: Bonjour à tous et bienvenue dans ce podcast.
Voix_02: Aujourd'hui, nous allons explorer plusieurs sujets très intéressants.
""".strip()
 
    try:
        audio_path = script_to_speech(
            script_text=sample_script,
            podcast_language="Français",
            output_file="speech.mp3"
        )
        print(f"MP3 généré : {audio_path}")
    except TTSError as e:
        print("Erreur :", e)
 