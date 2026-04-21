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


GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def call_llm_gemini(
    prompt: str,
    api_key: str,
    timeout: int = 300,
    num_predict: int = 5000,
) -> Tuple[str, Dict[str, Any]]:
    url = f"{GEMINI_API_BASE}/{GEMINI_MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "topP": 0.9,
            "maxOutputTokens": num_predict,
        },
    }
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
    except requests.Timeout:
        raise ScenarioError("Gemini API : timeout dépassé.")
    except requests.RequestException as e:
        raise ScenarioError(f"Gemini API : erreur réseau : {str(e)}")

    data = response.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        raise ScenarioError(f"Réponse Gemini invalide : {data}")

    finish_reason = (data.get("candidates", [{}])[0].get("finishReason") or "").upper()
    meta = {
        "done": True,
        "done_reason": "length" if finish_reason == "MAX_TOKENS" else finish_reason.lower(),
    }
    return text, meta


def call_llm(
    prompt: str,
    llm_engine: str = "local",
    gemini_api_key: str = "",
    model: str = DEFAULT_MODEL,
    api_url: str = DEFAULT_API_URL,
    timeout: int = 240,
    num_predict: int = 2200,
) -> Tuple[str, Dict[str, Any]]:
    if llm_engine == "gemini" and gemini_api_key:
        # Gemini tokens ≠ Ollama tokens — multiply to avoid premature cutoff
        gemini_tokens = min(num_predict * 2, 8192)
        return call_llm_gemini(prompt, gemini_api_key, timeout=timeout, num_predict=gemini_tokens)
    return call_llm_with_curl(prompt, model=model, api_url=api_url, timeout=timeout, num_predict=num_predict)


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


STYLE_INSTRUCTIONS = {
    "serieux": {
        "label": "Sérieux",
        "en": """
TONE & STYLE: SERIOUS / EDUCATIONAL
- Academic, structured tone
- Clear and precise explanations
- No jokes or puns
- Use examples to clarify concepts
- Both speakers are equally knowledgeable
- Short sentences, factual and direct
""",
        "fr": """
TON & STYLE : SÉRIEUX / PÉDAGOGIQUE
- Ton académique et structuré
- Explications claires et précises
- Pas de blagues ni jeux de mots
- Utiliser des exemples concrets pour illustrer
- Les deux intervenants ont un niveau équivalent
- Phrases courtes, factuelles et directes
""",
    },
    "humoristique": {
        "label": "Humoristique",
        "en": """
TONE & STYLE: HUMOROUS
- Light, fun, and entertaining tone
- Include jokes, puns, and witty remarks naturally
- Banter and playful teasing between speakers
- Use funny analogies and pop culture references if they fit
- Keep it entertaining while still covering the content
- Reactions like "No way!", "That's wild!", "Okay but..."
""",
        "fr": """
TON & STYLE : HUMORISTIQUE
- Ton léger, fun et divertissant
- Inclure des blagues, jeux de mots et remarques spirituelles
- Piques amicales et complicité entre les intervenants
- Utiliser des analogies drôles et des références pop culture si pertinent
- Rester divertissant tout en couvrant le contenu
- Réactions du type : "Non sérieusement ?!", "C'est dingue ça !", "Attends mais..."
""",
    },
    "vulgarisation": {
        "label": "Vulgarisation",
        "en": """
TONE & STYLE: POPULAR SCIENCE / ACCESSIBLE
- Simple language, accessible to everyone — no jargon
- One speaker explains, the other asks "naive" questions as a curious beginner
- Use lots of metaphors and everyday analogies
- Break down every technical concept into simple terms
- "Imagine it like..." / "It's basically like..." constructions
- Patient, friendly, and encouraging tone
""",
        "fr": """
TON & STYLE : VULGARISATION SCIENTIFIQUE
- Langage simple et accessible à tous — pas de jargon
- Un intervenant explique, l'autre pose des questions "naïves" en curieux débutant
- Beaucoup de métaphores et analogies du quotidien
- Décomposer chaque concept technique en termes simples
- Constructions du type "Imagine que c'est comme..." / "En gros c'est..."
- Ton patient, bienveillant et encourageant
""",
    },
    "debat": {
        "label": "Débat",
        "en": """
TONE & STYLE: DEBATE
- The two speakers have OPPOSING viewpoints on the topics
- One defends, the other challenges and questions
- Productive tension: disagreements are intellectually stimulating
- Use phrases like "I disagree because...", "That's one way to see it, but...", "Have you considered...?"
- Both sides present arguments backed by the source material
- End with a nuanced conclusion or agree to disagree
""",
        "fr": """
TON & STYLE : DÉBAT
- Les deux intervenants ont des POINTS DE VUE OPPOSÉS sur les sujets
- L'un défend, l'autre questionne et challenge
- Tension productive : les désaccords sont intellectuellement stimulants
- Utiliser des formules comme "Je ne suis pas d'accord parce que...", "C'est une façon de voir, mais...", "Tu as pensé à...?"
- Les deux côtés s'appuient sur les informations de la source
- Conclure avec une nuance ou accepter le désaccord
""",
    },
    "interview": {
        "label": "Interview",
        "en": """
TONE & STYLE: INTERVIEW
- One speaker is THE EXPERT (knows everything about the topic)
- The other speaker is THE HOST (asks open-ended questions, reacts with curiosity)
- Format: question → detailed answer → follow-up question
- The host never gives long answers — only short questions and reactions
- The expert gives detailed, informed responses
- The host uses phrases like "So what does that mean exactly?", "Can you give us an example?", "That's fascinating, and..."
""",
        "fr": """
TON & STYLE : INTERVIEW
- Un intervenant est L'EXPERT (sait tout sur le sujet)
- L'autre intervenant est L'ANIMATEUR (pose des questions ouvertes, réagit avec curiosité)
- Format : question → réponse détaillée → question de relance
- L'animateur ne donne jamais de longues réponses — uniquement des questions courtes et des réactions
- L'expert donne des réponses détaillées et informées
- L'animateur utilise des formules comme "Qu'est-ce que ça veut dire concrètement ?", "Tu peux nous donner un exemple ?", "C'est fascinant, et..."
""",
    },
}


