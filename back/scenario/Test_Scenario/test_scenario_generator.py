# Version5/back/scenario/Test_Scenario/test_scenario_generator.py
"""
Tests unitaires — scenario_generator.py

Ce fichier teste toutes les fonctions du module scenario_generator,
qui gère la scénarisation des segments en dialogue de podcast.
Le LLM (Ollama) est mocké pour éviter tout appel réseau réel pendant les tests.
"""
import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

# On remonte d'un niveau pour atteindre le dossier scenario/
# où se trouve scenario_generator.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scenario_generator import (
    ScenarioError,
    get_duration_settings,
    normalize_participants,
    extract_topic_list,
    build_topics_summary,
    build_context_from_segments,
    call_llm_with_curl,
    build_prompt,
    normalize_script,
    count_dialogue_lines,
    looks_truncated,
    count_covered_topics,
    repair_script_with_llm,
    continue_script_with_llm,
    generate_dialogue_from_segments,
    save_script,
)


# ===========================================================================
# get_duration_settings
# ===========================================================================

class TestGetDurationSettings:
    def test_court(self):
        # Le format "Court (1-3 min)" doit retourner des paramètres
        # adaptés à un podcast court : moins de segments, moins de tokens.
        s = get_duration_settings("Court (1-3 min)")
        assert s["max_chars"] == 6000
        assert s["max_segments"] == 6

    def test_court_alias(self):
        # Les alias "court" et "1-3 min" doivent retourner
        # exactement les mêmes paramètres que "Court (1-3 min)".
        assert get_duration_settings("court") == get_duration_settings("1-3 min")

    def test_moyen(self):
        # Le format "Moyen (3-5 min)" doit retourner des paramètres
        # intermédiaires entre court et long.
        s = get_duration_settings("Moyen (3-5 min)")
        assert s["max_chars"] == 9000

    def test_moyen_alias(self):
        # Les alias "moyen" et "3-5 min" doivent retourner
        # les mêmes paramètres que "Moyen (3-5 min)".
        assert get_duration_settings("moyen") == get_duration_settings("3-5 min")

    def test_long(self):
        # Le format "Long (5-10 min)" doit retourner des paramètres
        # adaptés à un podcast long : plus de segments, plus de tokens.
        s = get_duration_settings("Long (5-10 min)")
        assert s["max_chars"] == 13000

    def test_long_alias(self):
        # Les alias "long" et "5-10 min" doivent retourner
        # les mêmes paramètres que "Long (5-10 min)".
        assert get_duration_settings("long") == get_duration_settings("5-10 min")

    def test_inconnu_retourne_defaut(self):
        # Une durée non reconnue doit retourner les paramètres par défaut
        # (équivalents à "moyen") pour éviter de bloquer le pipeline.
        s = get_duration_settings("inconnu")
        assert s["max_chars"] == 9000

    def test_none_retourne_defaut(self):
        # None doit retourner les paramètres par défaut sans exception.
        s = get_duration_settings(None)
        assert "max_chars" in s

    def test_champs_requis_presents(self):
        # Tous les champs nécessaires au pipeline doivent être présents
        # dans le dictionnaire retourné quelle que soit la durée.
        s = get_duration_settings("court")
        for key in ("max_chars", "num_predict", "timeout",
                    "max_segments", "min_lines", "max_lines", "max_continuations"):
            assert key in s


# ===========================================================================
# normalize_participants
# ===========================================================================

