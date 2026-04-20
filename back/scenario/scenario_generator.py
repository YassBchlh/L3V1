# Version5/back/scenario/scenario_generator.py
import json
import os
import re
import requests
from typing import List, Dict, Any, Tuple


DEFAULT_API_URL = os.environ.get("OLLAMA_API_URL", "http://127.0.0.1:11434/api/generate")
DEFAULT_MODEL = "gemma3:4b"


class ScenarioError(Exception):
    pass


def get_duration_settings(podcast_duration: str) -> Dict[str, int]:
    duration = (podcast_duration or "").strip().lower()

    if duration in ["court", "court (1-3 min)", "1-3 min"]:
        return {
            "max_chars": 6000,
            "num_predict": 2500,
            "timeout": 180,
            "max_segments": 6,
            "min_lines": 15,
            "max_lines": 35,
            "max_continuations": 2,
        }

    if duration in ["moyen", "moyen (3-5 min)", "3-5 min"]:
        return {
            "max_chars": 9000,
            "num_predict": 3500,
            "timeout": 240,
            "max_segments": 10,
            "min_lines": 25,
            "max_lines": 55,
            "max_continuations": 3,
        }

    if duration in ["long", "long (5-10 min)", "5-10 min"]:
        return {
            "max_chars": 13000,
            "num_predict": 5000,
            "timeout": 400,
            "max_segments": 14,
            "min_lines": 45,
            "max_lines": 100,
            "max_continuations": 3,
        }

    return {
        "max_chars": 9000,
        "num_predict": 3500,
        "timeout": 240,
        "max_segments": 10,
        "min_lines": 25,
        "max_lines": 55,
        "max_continuations": 3,
    }

def normalize_participants(participants: List[str]) -> List[str]:
    cleaned = [p.strip() for p in participants if isinstance(p, str) and p.strip()]
    if len(cleaned) < 2:
        return ["Voix_01", "Voix_02"]
    return cleaned


def extract_topic_list(segments: List[Dict[str, Any]]) -> List[str]:
    topics = []
    seen = set()

    for seg in segments:
        title = (seg.get("title") or "").strip()
        text = (seg.get("text") or "").strip()

        if title:
            topic = title
        else:
            first_sentence = re.split(r"(?<=[.!?])\s+", text)[0].strip() if text else ""
            topic = first_sentence[:120].strip()

        if topic and topic not in seen:
            seen.add(topic)
            topics.append(topic)

    return topics


def build_topics_summary(topics: List[str]) -> str:
    if not topics:
        return "Aucun sujet détecté."

    return "\n".join(f"{i+1}. {topic}" for i, topic in enumerate(topics))


def build_context_from_segments(
    segments: List[Dict[str, Any]],
    max_chars: int = 10000,
    max_segments: int = 12,
) -> str:
    if not segments:
        raise ScenarioError("Aucun segment fourni.")

    parts = []
    total_chars = 0
    kept = 0

    for idx, seg in enumerate(segments, start=1):
        if kept >= max_segments:
            break

        text = (seg.get("text") or "").strip()
        if not text:
            continue

        title = (seg.get("title") or "Sans titre").strip()
        source_type = (seg.get("source_type") or seg.get("type") or "unknown").strip()

        block = (
            f"[SEGMENT {idx} | TITRE: {title} | TYPE: {source_type}]\n"
            f"{text}\n"
        )

        if total_chars + len(block) > max_chars:
            break

        parts.append(block)
        total_chars += len(block)
        kept += 1

    if not parts:
        raise ScenarioError("Aucun texte exploitable dans les segments.")

    return "\n\n".join(parts)


