# Version n°6/back/TTs/TTS_FISH_AUDIO.py
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict
import re
import json
import requests
import sys

# ============================================================
# CONFIGURATION FISH AUDIO
# ============================================================

# ⚠️ REMPLACEZ CETTE CHAÎNE PAR VOTRE CLÉ API FISH AUDIO ⚠️
FISH_AUDIO_API_KEY = "eb3ccb8b478f446ba5bdbfbe1c2140c7"

FISH_AUDIO_API_URL = "https://api.fish.audio/v1/tts"

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent
VOIX_JSON_PATH = PROJECT_ROOT / "voix.json"

class TTSError(Exception):
    pass


def load_voices_map() -> Dict[str, str]:
    """
    Lit voix.json et renvoie un mapping { "Nom" : "ID_Reference_Fish_Audio" }
    """
    if not VOIX_JSON_PATH.exists():
        raise TTSError(f"Le fichier {VOIX_JSON_PATH} est introuvable.")
    
    try:
        with open(VOIX_JSON_PATH, "r", encoding="utf-8") as f:
            voix_data = json.load(f)
            
        mapping = {}
        for voice in voix_data:
            nom = voice.get("nom", "").strip()
            v_id = voice.get("id", "").strip()
            if nom and v_id:
                mapping[nom] = v_id
        return mapping
    except Exception as e:
        raise TTSError(f"Erreur lors de la lecture de voix.json: {e}")


def parse_dialogue_script(script_text: str, available_names: list) -> List[Tuple[str, str]]:
    """
    Transforme le script en liste de tuples (speaker_name, text).
    Exemple de ligne : "Paul: Bonjour..."
    """
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

        speaker = match.group(1).strip()
        text = match.group(2).strip()

        if not text:
            continue

        # Optionnel: on peut forcer la correspondance exacte avec les noms dispos
        # Si vous trouvez "Host" au lieu de "Paul", vous pourriez le rediriger ici.
        if speaker in available_names:
            dialogue.append((speaker, text))
        else:
            # S'il y a des noms par défaut (Host/Expert) et qu'on ne les trouve pas
            print(f"Avertissement : Nom de voix non reconnu dans voix.json '{speaker}'. Ligne ignoree.")

    if not dialogue:
        raise TTSError(
            "Aucune ligne valide trouvée. "
            f"Les noms attendus dans le script sont : {', '.join(available_names)}."
        )

    return dialogue


def merge_consecutive_lines(
    dialogue: List[Tuple[str, str]],
    max_chars_per_block: int = 400
) -> List[Tuple[str, str]]:
    """
    Fusionne les répliques consécutives du même locuteur.
    """
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


def prepare_text_for_tts(text: str) -> str:
    """ Nettoyage et formatage du texte pour optimiser le TTS """
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\(.*?\)", "", text) # Supprime les didascalies entre parenthèses
    text = re.sub(r"[\"“”]", "", text)
    text = re.sub(r"([!?]){2,}", r"\1", text)
    return text