class TestNormalizeParticipants:
    def test_deux_participants_valides(self):
        # Deux participants valides doivent être retournés tels quels
        # après nettoyage des espaces.
        result = normalize_participants(["Voix_01", "Voix_02"])
        assert result == ["Voix_01", "Voix_02"]

    def test_un_seul_participant_retourne_defaut(self):
        # Un seul participant est insuffisant pour un dialogue.
        # La fonction doit retourner les deux voix par défaut.
        result = normalize_participants(["Seul"])
        assert result == ["Voix_01", "Voix_02"]

    def test_liste_vide_retourne_defaut(self):
        # Une liste vide doit retourner les deux voix par défaut
        # pour garantir qu'il y a toujours au moins deux intervenants.
        result = normalize_participants([])
        assert result == ["Voix_01", "Voix_02"]

    def test_espaces_supprimes(self):
        # Les espaces en début et fin de chaque participant
        # doivent être supprimés lors de la normalisation.
        result = normalize_participants(["  Alice  ", "  Bob  "])
        assert result == ["Alice", "Bob"]

    def test_non_strings_filtres(self):
        # Les éléments qui ne sont pas des chaînes de caractères
        # (None, int, etc.) doivent être filtrés silencieusement.
        result = normalize_participants([None, 42, "Alice", "Bob"])
        assert "Alice" in result
        assert "Bob" in result

    def test_strings_vides_filtrees(self):
        # Les chaînes vides doivent être filtrées car elles ne
        # représentent pas un participant valide.
        result = normalize_participants(["", "Alice", "Bob"])
        assert "" not in result


# ===========================================================================
# extract_topic_list
# ===========================================================================

class TestExtractTopicList:
    def test_titres_utilises_comme_topics(self):
        # Quand un segment a un titre, ce titre doit être utilisé
        # comme sujet du podcast plutôt que la première phrase.
        segs = [{"title": "IA et société", "text": "Du texte ici."}]
        result = extract_topic_list(segs)
        assert "IA et société" in result

    def test_sans_titre_premiere_phrase_utilisee(self):
        # Sans titre, la première phrase du texte est utilisée
        # comme sujet (tronquée à 120 caractères maximum).
        segs = [{"title": "", "text": "Première phrase importante. Suite du texte."}]
        result = extract_topic_list(segs)
        assert len(result) == 1
        assert "Première phrase" in result[0]

    def test_deduplique_les_topics(self):
        # Deux segments avec le même titre ne doivent produire
        # qu'un seul sujet pour éviter les répétitions dans le prompt.
        segs = [
            {"title": "IA", "text": "texte"},
            {"title": "IA", "text": "autre"},
        ]
        result = extract_topic_list(segs)
        assert result.count("IA") == 1

    def test_liste_vide(self):
        # Une liste de segments vide doit retourner une liste vide
        # sans lever d'exception.
        assert extract_topic_list([]) == []

    def test_segment_sans_titre_ni_texte(self):
        # Un segment sans titre ni texte ne doit pas produire de sujet.
        segs = [{"title": "", "text": ""}]
        result = extract_topic_list(segs)
        assert result == []


# ===========================================================================
# build_topics_summary
# ===========================================================================

class TestBuildTopicsSummary:
    def test_sans_topics_retourne_message(self):
        # Une liste de sujets vide doit retourner un message indiquant
        # qu'aucun sujet n'a été détecté plutôt qu'une liste vide.
        assert build_topics_summary([]) == "Aucun sujet détecté."

    def test_avec_topics_numerotes(self):
        # Les sujets doivent être numérotés à partir de 1
        # pour faciliter leur référencement dans le prompt.
        result = build_topics_summary(["Sujet A", "Sujet B"])
        assert "1. Sujet A" in result
        assert "2. Sujet B" in result

    def test_numerotation_correcte(self):
        # La numérotation doit être continue et correcte
        # quel que soit le nombre de sujets.
        result = build_topics_summary(["A", "B", "C"])
        assert "3. C" in result


# ===========================================================================
# build_context_from_segments
# ===========================================================================