def get_style_instructions(podcast_style: str, lang_key: str) -> str:
    style_key = (podcast_style or "serieux").lower().strip()
    style_key = style_key.replace("é", "e").replace("è", "e").replace("ê", "e")
    style = STYLE_INSTRUCTIONS.get(style_key, STYLE_INSTRUCTIONS["serieux"])
    return style.get(lang_key, style["fr"])


def build_prompt(
    context: str,
    podcast_duration: str,
    participants: List[str],
    podcast_language: str = "Français",
    topics: List[str] = None,
    podcast_style: str = "Sérieux",
) -> str:
    settings = get_duration_settings(podcast_duration)
    topics_summary = build_topics_summary(topics or [])
    max_lines = settings["max_lines"]

    lang = (podcast_language or "").lower()

    if lang in ["english", "en", "anglais"]:
        lang_name = "English"
        lang_key = "en"
        lang_rules = """
- The ENTIRE dialogue MUST be in English
- NEVER switch language
- Use natural spoken English
- Use contractions: it's, we're, that's, you know
- Casual podcast tone
"""
    else:
        lang_name = "Français"
        lang_key = "fr"
        lang_rules = """
- Le dialogue doit être entièrement en français
- Ne jamais changer de langue
- Style oral naturel
- Utiliser des contractions: c'est, on va, tu vois
"""
    speaker_list_inline = ", ".join(participants)
    style_instructions = get_style_instructions(podcast_style, lang_key)

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
STYLE (VERY IMPORTANT — FOLLOW EXACTLY)
═══════════════════════════════════════
{style_instructions}
- Short sentences (max ~15 words)
- Fast rhythm
- No long monologues
- Smooth transitions between topics

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
    llm_engine: str = "local",
    gemini_api_key: str = "",
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
- Chaque ligne commence exactement par l’un des intervenants suivi de ":" (ex: {cleaned_participants[0]}:)
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

    repaired, _ = call_llm(
        prompt=repair_prompt,
        llm_engine=llm_engine,
        gemini_api_key=gemini_api_key,
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
    podcast_style: str = "Sérieux",
    topics: List[str] = None,
    llm_engine: str = "local",
    gemini_api_key: str = "",
    model: str = DEFAULT_MODEL,
    api_url: str = DEFAULT_API_URL,
) -> str:
    cleaned_participants = normalize_participants(participants)
    settings = get_duration_settings(podcast_duration)
    topics_summary = build_topics_summary(topics or [])
    
    part_list_inline = ", ".join(cleaned_participants)

    lang = (podcast_language or "").lower()
    lang_key = "en" if lang in ["english", "en", "anglais"] else "fr"
    style_instructions = get_style_instructions(podcast_style, lang_key)

    continuation_prompt = f"""
Tu dois CONTINUER un script de podcast en {podcast_language}.

STYLE À CONSERVER :
{style_instructions}

IMPORTANT :
- Ne recommence pas depuis le début.
- Continue exactement là où le dialogue s’est arrêté.
- Utilise uniquement : {part_list_inline}.
- Chaque ligne commence exactement par le nom de l’intervenant suivi de ":"
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

    continuation, _ = call_llm(
        prompt=continuation_prompt,
        llm_engine=llm_engine,
        gemini_api_key=gemini_api_key,
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
    podcast_style: str = "Sérieux",
    llm_engine: str = "local",
    gemini_api_key: str = "",
    model: str = DEFAULT_MODEL,
    api_url: str = DEFAULT_API_URL,
) -> Dict[str, str]:
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
        podcast_style=podcast_style,
    )

    raw_script, meta = call_llm(
        prompt=prompt,
        llm_engine=llm_engine,
        gemini_api_key=gemini_api_key,
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
            llm_engine=llm_engine,
            gemini_api_key=gemini_api_key,
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
                podcast_style=podcast_style,
                topics=topics,
                llm_engine=llm_engine,
                gemini_api_key=gemini_api_key,
                model=model,
                api_url=api_url,
            )
            script = normalize_script(script, cleaned_participants)
        except Exception as e:
            print(f"[WARN] Continuation impossible : {e}")
            break
    lines = script.splitlines()
    if len(lines) > 200:
        script = "\n".join(lines[:200])

    meta = generate_title_and_summary(
        script=script,
        topics=topics,
        podcast_language=podcast_language,
        llm_engine=llm_engine,
        gemini_api_key=gemini_api_key,
        model=model,
        api_url=api_url,
    )

    return {
        "script": script.strip(),
        "title": meta["title"],
        "summary": meta["summary"],
    }


def generate_title_and_summary(
    script: str,
    topics: List[str],
    podcast_language: str = "Français",
    llm_engine: str = "local",
    gemini_api_key: str = "",
    model: str = DEFAULT_MODEL,
    api_url: str = DEFAULT_API_URL,
) -> Dict[str, str]:
    lang = (podcast_language or "").lower()
    is_english = lang in ["english", "en", "anglais"]

    topics_line = ", ".join(topics[:5]) if topics else ""

    if is_english:
        prompt = f"""Based on this podcast script and its topics, generate a short title and a 1-2 sentence summary.

