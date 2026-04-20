# Version5/back/api.py
import sys
import os
from pathlib import Path
 
sys.path.append(str(Path(__file__).resolve().parent.parent))
 
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
 
import subprocess
import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
 
from back.segmentation.pipeline_segmentation import run_full_pipeline
from back.scenario.scenario_generator import generate_dialogue_from_segments
from fastapi.responses import FileResponse
import subprocess as _subprocess
 
 
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR = BASE_DIR / "temp_uploads"
INTROS_DIR = BASE_DIR / "intros"
VOIX_JSON = BASE_DIR / "voix.json"
TTS_API_URL = "http://127.0.0.1:8001"
 
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
INTROS_DIR.mkdir(parents=True, exist_ok=True)
 
app = FastAPI(title="Podcast Generator API")
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
 
 
class GenerateAudioRequest(BaseModel):
    script: str
    podcast_language: str = "Français"
    participants: List[str] = []
    title: Optional[str] = "Podcast généré"
    intro_file: Optional[str] = None
    outro_file: Optional[str] = None
    tts_engine: str = "fish"
 
 
def build_voices_wav(participants: List[str]) -> Dict[str, str]:
    """
    Construit le mapping Voix_01 → fr_male_01.wav
    en lisant voix.json et en matchant les noms des participants.
    """
    try:
        voix_data = json.loads(VOIX_JSON.read_text(encoding="utf-8"))
        
        wav_map = {v["nom"]: v.get("wav", "") for v in voix_data}
        result = {}
        for i, name in enumerate(participants, start=1):
            wav = wav_map.get(name, "")
            if wav:
                result[f"Voix_0{i}"] = wav
        return result
    except Exception as e:
        print(f"Erreur build_voices_wav: {e}")
        return {}
 
 
def merge_with_intro_outro(
    audio_path: str,
    intro_path: Optional[str],
    outro_path: Optional[str],
) -> str:
    files_to_concat = []
    if intro_path and Path(intro_path).exists():
        files_to_concat.append(intro_path)
    files_to_concat.append(audio_path)
    if outro_path and Path(outro_path).exists():
        files_to_concat.append(outro_path)
 
    if len(files_to_concat) == 1:
        return audio_path
 
    p = Path(audio_path)
    merged_path = str(p.parent / f"merged_{p.name}")
    list_file = p.parent / "concat_intro_outro.txt"
 
    with open(list_file, "w", encoding="utf-8") as f:
        for fp in files_to_concat:
            f.write(f"file '{Path(fp).resolve()}'\n")
 
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-ar", "44100",
        "-ac", "1",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        merged_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        Path(audio_path).unlink(missing_ok=True)
        Path(merged_path).rename(audio_path)
    except subprocess.CalledProcessError as e:
        print(f"Erreur ffmpeg fusion intro/outro : {e.stderr}")
 
    return audio_path
 
 
def sanitize_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in ("-", "_", ".", " ")).strip()
 
 
def list_archives():
    archives = []
 
    for meta_file in sorted(OUTPUT_DIR.glob("run_metadata_*.json"), reverse=True):
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
 
            if not data.get("audio_path"):
                continue
 
            script_path = data.get("script_path", "")
            title = data.get("title") or (Path(script_path).stem.replace("_", " ") if script_path else "Podcast")
 
            archives.append(
                {
                    "id": data.get("id", meta_file.stem.replace("run_metadata_", "")),
                    "title": title,
                    "date": data.get("generated_at", ""),
                    "script_path": script_path,
                    "audio_path": data.get("audio_path", ""),
                    "audio_url": data.get("audio_url", ""),
                }
            )
        except Exception:
            continue
 
    return archives
 
 
def request_tts_audio(
    script: str,
    podcast_language: str,
    tts_engine: str = "fish",
    participants: list = None,
) -> dict:
    voices_wav = {}
    if tts_engine == "coqui" and participants:
        voices_wav = build_voices_wav(participants)
        print(f"BUILD VOICES WAV RESULT: {voices_wav}")
        print(f"VOIX_JSON exists: {VOIX_JSON.exists()}")

    response = requests.post(
        f"{TTS_API_URL}/generate-audio",
        json={
            "script_text": script,
            "podcast_language": podcast_language,
            "tts_engine": tts_engine,
            "participants": participants or [],
            "voices_wav": voices_wav,
        },
        timeout=1800,
    )
    response.raise_for_status()
    return response.json()
 
 
@app.get("/archives")
def get_archives():
    return {"archives": list_archives()}
 
 
@app.get("/api/intros")
def get_intros():
    if not INTROS_DIR.exists():
        return {"intros": []}
    files = [f.name for f in INTROS_DIR.glob("*") if f.suffix.lower() in [".mp3", ".wav"]]
    return {"intros": files}
 
 
@app.get("/health")
def health():
    return {"status": "ok"}
 
 