class TestBuildContextFromSegments:

    def _seg(self, text="Texte du segment.", title="Titre", source_type="txt"):
        # Helper pour créer un segment de test avec les champs requis.
        return {"text": text, "title": title, "source_type": source_type}

    def test_liste_vide_exception(self):
        # Une liste de segments vide ne peut pas produire de contexte.
        # La fonction doit lever ScenarioError immédiatement.
        with pytest.raises(ScenarioError, match="Aucun segment"):
            build_context_from_segments([])

    def test_retourne_string(self):
        # Le contexte retourné doit être une chaîne de caractères
        # prête à être insérée dans le prompt du LLM.
        result = build_context_from_segments([self._seg()])
        assert isinstance(result, str)

    def test_contenu_inclus(self):
        # Le texte de chaque segment doit être présent dans le contexte
        # pour que le LLM puisse l'utiliser pour générer le dialogue.
        result = build_context_from_segments([self._seg("Contenu unique.")])
        assert "Contenu unique." in result

    def test_respecte_max_segments(self):
        # La fonction doit respecter la limite max_segments pour éviter
        # de surcharger le contexte du LLM avec trop d'informations.
        segs = [self._seg(f"Texte {i}.") for i in range(20)]
        result = build_context_from_segments(segs, max_segments=3)
        assert result.count("[SEGMENT") == 3

    def test_respecte_max_chars(self):
        # La fonction doit s'arrêter d'ajouter des segments quand
        # la limite max_chars est atteinte pour respecter le contexte du LLM.
        segs = [self._seg("A" * 1000) for _ in range(10)]
        result = build_context_from_segments(segs, max_chars=2000)
        assert len(result) <= 2500

    def test_segments_vides_ignores(self):
        # Les segments sans texte doivent être ignorés silencieusement
        # pour éviter des blocs vides dans le contexte.
        segs = [
            {"text": "", "title": "Vide", "source_type": "txt"},
            self._seg("Contenu valide.")
        ]
        result = build_context_from_segments(segs)
        assert "Contenu valide." in result

    def test_aucun_texte_exploitable_exception(self):
        # Si tous les segments sont vides, aucun contexte ne peut
        # être construit. La fonction doit lever ScenarioError.
        segs = [{"text": "", "title": "T", "source_type": "txt"}]
        with pytest.raises(ScenarioError, match="Aucun texte"):
            build_context_from_segments(segs)


# ===========================================================================
# call_llm_with_curl
# ===========================================================================

class TestCallLLMWithCurl:

    def _fake_response(self, response_text="Bonjour"):
        # Helper pour créer une réponse JSON simulée du LLM.
        return json.dumps({
            "response": response_text,
            "done": True,
            "done_reason": "stop",
            "eval_count": 10,
            "prompt_eval_count": 5,
        })

    @patch("scenario_generator.subprocess.run")
    def test_appel_reussi(self, mock_run):
        # Cas nominal : le LLM répond avec un texte valide.
        # La fonction doit retourner le texte et les métadonnées.
        mock_run.return_value = MagicMock(
            stdout=self._fake_response("Script ok"),
            returncode=0
        )
        text, meta = call_llm_with_curl("prompt", timeout=10)
        assert text == "Script ok"
        assert meta["done"] is True

    @patch("scenario_generator.subprocess.run")
    def test_reponse_vide_leve_exception(self, mock_run):
        # Si le serveur Ollama retourne une réponse vide,
        # la fonction doit lever ScenarioError car il n'y a
        # rien à parser.
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        with pytest.raises(ScenarioError, match="Réponse vide"):
            call_llm_with_curl("prompt", timeout=10)

    @patch("scenario_generator.subprocess.run")
    def test_json_invalide_leve_exception(self, mock_run):
        # Si la réponse n'est pas du JSON valide,
        # la fonction doit lever ScenarioError avec un message
        # indiquant que le JSON est invalide.
        mock_run.return_value = MagicMock(stdout="pas du json", returncode=0)
        with pytest.raises(ScenarioError, match="JSON invalide"):
            call_llm_with_curl("prompt", timeout=10)

    @patch("scenario_generator.subprocess.run")
    def test_champ_response_absent_leve_exception(self, mock_run):
        # Si le JSON est valide mais ne contient pas le champ "response",
        # la fonction doit lever ScenarioError car il n'y a pas de texte généré.
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"done": True}),
            returncode=0
        )
        with pytest.raises(ScenarioError, match="Aucune réponse"):
            call_llm_with_curl("prompt", timeout=10)

    @patch("scenario_generator.subprocess.run",
           side_effect=__import__("subprocess").TimeoutExpired(cmd="curl", timeout=10))
    def test_timeout_leve_exception(self, _):
        # Si curl dépasse le timeout, la fonction doit lever ScenarioError
        # avec un message indiquant que le serveur a mis trop de temps.
        with pytest.raises(ScenarioError, match="trop de temps"):
            call_llm_with_curl("prompt", timeout=10)

    @patch("scenario_generator.subprocess.run",
           side_effect=__import__("subprocess").CalledProcessError(1, "curl", stderr="erreur curl"))
    def test_curl_erreur_leve_exception(self, _):
        # Si curl retourne un code d'erreur, la fonction doit lever
        # ScenarioError avec le message d'erreur de curl.
        with pytest.raises(ScenarioError, match="Erreur curl"):
            call_llm_with_curl("prompt", timeout=10)


