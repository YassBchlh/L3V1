// Version5/frontend/src/pages/ScriptPage.jsx
import { useMemo, useState } from "react";
import "./BuilderPage.css";
import "./ScriptPage.css";
import logo from "../assets/logo-app.png";


function ScriptPage({
  generatedData,
  setGeneratedData,
  language,
  duration,
  participants,
  loadingAudio,
  error,
  onBack,
  onGenerateAudio,
  onGoToPlayer,
}) {
  const [showPreview, setShowPreview] = useState(false);
  const [actionMessage, setActionMessage] = useState("");

  // ✅ ROBUST PARSER (multi-voice safe)
  const scriptBlocks = useMemo(() => {
    if (!generatedData?.script?.trim()) return [];

    return generatedData.script
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line, index) => {
        const match = line.match(/^([^:]+):\s*(.*)$/);

        if (match) {
          return {
            id: index,
            speaker: match[1].trim(),
            text: match[2].trim(),
          };
        }

        return {
          id: index,
          speaker: "Narration",
          text: line,
        };
      });
  }, [generatedData]);

  const handleDownloadScript = () => {
    const script = generatedData?.script || "";
    if (!script.trim()) return;

    const blob = new Blob([script], { type: "text/plain;charset=utf-8" });
    const blobUrl = window.URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = `${generatedData?.title || "podcast_script"}.txt`;
    document.body.appendChild(a);
    a.click();
    a.remove();

    window.URL.revokeObjectURL(blobUrl);
    setActionMessage("Script téléchargé.");
  };

  const handleShareScript = async () => {
    const script = generatedData?.script || "";
    if (!script.trim()) return;

    try {
      if (navigator.share) {
        await navigator.share({
          title: generatedData?.title || "Script de podcast",
          text: script.slice(0, 1200),
        });
        setActionMessage("Script partagé.");
        return;
      }

      await navigator.clipboard.writeText(script);
      setActionMessage("Script copié.");
    } catch (err) {
      console.error("Erreur partage script :", err);
      setActionMessage("Impossible de partager le script.");
    }
  };

  return (
    <div className="script-page">
      <div className="script-container">
        <button className="script-back-btn" onClick={onBack}>
          Retour
        </button>

        <div className="script-top">
          <div className="builder-logo">
            <img src={logo} height="50" alt="Logo" />
            <h1> Podcast</h1>
          </div>

          <div className="script-head">
            <h1>{generatedData?.title || "Podcast généré"}</h1>

            <div className="script-date">
              {generatedData?.date || generatedData?.generated_at || "Date inconnue"}
            </div>

            {generatedData?.summary && (
              <p className="script-summary">{generatedData.summary}</p>
            )}

            <div className="script-meta">
              <span>Langue : {language}</span>
              <span>Durée : {duration}</span>
              <span>
                Participants :{" "}
                {participants?.length
                  ? participants.join(", ")
                  : "Détectés automatiquement"}
              </span>
              <span>
                Segments :{" "}
                {generatedData?.segmentsCount ??
                  generatedData?.segments_count ??
                  0}
              </span>
            </div>
          </div>
        </div>

        {/* EDITOR */}
        <div className="script-panel">
          <div className="script-panel-title">📝 Script généré</div>

          <textarea
            className="script-editor"
            value={generatedData?.script || ""}
            onChange={(e) =>
              setGeneratedData((prev) => ({
                ...prev,
                script: e.target.value,
              }))
            }
            placeholder="Le script apparaîtra ici..."
          />
        </div>

        {/* PREVIEW */}
        <div className="script-preview-panel">
          <div className="script-preview-header">
            <div className="script-preview-title">
              👀 Prévisualisation des répliques
            </div>

            <button
              className="script-toggle-btn"
              onClick={() => setShowPreview((prev) => !prev)}
            >
              {showPreview ? "Masquer" : "Afficher"}
            </button>
          </div>

          {showPreview && (
            <>
              {scriptBlocks.length === 0 ? (
                <div className="script-empty">Aucune réplique à afficher</div>
              ) : (
                scriptBlocks.map((block) => (
                  <div
                    className="script-dialogue-block"
                    key={block.id}
                  >
                    <div className="script-dialogue-speaker">
                      {block.speaker}
                    </div>
                    <div className="script-dialogue-text">
                      {block.text}
                    </div>
                  </div>
                ))
              )}
            </>
          )}
        </div>

        {/* ACTIONS */}
        <div className="script-actions">
          <button
            className="script-action-btn"
            onClick={onGenerateAudio}
            disabled={loadingAudio}
          >
            {loadingAudio
              ? "Génération audio..."
              : "🔊 Générer l’audio"}
          </button>

          <button
            className="script-action-btn secondary"
            onClick={handleDownloadScript}
            disabled={!generatedData?.script?.trim()}
          >
            ⬇ Télécharger le script
          </button>

          <button
            className="script-action-btn secondary"
            onClick={handleShareScript}
            disabled={!generatedData?.script?.trim()}
          >
            🔗 Partager le script
          </button>

          <button
            className="script-action-btn secondary"
            onClick={onGoToPlayer}
            disabled={
              !generatedData?.audioPath && !generatedData?.audioUrl
            }
          >
            🎧 Aller au lecteur
          </button>
        </div>

        {actionMessage && (
          <div className="script-result-box">{actionMessage}</div>
        )}

        {error && <div className="script-error-box">{error}</div>}
      </div>
    </div>
  );
}

export default ScriptPage;