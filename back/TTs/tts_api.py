# Version5/back/TTs/tts_api.py
from pathlib import Path
from typing import List, Dict
import uuid
 
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
 
from back.TTs.TTS_FISH_AUDIO import script_to_speech as fish_tts, TTSError as FishTTSError
 
try:
    from back.TTs.tts import script_to_speech as coqui_tts, TTSError as CoquiTTSError
    COQUI_AVAILABLE = True
except ImportError:
    COQUI_AVAILABLE = False
    CoquiTTSError = Exception
 
app = FastAPI(title="Podcast Generator TTS Service")
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
 
BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs" / "tts_final"
TMP_DIR = BASE_DIR / "outputs" / "tts_tmp"
 
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)
 
 
class GenerateAudioRequest(BaseModel):
    script_text: str
    podcast_language: str = "Français"
    tts_engine: str = "fish"
    participants: List[str] = []
    voices_wav: Dict[str, str] = {}  # {"Voix_01": "fr_male_01.wav", ...}
 
 
@app.get("/health")
def health():
    return {"status": "ok", "coqui_available": COQUI_AVAILABLE}
 
 
@app.post("/generate-audio")
def generate_audio(payload: GenerateAudioRequest):
    try:
        filename = f"podcast_{uuid.uuid4().hex}.mp3"
        output_path = OUTPUTS_DIR / filename
        script = payload.script_text
 
        print("PARTICIPANTS REÇUS:", payload.participants)
        print("VOICES WAV:", payload.voices_wav)
        print("SCRIPT DÉBUT:", script[:200])
 
        if payload.tts_engine == "coqui":
            if not COQUI_AVAILABLE:
                raise HTTPException(
                    status_code=400,
                    detail="Coqui TTS non disponible (Python 3.14 incompatible)."
                )
            # Remplace Marc:, Eva:, etc. → Voix_01:, Voix_02:...
            for i, name in enumerate(payload.participants, start=1):
                script = script.replace(f"{name}:", f"Voix_0{i}:")
 
            final_audio = coqui_tts(
                script_text=script,
                podcast_language=payload.podcast_language,
                output_file=str(output_path),
                temp_dir=str(TMP_DIR),
                voices_override=payload.voices_wav if payload.voices_wav else None,
            )
        else:
            final_audio = fish_tts(
                script_text=script,
                podcast_language=payload.podcast_language,
                output_file=str(output_path),
                temp_dir=str(TMP_DIR),
            )
 
        return {
            "success": True,
            "filename": Path(final_audio).name,
            "audio_url": f"http://127.0.0.1:8001/audio/{Path(final_audio).name}",
        }
 
    except HTTPException:
        raise
    except (FishTTSError, CoquiTTSError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS internal error: {e}")
 
 
@app.get("/audio/{filename}")
def get_audio(filename: str):
    file_path = OUTPUTS_DIR / filename
 
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
 
    return FileResponse(
        path=file_path,
        media_type="audio/mpeg",
        filename=filename,
    )