# ===========================================================================
# build_prompt
# ===========================================================================

class TestBuildPrompt:
    def test_retourne_string(self):
        # Le prompt retourné doit être une chaîne de caractères
        # prête à être envoyée au LLM.
        result = build_prompt("Contexte", "Court", ["Voix_01", "Voix_02"])
        assert isinstance(result, str)

    def test_contient_participants(self):
        # Les noms des participants doivent apparaître dans le prompt
        # pour que le LLM sache quels intervenants utiliser.
        result = build_prompt("Contexte", "Court", ["Voix_01", "Voix_02"])
        assert "Voix_01" in result
        assert "Voix_02" in result

    def test_contient_contexte(self):
        # Le contexte fourni doit être présent dans le prompt
        # pour que le LLM puisse s'appuyer sur les sources.
        result = build_prompt("Mon contexte unique.", "Court", ["Voix_01", "Voix_02"])
        assert "Mon contexte unique." in result

    def test_langue_francaise(self):
        # Quand la langue est "Français", le prompt doit contenir
        # les règles de langue française pour guider le LLM.
        result = build_prompt("ctx", "Court", ["V1", "V2"], podcast_language="Français")
        assert "français" in result.lower() or "Français" in result

    def test_langue_anglaise(self):
        # Quand la langue est "English", le prompt doit contenir
        # les règles de langue anglaise pour guider le LLM.
        result = build_prompt("ctx", "Court", ["V1", "V2"], podcast_language="English")
        assert "English" in result

    def test_topics_inclus(self):
        # Les sujets fournis doivent apparaître dans le prompt
        # pour que le LLM les couvre tous dans le dialogue.
        result = build_prompt("ctx", "Court", ["V1", "V2"], topics=["IA", "Éducation"])
        assert "IA" in result

    def test_topics_vide_ok(self):
        # Un topic vide ne doit pas faire planter la construction du prompt.
        result = build_prompt("ctx", "Court", ["V1", "V2"], topics=[])
        assert isinstance(result, str)


# ===========================================================================
# normalize_script
# ===========================================================================