def synthesize_line_fish_audio(
    text: str,
    speaker_id: str,
    output_file: str
) -> None:
    """
    Lance une requête API vers Fish Audio pour générer l'audio.
    """
    if FISH_AUDIO_API_KEY == "VOTRE_CLE_ICI":
        raise TTSError("⚠️ Veuillez définir votre FISH_AUDIO_API_KEY dans le fichier TTS_FISH_AUDIO.py !")
        
    payload = {
        "text": text,
        "reference_id": speaker_id,
        "format": "mp3"
    }
    
    headers = {
        "Authorization": f"Bearer {FISH_AUDIO_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(FISH_AUDIO_API_URL, json=payload, headers=headers)
        
        if response.status_code == 200:
            with open(output_file, "wb") as f:
                f.write(response.content)
        else:
            try:
                error_detail = response.json()
            except:
                error_detail = response.text
            raise TTSError(f"Code {response.status_code} - {error_detail}")
            
    except requests.exceptions.RequestException as e:
        raise TTSError(f"Impossible de contacter l'API Fish Audio : {e}")


def create_silence_mp3(output_file: str, duration_ms: int = 220) -> str:
    """ Crée un silence MP3 d'une certaine durée en utilisant FFmpeg. """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=mono:sample_rate=44100",
        "-t", str(duration_ms / 1000),
        "-ar", "44100",
        "-ac", "1",
        "-c:a", "libmp3lame",
        "-b:a", "128k",
        str(output_path),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
    except subprocess.CalledProcessError as e:
        error_msg = (e.stderr or e.stdout or str(e)).strip()
        raise TTSError(f"Erreur création silence FFmpeg : {error_msg}")

    return str(output_path)


def combine_audio_files_with_ffmpeg(audio_files: List[str], output_file: str) -> str:
    """
    Concatène plusieurs fichiers MP3 en un seul MP3 final avec FFmpeg concat demuxer.
    """
    if not audio_files:
        raise TTSError("Aucun fichier audio à concaténer.")

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    list_file = output_path.parent / "tts_fish_concat_list.txt"

    with open(list_file, "w", encoding="utf-8") as f:
        for audio in audio_files:
            f.write(f"file '{Path(audio).resolve()}'\n")

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output_path),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
    except subprocess.CalledProcessError as e:
        error_msg = (e.stderr or e.stdout or str(e)).strip()
        raise TTSError(f"Erreur ffmpeg concat : {error_msg}")

    return str(output_path)


def get_pause_duration_ms(current_speaker: str, next_speaker: str | None) -> int:
    if next_speaker is None:
        return 0
    if current_speaker != next_speaker:
        return 280
    return 180


def script_to_speech(
    script_text: str,
    podcast_language: str = "Français",
    output_file: str = "speech.mp3",
    temp_dir: str = "outputs/tts_fish_tmp",
) -> str:
    """
    Fonction principale de génération TTS.
    """
    # 1. Charger les ID Fish Audio depuis voix.json
    voices_map = load_voices_map()
    available_names = list(voices_map.keys())

    # 2. Parser le script
    dialogue = parse_dialogue_script(script_text, available_names)
    dialogue = merge_consecutive_lines(dialogue, max_chars_per_block=260)
    print(f"[Fish TTS] Nombre de blocs à générer via API : {len(dialogue)}")

    tmp_path = Path(temp_dir)
    tmp_path.mkdir(parents=True, exist_ok=True)
    generated_files: List[str] = []

    # 3. Appeler l'API ligne par ligne
    for i, (speaker, text) in enumerate(dialogue, start=1):
        speaker_id = voices_map[speaker]
        prepared_text = prepare_text_for_tts(text)

        raw_output = tmp_path / f"line_{i:03d}_raw.mp3"

        print(f"[Fish TTS {i}/{len(dialogue)}] {speaker} | Envoi de {len(prepared_text)} caracteres...")

        synthesize_line_fish_audio(
            text=prepared_text,
            speaker_id=speaker_id,
            output_file=str(raw_output),
        )

        generated_files.append(str(raw_output))

        # Ajouter le silence entre les répliques
        next_speaker = dialogue[i][0] if i < len(dialogue) else None
        pause_ms = get_pause_duration_ms(speaker, next_speaker)

        if pause_ms > 0:
            silence_file = tmp_path / f"pause_{i:03d}.mp3"
            create_silence_mp3(str(silence_file), duration_ms=pause_ms)
            generated_files.append(str(silence_file))

    # 4. Concaténer tout l'audio
    final_audio_path = combine_audio_files_with_ffmpeg(
        audio_files=generated_files,
        output_file=output_file
    )

    print(f"\nAudio final Fish Audio genere : {final_audio_path}")
    return final_audio_path


if __name__ == "__main__":
    # Test simple du module
    sample_script = "Paul: Salut tout le monde.\nEva: Bienvenue dans ce super podcast."
    try:
        audio_path = script_to_speech(
            script_text=sample_script,
            podcast_language="Français",
            output_file="speech.mp3",
            temp_dir="outputs/test_fish_tmp"
        )
    except TTSError as e:
        print(f"Erreur Terminale : {e}")