Topics covered: {topics_line}

Script (excerpt):
{script[:1200]}

Reply with EXACTLY this format, nothing else:
TITLE: <title under 8 words>
SUMMARY: <1-2 sentences about what the podcast covers>"""
    else:
        prompt = f"""À partir de ce script de podcast et de ses sujets, génère un titre court et un résumé de 1-2 phrases.

Sujets abordés : {topics_line}

Script (extrait) :
{script[:1200]}

Réponds avec EXACTEMENT ce format, rien d'autre :
TITLE: <titre de moins de 8 mots>
SUMMARY: <1-2 phrases sur ce dont parle le podcast>"""

    try:
        raw, _ = call_llm(
            prompt=prompt,
            llm_engine=llm_engine,
            gemini_api_key=gemini_api_key,
            model=model,
            api_url=api_url,
            timeout=60,
            num_predict=350,
        )

        title = ""
        summary_lines = []
        in_summary = False

        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("TITLE:"):
                title = stripped[6:].strip().strip('"')
                in_summary = False
            elif stripped.upper().startswith("SUMMARY:"):
                summary_lines = [stripped[8:].strip()]
                in_summary = True
            elif in_summary and stripped:
                summary_lines.append(stripped)

        summary = " ".join(summary_lines).strip()

        if title:
            return {"title": title, "summary": summary}
    except Exception as e:
        print(f"[WARN] Génération titre/résumé échouée : {e}")

    fallback_title = topics[0][:60] if topics else ("Podcast" if is_english else "Podcast généré")
    return {"title": fallback_title, "summary": ""}


def save_script(script: str, filename: str = "podcast_script.txt") -> None:
    with open(filename, "w", encoding="utf-8") as f:
        f.write(script)