class TestNormalizeScript:
    def test_garde_lignes_valides(self):
        # Les lignes commençant par un participant valide suivi de ":"
        # doivent être conservées dans le script normalisé.
        script = "Voix_01: Bonjour tout le monde.\nVoix_02: Bienvenue."
        result = normalize_script(script, ["Voix_01", "Voix_02"])
        assert "Voix_01: Bonjour tout le monde." in result
        assert "Voix_02: Bienvenue." in result

    def test_filtre_lignes_invalides(self):
        # Les lignes qui ne commencent pas par un participant valide
        # (narration, titres, etc.) doivent être supprimées.
        script = "Voix_01: Ligne valide.\nNarration hors dialogue.\nVoix_02: Autre."
        result = normalize_script(script, ["Voix_01", "Voix_02"])
        assert "Narration" not in result

    def test_aucune_ligne_valide_leve_exception(self):
        # Si aucune ligne valide n'est trouvée dans le script,
        # la fonction doit lever ScenarioError car le script est inutilisable.
        with pytest.raises(ScenarioError):
            normalize_script("Aucune ligne valide ici.", ["Voix_01", "Voix_02"])

    def test_lignes_vides_ignorees(self):
        # Les lignes vides ne doivent pas être incluses dans le résultat.
        script = "\nVoix_01: Une ligne.\n\nVoix_02: Autre ligne.\n"
        result = normalize_script(script, ["Voix_01", "Voix_02"])
        assert "Voix_01:" in result
        assert "Voix_02:" in result


# ===========================================================================
# count_dialogue_lines
# ===========================================================================

class TestCountDialogueLines:
    def test_compte_correct(self):
        # La fonction doit compter exactement le nombre de lignes
        # qui commencent par un participant valide.
        script = "Voix_01: Ligne 1.\nVoix_02: Ligne 2.\nVoix_01: Ligne 3."
        assert count_dialogue_lines(script, ["Voix_01", "Voix_02"]) == 3

    def test_ignore_non_participants(self):
        # Les lignes qui ne commencent pas par un participant valide
        # ne doivent pas être comptées.
        script = "Voix_01: Valide.\nNarration: Invalide."
        assert count_dialogue_lines(script, ["Voix_01", "Voix_02"]) == 1

    def test_script_vide(self):
        # Un script vide doit retourner 0 sans lever d'exception.
        assert count_dialogue_lines("", ["Voix_01"]) == 0


# ===========================================================================
# looks_truncated
# ===========================================================================

class TestLooksTruncated:
    def test_texte_vide_est_tronque(self):
        # Un texte vide est considéré comme tronqué car il ne contient
        # aucune ligne de dialogue.
        assert looks_truncated("") is True

    def test_fin_par_virgule_est_tronque(self):
        # Une fin par virgule indique clairement que la phrase
        # n'est pas terminée → le script est tronqué.
        assert looks_truncated("Voix_01: Bonjour,") is True

    def test_fin_correcte_pas_tronque(self):
        # Une fin par point indique que la dernière phrase est
        # complète → le script n'est pas tronqué.
        assert looks_truncated("Voix_01: Au revoir.") is False

    def test_fin_point_exclamation_pas_tronque(self):
        # Une fin par point d'exclamation est aussi une fin valide.
        assert looks_truncated("Voix_02: Excellent !") is False

    def test_derniere_ligne_vide_est_tronque(self):
        # Si la dernière ligne contient un participant sans texte,
        # le script est considéré comme tronqué.
        assert looks_truncated("Voix_01: Ligne.\nVoix_02: ") is True

    def test_fin_avec_mot_de_liaison_tronque(self):
        # Une fin par un mot de liaison (à, de, du, etc.)
        # indique que la phrase n'est pas terminée.
        assert looks_truncated("Voix_01: Cela est dû à") is True


# ===========================================================================
# count_covered_topics
# ===========================================================================