def call_llm_with_curl(
    prompt: str,
    model: str = DEFAULT_MODEL,
    api_url: str = DEFAULT_API_URL,
    timeout: int = 240,
    num_predict: int = 2200,
) -> Tuple[str, Dict[str, Any]]:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": num_predict,
            "temperature": 0.3,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
        },
    }

    try:
        response = requests.post(
            api_url,
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.Timeout:
        raise ScenarioError("Le serveur Ollama a mis trop de temps à répondre.")
    except requests.RequestException as e:
        raise ScenarioError(f"Erreur lors de l'appel API : {str(e)}")

    raw_output = response.text.strip()
    if not raw_output:
        raise ScenarioError("Réponse vide de l'API.")

    try:
        data = json.loads(raw_output)
    except json.JSONDecodeError:
        raise ScenarioError(f"Réponse JSON invalide : {raw_output}")

    response_text = (data.get("response") or "").strip()
    if not response_text:
        raise ScenarioError(f"Aucune réponse générée. Réponse brute : {raw_output}")

    meta = {
        "done": data.get("done"),
        "done_reason": data.get("done_reason"),
        "eval_count": data.get("eval_count"),
        "prompt_eval_count": data.get("prompt_eval_count"),
    }

    return response_text, meta


def build_prompt(
    context: str,
    podcast_duration: str,
    participants: List[str],
    podcast_language: str = "Français",
    topics: List[str] = None,
) -> str:
    settings = get_duration_settings(podcast_duration)
    topics_summary = build_topics_summary(topics or [])
    max_lines = settings["max_lines"]

    lang = (podcast_language or "").lower()

    if lang in ["english", "en", "anglais"]:
        lang_name = "English"
        lang_rules = """
- The ENTIRE dialogue MUST be in English
- NEVER switch language
- Use natural spoken English
- Use contractions: it's, we're, that's, you know
- Casual podcast tone
"""
    else:
        lang_name = "Français"
        lang_rules = """
- Le dialogue doit être entièrement en français
- Ne jamais changer de langue
- Style oral naturel
- Utiliser des contractions: c'est, on va, tu vois
"""
    speaker_list_inline = ", ".join(participants)
    
    return f"""
You are a professional podcast scriptwriter.

LANGUAGE: {lang_name}

STRICT LANGUAGE RULES:
{lang_rules}

═══════════════════════════════════════
FORMAT (MANDATORY)
═══════════════════════════════════════
- Each line starts EXACTLY with ONE of these speakers: {speaker_list_inline}
- Each speaker name must be followed by a colon (:)
- Dialogue ONLY
- No narration
- No title
- No markdown
- Start immediately

═══════════════════════════════════════
ANTI-HALLUCINATION (CRITICAL)
═══════════════════════════════════════
YOU MUST ONLY USE THE SOURCE.

- Every fact MUST exist in the source
- If not in source → DO NOT SAY IT
- No guessing
- No completion
- No external knowledge

If unsure → SKIP the information

Goal: ZERO hallucination

═══════════════════════════════════════
STYLE (VERY IMPORTANT)
═══════════════════════════════════════
- Natural conversation
- Short sentences (max ~15 words)
- Fast rhythm
- No long monologues

Use:
- interruptions
- reactions
- curiosity
- smooth transitions between completely different topics

Rule:
→ ONE idea per exchange

═══════════════════════════════════════
STRUCTURE & TOPIC COVERAGE (CRITICAL)
═══════════════════════════════════════
1. Quick intro (2 lines max)
2. Hook
3. Main discussion: YOU MUST DISCUSS EVERY SINGLE TOPIC LISTED IN THE "TOPICS" SECTION BELOW. Do not skip any. Transition naturally from one piece of news to the next.
4. Outro (2 lines max)

═══════════════════════════════════════
LENGTH CONSTRAINT
═══════════════════════════════════════
- Target length: around {max_lines} lines.
- HOWEVER: Do not sacrifice content. It is more important to cover ALL topics from the source than to strictly obey the line limit. Do not write the outro until all topics are covered.

═══════════════════════════════════════
TOPICS YOU MUST COVER:
═══════════════════════════════════════
{topics_summary}

═══════════════════════════════════════
SOURCE
═══════════════════════════════════════
{context}

Start immediately.
""".strip()

def canonicalize_speaker(label: str, participants: List[str]) -> str:
    cleaned_participants = normalize_participants(participants)
    raw = label.strip().lower()
    raw = raw.replace("_", " ")
    raw = re.sub(r"\s+", " ", raw)

    # First, check direct matches with actual participant names
    for p in cleaned_participants:
        if raw == p.lower().replace("_", " "):
            return p

    # Fallback fuzzy mapping (e.g. "speaker 1", "voix 2", "intervenant 3")
    match = re.search(r'\d+', raw)
    if match:
        num = int(match.group())
        if 1 <= num <= len(cleaned_participants):
            return cleaned_participants[num - 1]

    return ""

def normalize_script(script: str, participants: List[str]) -> str:
    cleaned_participants = normalize_participants(participants)
    valid_lines = []

    for line in script.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        stripped = stripped.replace("**", "").replace("__", "").strip()
        stripped = re.sub(r"^[\-\*\•\d\.\)\s]+", "", stripped)
        stripped = re.sub(r"\[\d+\]", "", stripped).strip()

        match = re.match(r"^([^:>\-–—]+?)\s*[:>\-–—]\s*(.+)$", stripped)
        if not match:
            continue

        raw_label = match.group(1).strip()
        content = match.group(2).strip()
        speaker = canonicalize_speaker(raw_label, cleaned_participants)

        if speaker and content:
            valid_lines.append(f"{speaker}: {content}")

    if not valid_lines:
        raise ScenarioError(
            f"Le script généré ne contient aucune ligne valide. Participants attendus : {', '.join(cleaned_participants)}."
        )

    return "\n".join(valid_lines)


def count_dialogue_lines(script: str, participants: List[str]) -> int:
    cleaned_participants = normalize_participants(participants)
    count = 0
    for line in script.splitlines():
        stripped = line.strip()
        # Check if the line starts with ANY of the participants
        if any(stripped.startswith(f"{p}:") for p in cleaned_participants):
            count += 1
    return count


def looks_truncated(script: str) -> bool:
    stripped = (script or "").strip()
    if not stripped:
        return True

    suspicious_endings = (
        "et", "mais", "ou", "donc", "car", "avec", "de", "des", "du",
        "la", "le", "les", "un", "une", "pour", "sur", "dans", "à",
        ",", ";", ":", "-"
    )

    lower = stripped.lower()

    if lower.endswith(suspicious_endings):
        return True

    if not stripped.endswith((".", "!", "?", "…", '"', "”")):
        return True

    last_line = stripped.splitlines()[-1].strip()
    if re.match(r"^[^:]+:\s*$", last_line):
        return True
    last_line = stripped.splitlines()[-1].strip()

    if len(last_line.split()) <= 4 and not last_line.endswith((".", "!", "?", "…", '"', "”")):
        return True
    return False


def count_covered_topics(script: str, topics: List[str]) -> int:
    if not script or not topics:
        return 0

    script_lower = script.lower()
    covered = 0

    for topic in topics:
        topic_lower = topic.lower()

        words = [
            w.strip()
            for w in re.split(r"[^a-zA-Z0-9À-ÿ]+", topic_lower)
            if len(w.strip()) >= 4
        ]

        strong_words = words[:4]

        if strong_words and any(word in script_lower for word in strong_words):
            covered += 1

    return covered


def repair_script_with_llm(
    raw_script: str,
    participants: List[str],
    podcast_duration: str,
    model: str = DEFAULT_MODEL,
    api_url: str = DEFAULT_API_URL,
) -> str:
    cleaned_participants = normalize_participants(participants)
    settings = get_duration_settings(podcast_duration)
    
    part_list_bullet = "\n".join([f"- {p}" for p in cleaned_participants])

    repair_prompt = f"""
Tu dois corriger et reformater un script de podcast.

Intervenants autorisés uniquement :
{part_list_bullet}

FORMAT OBLIGATOIRE :
- Chaque ligne commence exactement par l'un des intervenants suivi de ":" (ex: {cleaned_participants[0]}:)
- Aucun autre nom
- Aucun titre
- Aucun markdown
- Aucun texte hors dialogue

RÈGLES :
- Conserve uniquement les informations déjà présentes
- N’ajoute aucun fait nouveau
- Nettoie seulement le format
- Garde un style naturel et pédagogique

Texte à corriger :
{raw_script}
""".strip()

    repaired, _ = call_llm_with_curl(
        prompt=repair_prompt,
        model=model,
        api_url=api_url,
        timeout=settings["timeout"],
        num_predict=settings["num_predict"] + 300,
    )

    return normalize_script(repaired, cleaned_participants)

def continue_script_with_llm(
    partial_script: str,
    context: str,
    participants: List[str],
    podcast_duration: str,
    podcast_language: str = "Français",
    topics: List[str] = None,
    model: str = DEFAULT_MODEL,
    api_url: str = DEFAULT_API_URL,
) -> str:
    cleaned_participants = normalize_participants(participants)
    settings = get_duration_settings(podcast_duration)
    topics_summary = build_topics_summary(topics or [])
    
    part_list_inline = ", ".join(cleaned_participants)

    continuation_prompt = f"""
Tu dois CONTINUER un script de podcast éducatif en {podcast_language}.

IMPORTANT :
- Ne recommence pas depuis le début.
- Continue exactement là où le dialogue s'est arrêté.
- Utilise uniquement : {part_list_inline}.
- Chaque ligne commence exactement par le nom de l'intervenant suivi de ":"
- Aucun titre
- Aucun markdown
- Aucun texte hors dialogue
- Utilise uniquement les informations du contenu source
- N’invente aucun fait
- Le script actuel est incomplet
- Tu dois terminer tous les sujets importants restants
- Tu ne dois conclure qu’après avoir traité tous les sujets
- Ne coupe pas le script au milieu d’un sujet

SUJETS IMPORTANTS À COUVRIR :
{topics_summary}

CONTENU SOURCE :
{context}

SCRIPT DÉJÀ GÉNÉRÉ :
{partial_script}

CONTINUE DIRECTEMENT LE DIALOGUE À PARTIR DU DERNIER POINT NON TERMINÉ.
""".strip()

    continuation, _ = call_llm_with_curl(
        prompt=continuation_prompt,
        model=model,
        api_url=api_url,
        timeout=settings["timeout"],
        num_predict=max(900, settings["num_predict"] // 2),
    )

    normalized_continuation = normalize_script(continuation, cleaned_participants)

    merged = partial_script.strip() + "\n" + normalized_continuation.strip()
    return merged.strip()


def generate_dialogue_from_segments(
    segments: List[Dict[str, Any]],
    podcast_duration: str,
    participants: List[str],
    podcast_language: str = "Français",
    model: str = DEFAULT_MODEL,
    api_url: str = DEFAULT_API_URL,
) -> str:
    cleaned_participants = normalize_participants(participants)
    settings = get_duration_settings(podcast_duration)

    context = build_context_from_segments(
        segments,
        max_chars=settings["max_chars"],
        max_segments=settings["max_segments"],
    )

    topics = extract_topic_list(segments)

    print("\n===== TOPICS =====")
    for t in topics:
        print("-", t)
    print("===== END TOPICS =====\n")

    print("\n===== CONTEXT SENT TO LLM =====\n")
    print(context[:3000] + ("\n...[TRUNCATED FOR LOG]..." if len(context) > 3000 else ""))
    print("\n===== END CONTEXT =====\n")

    prompt = build_prompt(
        context=context,
        podcast_duration=podcast_duration,
        participants=cleaned_participants,
        podcast_language=podcast_language,
        topics=topics,
    )

    raw_script, meta = call_llm_with_curl(
        prompt=prompt,
        model=model,
        api_url=api_url,
        timeout=settings["timeout"],
        num_predict=settings["num_predict"],
    )

    print("\n===== GENERATION META =====\n")
    print(meta)
    print("\n===== END GENERATION META =====\n")

    try:
        script = normalize_script(raw_script, cleaned_participants)
    except ScenarioError:
        script = repair_script_with_llm(
            raw_script=raw_script,
            participants=cleaned_participants,
            podcast_duration=podcast_duration,
            model=model,
            api_url=api_url,
        )

    max_continuations = settings.get("max_continuations", 2)

    for i in range(max_continuations):
        line_count = count_dialogue_lines(script, cleaned_participants)
        covered_topics = count_covered_topics(script, topics)
        total_topics = len(topics)

        print(
            f"[CHECK] continuation={i} | lines={line_count} | covered_topics={covered_topics}/{total_topics}"
        )

        enough_topics = covered_topics >= total_topics

        needs_continuation = (
            meta.get("done_reason") == "length"
            or looks_truncated(script)
            or line_count < settings["min_lines"]
            or not enough_topics
        )

        if not needs_continuation:
            break

        try:
            script = continue_script_with_llm(
                partial_script=script,
                context=context,
                participants=cleaned_participants,
                podcast_duration=podcast_duration,
                podcast_language=podcast_language,
                topics=topics,
                model=model,
                api_url=api_url,
            )
            script = normalize_script(script, cleaned_participants)
        except Exception as e:
            print(f"[WARN] Continuation impossible : {e}")
            break
    # HARD LIMIT de sécurité absolue (pour éviter les boucles infinies, mais on laisse le LLM respirer)
    lines = script.splitlines()
    if len(lines) > 200:
        script = "\n".join(lines[:200])
        
    return script.strip()


def save_script(script: str, filename: str = "podcast_script.txt") -> None:
    with open(filename, "w", encoding="utf-8") as f:
        f.write(script)