@app.post("/generate-script")
async def generate_script(
    files: List[UploadFile] = File(default=[]),
    links: str = Form(default="[]"),
    podcast_language: str = Form(default="Français"),
    podcast_duration: str = Form(default="Court (1-3 min)"),
    participants: str = Form(default="[]"),
):
    try:
        parsed_links = json.loads(links) if links else []
        parsed_participants = json.loads(participants) if participants else []
        print("LANG RECEIVED:", podcast_language)
        saved_paths: List[str] = []
 
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        request_upload_dir = UPLOAD_DIR / f"request_{timestamp}"
        request_upload_dir.mkdir(parents=True, exist_ok=True)
 
        for upload in files:
            safe_name = sanitize_filename(upload.filename or "uploaded_file")
            target_path = request_upload_dir / safe_name
 
            with open(target_path, "wb") as buffer:
                shutil.copyfileobj(upload.file, buffer)
 
            saved_paths.append(str(target_path))
 
        resources = saved_paths + parsed_links
 
        if not resources:
            raise HTTPException(status_code=400, detail="Aucune ressource reçue.")
 
        if not parsed_participants:
            parsed_participants = ["Voix_01", "Voix_02"]
 
        segments = run_full_pipeline(resources)
 
        if not segments:
            raise HTTPException(status_code=400, detail="Aucun segment généré.")
 
        script = generate_dialogue_from_segments(
            segments=segments,
            podcast_duration=podcast_duration,
            participants=parsed_participants,
            podcast_language=podcast_language,
        )
 
        if not script or not script.strip():
            raise HTTPException(status_code=500, detail="Le script généré est vide.")
 
        title = f"Podcast à partir de {len(resources)} ressource(s)"
        if files and not parsed_links:
            first_name = files[0].filename if files[0].filename else "Podcast généré"
            title = Path(first_name).stem
        elif files and parsed_links:
            title = f"Podcast multi-sources ({len(resources)})"
        elif parsed_links and len(parsed_links) == 1:
            title = "Podcast à partir de ressources"
 
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        script_output_path = OUTPUT_DIR / f"podcast_script_{timestamp}.txt"
        metadata_output_path = OUTPUT_DIR / f"run_metadata_{timestamp}.json"
 
        script_output_path.write_text(script, encoding="utf-8")
 
        metadata = {
            "id": timestamp,
            "generated_at": datetime.now().isoformat(),
            "title": title,
            "script_path": str(script_output_path),
            "audio_path": "",
            "audio_url": "",
        }
        metadata_output_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
 
        return {
            "id": timestamp,
            "title": title,
            "date": datetime.now().strftime("%d/%m/%Y"),
            "generated_at": datetime.now().isoformat(),
            "summary": f"Podcast généré à partir de {len(resources)} ressource(s).",
            "description": f"Langue : {podcast_language} | Durée : {podcast_duration}",
            "script": script,
            "segments_count": len(segments),
            "participants": parsed_participants,
        }
 
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.get("/api/download/{timestamp}")
def download_podcast(timestamp: str, format: str = "mp3"):
    meta_file = OUTPUT_DIR / f"run_metadata_{timestamp}.json"
    if not meta_file.exists():
        raise HTTPException(status_code=404, detail="Podcast non trouvé.")
 
    try:
        data = json.loads(meta_file.read_text(encoding="utf-8"))
        audio_path_str = data.get("audio_path", "")
        if not audio_path_str:
            raise HTTPException(status_code=404, detail="Chemin audio non trouvé dans les métadonnées.")
 
        source_path = Path(audio_path_str)
        if not source_path.exists():
            source_path = OUTPUT_DIR / source_path.name
            if not source_path.exists():
                raise HTTPException(status_code=404, detail="Fichier audio source introuvable.")
 
        req_format = format.lower()
        if req_format not in ["mp3", "wav"]:
            raise HTTPException(status_code=400, detail="Format non supporté. MP3 ou WAV uniquement.")
 
        if source_path.suffix.lower() == f".{req_format}":
            return FileResponse(path=str(source_path), filename=source_path.name)
 
        target_path = source_path.with_suffix(f".{req_format}")
 
        if not target_path.exists():
            try:
                _subprocess.run(
                    ["ffmpeg", "-y", "-i", str(source_path), str(target_path)],
                    check=True, capture_output=True
                )
            except _subprocess.CalledProcessError as e:
                raise HTTPException(status_code=500, detail=f"Echec de la conversion ffmpeg : {e.stderr.decode('utf-8', errors='replace')}")
 
        return FileResponse(path=str(target_path), filename=target_path.name)
 
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Erreur lors du téléchargement : {str(e)}")
 
 
@app.post("/generate-audio")
async def generate_audio(payload: GenerateAudioRequest):
    try:
        if not payload.script or not payload.script.strip():
            raise HTTPException(status_code=400, detail="Le script est vide.")
 
        result = request_tts_audio(
            script=payload.script,
            podcast_language=payload.podcast_language,
            tts_engine=payload.tts_engine,
            participants=payload.participants,
        )
 
        audio_url = result.get("audio_url", "")
        filename = result.get("filename", "")
 
        audio_path = ""
        if filename:
            audio_path = str(OUTPUT_DIR / "tts_final" / filename)
 
            if payload.intro_file or payload.outro_file:
                audio_path = merge_with_intro_outro(
                    audio_path=audio_path,
                    intro_path=str(INTROS_DIR / payload.intro_file) if payload.intro_file else None,
                    outro_path=str(INTROS_DIR / payload.outro_file) if payload.outro_file else None,
                )
 
        meta_id = None
        latest_meta = sorted(OUTPUT_DIR.glob("run_metadata_*.json"), reverse=True)
        if latest_meta:
            try:
                data = json.loads(latest_meta[0].read_text(encoding="utf-8"))
                data["audio_path"] = audio_path
                data["audio_url"] = audio_url
                latest_meta[0].write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                meta_id = latest_meta[0].stem.replace("run_metadata_", "")
            except Exception:
                pass
 
        return {
            "id": meta_id or datetime.now().strftime("%Y%m%d_%H%M%S"),
            "audio_path": audio_path,
            "audio_url": audio_url,
            "filename": filename,
        }
 
    except requests.HTTPError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text if e.response is not None else str(e)
        raise HTTPException(status_code=500, detail=f"TTS service error: {detail}")
 
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
app.mount("/audio", StaticFiles(directory=str(OUTPUT_DIR)), name="audio")
app.mount("/intros", StaticFiles(directory=str(INTROS_DIR)), name="intros")