class TestCountCoveredTopics:
    def test_sujet_couvert(self):
        # Un sujet dont les mots clés apparaissent dans le script
        # doit être compté comme couvert.
        script = "Voix_01: On parle d'intelligence artificielle aujourd'hui."
        count = count_covered_topics(script, ["intelligence artificielle"])
        assert count == 1

    def test_sujet_non_couvert(self):
        # Un sujet dont les mots clés n'apparaissent pas dans le script
        # ne doit pas être compté comme couvert.
        script = "Voix_01: On parle de cuisine."
        count = count_covered_topics(script, ["intelligence artificielle"])
        assert count == 0

    def test_script_vide(self):
        # Un script vide ne couvre aucun sujet.
        assert count_covered_topics("", ["sujet"]) == 0

    def test_topics_vide(self):
        # Une liste de sujets vide retourne 0 sans exception.
        assert count_covered_topics("Script.", []) == 0

    def test_plusieurs_sujets(self):
        # Plusieurs sujets présents dans le script doivent tous
        # être comptés comme couverts.
        script = "Voix_01: On parle d'intelligence et de données et aussi d'éducation."
        count = count_covered_topics(script, ["intelligence", "données", "éducation"])
        assert count >= 2


# ===========================================================================
# repair_script_with_llm
# ===========================================================================

class TestRepairScriptWithLLM:
    @patch("scenario_generator.call_llm_with_curl")
    def test_appel_llm_et_normalise(self, mock_call):
        # La fonction doit appeler le LLM avec un prompt de réparation
        # et normaliser le script retourné pour le rendre exploitable.
        mock_call.return_value = (
            "Voix_01: Bonjour.\nVoix_02: Au revoir.",
            {"done": True}
        )
        result = repair_script_with_llm(
            raw_script="Script brut invalide.",
            participants=["Voix_01", "Voix_02"],
            podcast_duration="Court",
        )
        assert "Voix_01:" in result

    @patch("scenario_generator.call_llm_with_curl")
    def test_erreur_llm_propage(self, mock_call):
        # Si le LLM échoue pendant la réparation,
        # l'exception doit être propagée au lieu d'être silencieuse.
        mock_call.side_effect = ScenarioError("Serveur inaccessible")
        with pytest.raises(ScenarioError):
            repair_script_with_llm("script", ["Voix_01", "Voix_02"], "Court")


# ===========================================================================
# continue_script_with_llm
# ===========================================================================

class TestContinueScriptWithLLM:
    @patch("scenario_generator.call_llm_with_curl")
    def test_continue_et_merge(self, mock_call):
        # La fonction doit appeler le LLM pour continuer le script
        # et fusionner la continuation avec le script partiel existant.
        mock_call.return_value = (
            "Voix_02: Et voilà la suite.",
            {"done": True}
        )
        partial = "Voix_01: Début du podcast."
        result = continue_script_with_llm(
            partial_script=partial,
            context="Contexte source.",
            participants=["Voix_01", "Voix_02"],
            podcast_duration="Court",
        )
        # Le script partiel doit être présent dans le résultat fusionné
        assert "Voix_01: Début du podcast." in result
        # La continuation doit aussi être présente
        assert "Voix_02" in result

    @patch("scenario_generator.call_llm_with_curl")
    def test_erreur_continuation_propage(self, mock_call):
        # Si le LLM échoue pendant la continuation,
        # l'exception doit être propagée.
        mock_call.side_effect = ScenarioError("Timeout")
        with pytest.raises(ScenarioError):
            continue_script_with_llm(
                partial_script="Script.",
                context="ctx",
                participants=["Voix_01", "Voix_02"],
                podcast_duration="Court",
            )


# ===========================================================================
# generate_dialogue_from_segments
# ===========================================================================

