// Version5/frontend/src/App.jsx
import { useEffect, useState } from "react";
import BuilderPage from "./pages/BuilderPage";
import ScriptPage from "./pages/ScriptPage";
import PlayerPage from "./pages/PlayerPage";
import ArchivesPage from "./pages/ArchivesPage";
import "./App.css";

const API_BASE_URL = "http://127.0.0.1:8000";

function App() {
  const [page, setPage] = useState("builder");
  const [theme, setTheme] = useState("dark");
  const [ttsEngine, setTtsEngine] = useState("fish");

  const [selectedFiles, setSelectedFiles] = useState([]);
  const [links, setLinks] = useState([]);
  const [participants, setParticipants] = useState(["Paul", "Eva"]);
  const [language, setLanguage] = useState("Français");
  const [duration, setDuration] = useState("Court (1-3 min)");
  const [style, setStyle] = useState("Sérieux");
  const [llmEngine, setLlmEngine] = useState("local");
  const [geminiApiKey, setGeminiApiKey] = useState("");

  const [useIntro, setUseIntro] = useState(false);
  const [useOutro, setUseOutro] = useState(false);
  const [selectedIntro, setSelectedIntro] = useState("");
  const [selectedOutro, setSelectedOutro] = useState("");

  const [archives, setArchives] = useState([]);

  const [generatedData, setGeneratedData] = useState({
    id: null,
    title: "",
    date: "",
    generated_at: "",
    summary: "",
    description: "",
    script: "",
    scriptPath: "",
    audioPath: "",
    audioUrl: "",
    segmentsCount: 0,
  });

  const [loadingScript, setLoadingScript] = useState(false);
  const [loadingAudio, setLoadingAudio] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    document.body.setAttribute("data-theme", theme);
  }, [theme]);

  useEffect(() => {
    if (page === "builder") {
      document.title = "Page d'accueil";
    } else if (page === "script") {
      document.title = "Modification de script";
    } else if (page === "player") {
      document.title = "Audio";
    } else if (page === "archives") {
      document.title = "Archives";
    }
  }, [page]);

  const handleToggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  const handleAddParticipant = (voiceName) => {
    setParticipants((prev) => {
      if (prev.length >= 4) return prev;
      if (prev.includes(voiceName)) return prev;
      return [...prev, voiceName];
    });
  };

  const handleRemoveParticipant = (indexToRemove) => {
    setParticipants((prev) => {
      if (prev.length <= 2) return prev;
      return prev.filter((_, index) => index !== indexToRemove);
    });
  };

  const handleChangeParticipant = (indexToChange, newVoiceName) => {
    setParticipants((prev) => {
      if (prev.includes(newVoiceName)) return prev;
      const updated = [...prev];
      updated[indexToChange] = newVoiceName;
      return updated;
    });
  };

  const handlePlayArchive = (archive) => {
    setGeneratedData({
      id: archive.id || null,
      title: archive.title || "Podcast archivé",
      date: archive.date || "",
      generated_at: archive.generated_at || "",
      summary: archive.summary || "",
      description: archive.description || "",
      script: "",
      scriptPath: archive.script_path || "",
      audioPath: archive.audio_path || "",
      audioUrl: archive.audio_url || archive.audio_path || "",
      segmentsCount: 0,
    });
    setPage("player");
  };

  const handleGenerateScript = async () => {
    setLoadingScript(true);
    setError("");

    if (selectedFiles.length === 0 && links.length === 0) {
      setError("Ajoute au moins une source.");
      setLoadingScript(false);
      return;
    }

    try {
      const formData = new FormData();

      selectedFiles.forEach((file) => {
        formData.append("files", file);
      });

      formData.append("links", JSON.stringify(links));
      formData.append("podcast_language", language);
      formData.append("podcast_duration", duration);
      formData.append("podcast_style", style);
      formData.append("llm_engine", llmEngine);
      formData.append("gemini_api_key", geminiApiKey);
      formData.append("participants", JSON.stringify(participants));

      const response = await fetch(`${API_BASE_URL}/generate-script`, {
        method: "POST",
        body: formData,
      });

      let data = {};
      try {
        data = await response.json();
      } catch {
        throw new Error("Réponse backend invalide.");
      }

      if (!response.ok || data.error) {
        throw new Error(
          data.detail || data.error || "Erreur de génération du script."
        );
      }

      const newEntry = {
        id: data.id || null,
        title: data.title || "Podcast généré",
        date: data.date || "",
        generated_at: data.generated_at || "",
        script_path: data.script_path || "",
        audio_path: "",
        audio_url: "",
      };
      setArchives((prev) => [newEntry, ...prev]);

      setGeneratedData({
        id: data.id || null,
        title: data.title || "Podcast généré",
        date: data.date || "",
        generated_at: data.generated_at || "",
        summary: data.summary || "",
        description: data.description || "",
        script: data.script || "",
        scriptPath: data.script_path || "",
        audioPath: data.audio_path || "",
        audioUrl: data.audio_url || "",
        segmentsCount: data.segments_count || 0,
      });

      setPage("script");
    } catch (e) {
      setError(e.message || "Erreur lors de la génération");
    } finally {
      setLoadingScript(false);
    }
  };

  const handleGenerateAudio = async () => {
    setLoadingAudio(true);
    setError("");

    if (!generatedData.script.trim()) {
      setError("Le script est vide.");
      setLoadingAudio(false);
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/generate-audio`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          script: generatedData.script,
          podcast_language: language,
          participants,
          title: generatedData.title || "Podcast généré",
          intro_file: useIntro ? selectedIntro : undefined,
          outro_file: useOutro ? selectedOutro : undefined,
          tts_engine: ttsEngine,
        }),
      });

      let data = {};
      try {
        data = await response.json();
      } catch {
        throw new Error("Réponse backend invalide.");
      }

      if (!response.ok || data.error) {
        throw new Error(
          data.detail || data.error || "Erreur de génération audio."
        );
      }

      const audioPath = data.audio_path || generatedData.audioPath;
      const audioUrl = data.audio_url || data.audio_path || generatedData.audioUrl;

      setGeneratedData((prev) => ({
        ...prev,
        id: data.id || prev.id,
        audioPath,
        audioUrl,
      }));

      setArchives((prev) =>
        prev.map((entry) =>
          entry.id === (data.id || generatedData.id)
            ? { ...entry, audio_path: audioPath, audio_url: audioUrl }
            : entry
        )
      );

      setPage("player");
    } catch (e) {
      setError(e.message || "Erreur audio");
    } finally {
      setLoadingAudio(false);
    }
  };

  const globalButton = (
    <button className="global-theme-btn" onClick={handleToggleTheme}>
      {theme === "dark" ? "☀️ Mode clair" : "🌙 Mode nuit"}
    </button>
  );

  if (page === "player") {
    return (
      <>
        <div className="global-theme-wrap">{globalButton}</div>
        <PlayerPage
          generatedData={generatedData}
          onBack={() => setPage("script")}
          onNewPodcast={() => {
            setPage("builder");
            setGeneratedData({
              id: null,
              title: "",
              date: "",
              generated_at: "",
              summary: "",
              description: "",
              script: "",
              scriptPath: "",
              audioPath: "",
              audioUrl: "",
              segmentsCount: 0,
            });
          }}
        />
      </>
    );
  }

  if (page === "script") {
    return (
      <>
        <div className="global-theme-wrap">{globalButton}</div>
        <ScriptPage
          generatedData={generatedData}
          setGeneratedData={setGeneratedData}
          language={language}
          duration={duration}
          participants={participants}
          loadingAudio={loadingAudio}
          error={error}
          onBack={() => setPage("builder")}
          onGenerateAudio={handleGenerateAudio}
          onGoToPlayer={() => setPage("player")}
        />
      </>
    );
  }

  if (page === "archives") {
    return (
      <>
        <div className="global-theme-wrap">{globalButton}</div>
        <ArchivesPage
          archives={archives}
          onBack={() => setPage("builder")}
          onPlay={handlePlayArchive}
        />
      </>
    );
  }

  return (
    <>
      <div className="global-theme-wrap">{globalButton}</div>
      <BuilderPage
        selectedFiles={selectedFiles}
        setSelectedFiles={setSelectedFiles}
        links={links}
        setLinks={setLinks}
        participants={participants}
        language={language}
        setLanguage={setLanguage}
        duration={duration}
        setDuration={setDuration}
        style={style}
        setStyle={setStyle}
        llmEngine={llmEngine}
        setLlmEngine={setLlmEngine}
        geminiApiKey={geminiApiKey}
        setGeminiApiKey={setGeminiApiKey}
        loadingScript={loadingScript}
        error={error}
        onGenerate={handleGenerateScript}
        onAddParticipant={handleAddParticipant}
        onRemoveParticipant={handleRemoveParticipant}
        onChangeParticipant={handleChangeParticipant}
        archives={archives}
        onViewAllArchives={() => setPage("archives")}
        onPlayArchive={handlePlayArchive}
        ttsEngine={ttsEngine}
        setTtsEngine={setTtsEngine}
        useIntro={useIntro}
        setUseIntro={setUseIntro}
        useOutro={useOutro}
        setUseOutro={setUseOutro}
        selectedIntro={selectedIntro}
        setSelectedIntro={setSelectedIntro}
        selectedOutro={selectedOutro}
        setSelectedOutro={setSelectedOutro}
      />
    </>
  );
}

export default App;