class TestGenerateDialogueFromSegments:

    def _segments(self):
        # Helper pour créer une liste de segments de test.
        return [
            {"text": "Contenu sur l'IA.", "title": "Intelligence Artificielle", "source_type": "txt"},
            {"text": "Contenu sur l'éducation.", "title": "Éducation", "source_type": "txt"},
        ]

    @patch("scenario_generator.call_llm_with_curl")
    def test_genere_script_valide(self, mock_call):
        # Cas nominal : le LLM génère un script valide au premier essai.
        # La fonction doit retourner le script normalisé.
        mock_call.return_value = (
            "Voix_01: Bonjour et bienvenue.\nVoix_02: Merci d'être là.",
            {"done": True, "done_reason": "stop", "eval_count": 10, "prompt_eval_count": 5}
        )
        result = generate_dialogue_from_segments(
            segments=self._segments(),
            podcast_duration="Court",
            participants=["Voix_01", "Voix_02"],
        )
        assert "Voix_01:" in result

    @patch("scenario_generator.call_llm_with_curl")
    def test_repair_appele_si_normalisation_echoue(self, mock_call):
        # Si le script initial n'est pas valide (pas de lignes au bon format),
        # la fonction doit appeler repair_script_with_llm automatiquement.
        mock_call.side_effect = [
            # Première génération invalide
            ("Script sans format valide.", {"done": True, "done_reason": "stop"}),
            # Réparation réussie
            ("Voix_01: Script réparé.\nVoix_02: Fin.", {"done": True, "done_reason": "stop"}),
        ]
        result = generate_dialogue_from_segments(
            segments=self._segments(),
            podcast_duration="Court",
            participants=["Voix_01", "Voix_02"],
        )
        assert isinstance(result, str)

    @patch("scenario_generator.call_llm_with_curl")
    def test_limite_200_lignes(self, mock_call):
        # La fonction doit tronquer le script à 200 lignes maximum
        # pour éviter des podcasts trop longs.
        long_script = "\n".join(
            [f"Voix_0{(i%2)+1}: Ligne {i}." for i in range(250)]
        )
        mock_call.return_value = (
            long_script,
            {"done": True, "done_reason": "stop", "eval_count": 10, "prompt_eval_count": 5}
        )
        result = generate_dialogue_from_segments(
            segments=self._segments(),
            podcast_duration="Court",
            participants=["Voix_01", "Voix_02"],
        )
        assert len(result.splitlines()) <= 200

    @patch("scenario_generator.call_llm_with_curl")
    def test_retourne_string(self, mock_call):
        # La valeur retournée doit toujours être une chaîne de caractères.
        mock_call.return_value = (
            "Voix_01: Bonjour.\nVoix_02: Salut.",
            {"done": True, "done_reason": "stop", "eval_count": 5, "prompt_eval_count": 2}
        )
        result = generate_dialogue_from_segments(
            segments=self._segments(),
            podcast_duration="Court",
            participants=["Voix_01", "Voix_02"],
        )
        assert isinstance(result, str)


# ===========================================================================
# save_script
# ===========================================================================

class TestSaveScript:
    def test_sauvegarde_dans_fichier(self, tmp_path):
        # La fonction doit créer un fichier avec le contenu exact
        # du script fourni en paramètre.
        script = "Voix_01: Bonjour.\nVoix_02: Au revoir."
        filepath = str(tmp_path / "test_script.txt")
        save_script(script, filepath)
        assert os.path.exists(filepath)
        content = open(filepath, encoding="utf-8").read()
        assert content == script

    def test_ecrase_fichier_existant(self, tmp_path):
        # Si le fichier existe déjà, il doit être écrasé
        # avec le nouveau contenu sans lever d'exception.
        filepath = str(tmp_path / "script.txt")
        save_script("Ancien contenu.", filepath)
        save_script("Nouveau contenu.", filepath)
        content = open(filepath, encoding="utf-8").read()
        assert content == "Nouveau contenu."

    def test_fichier_vide(self, tmp_path):
        # Un script vide doit produire un fichier vide
        # sans lever d'exception.
        filepath = str(tmp_path / "vide.txt")
        save_script("", filepath)
        assert open(filepath).read() == ""

    def test_encodage_utf8(self, tmp_path):
        # Le fichier doit être sauvegardé en UTF-8 pour supporter
        # les caractères spéciaux français (accents, etc.).
        script = "Voix_01: Éducation, données, à bientôt."
        filepath = str(tmp_path / "utf8_script.txt")
        save_script(script, filepath)
        content = open(filepath, encoding="utf-8").read()
        assert "Éducation" in content