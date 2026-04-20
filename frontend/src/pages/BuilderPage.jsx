import { useState, useRef, useEffect } from "react";
import "./BuilderPage.css";
import logo from "../assets/logo-app.png";
 
function getLinkType(url) {
  if (!url) return "web";
  if (url.includes("youtube.com/watch") || url.includes("youtu.be/")) return "youtube";
  return "web";
}
 
function getLinkIcon(url) {
  return getLinkType(url) === "youtube" ? "▶️" : "🌐";
}
 
function getLinkLabel(url) {
  try {
    const { hostname, pathname } = new URL(url);
    const short = (hostname + pathname).replace(/^www\./, "");
    return short.length > 45 ? short.slice(0, 45) + "…" : short;
  } catch {
    return url;
  }
}
 
function formatDate(dateStr) {
  if (!dateStr) return "Date inconnue";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}
 
function BuilderPage({
  selectedFiles,
  setSelectedFiles,
  links,
  setLinks,
  participants,
  onAddParticipant,
  onRemoveParticipant,
  onChangeParticipant,
  language,
  setLanguage,
  duration,
  setDuration,
  loadingScript,
  error,
  onGenerate,
  archives,
  onViewAllArchives,
  onPlayArchive,
  ttsEngine,
  setTtsEngine,
  useIntro,
  setUseIntro,
  useOutro,
  setUseOutro,
  selectedIntro,
  setSelectedIntro,
  selectedOutro,
  setSelectedOutro,
}) {
  // ========================
  // FICHIERS
  // ========================
 
  const handleAddFile = () => {
    const input = document.createElement("input");
    input.type = "file";
 
    input.onchange = (e) => {
      const file = e.target.files?.[0];
      if (file) {
        setSelectedFiles([...selectedFiles, file]);
      }
    };
 
    input.click();
  };
 
  const removeFile = (indexToRemove) => {
    setSelectedFiles(selectedFiles.filter((_, index) => index !== indexToRemove));
  };
 
  // ========================
  // LIENS
  // ========================
 
  const [linkInput, setLinkInput] = useState("");
  const [linkError, setLinkError] = useState("");
 
  const handleAddLink = () => {
    const val = linkInput.trim();
    if (!val) return;
 
    try {
      const url = new URL(val);
      if (!["http:", "https:"].includes(url.protocol)) {
        setLinkError("L'URL doit commencer par http:// ou https://");
        return;
      }
    } catch {
      setLinkError("URL invalide — ex: https://youtube.com/watch?v=...");
      return;
    }
 
    if (links.includes(val)) {
      setLinkError("Ce lien est déjà ajouté.");
      return;
    }
 
    setLinks([...links, val]);
    setLinkInput("");
    setLinkError("");
  };
 
  const handleLinkKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleAddLink();
    }
  };
 
  const removeLink = (indexToRemove) => {
    setLinks(links.filter((_, index) => index !== indexToRemove));
    setLinkError("");
  };
 
  // ========================
  // UI
  // ========================
 
  const [showVoiceModal, setShowVoiceModal] = useState(false);
  const [indexToReplace, setIndexToReplace] = useState(null);
 
  const [availableVoices, setAvailableVoices] = useState([]);
  const [availableIntros, setAvailableIntros] = useState([]);
  const [introsLoading, setIntrosLoading] = useState(false);
  const [introsError, setIntrosError] = useState(null);
 
  const fetchIntros = () => {
    setIntrosLoading(true);
    setIntrosError(null);
    fetch('http://127.0.0.1:8000/api/intros')
      .then(res => res.json())
      .then(data => {
        setIntrosLoading(false);
        if (data.intros && data.intros.length > 0) {
          setAvailableIntros(data.intros);
          if (!selectedIntro) setSelectedIntro(data.intros[0]);
          if (!selectedOutro) setSelectedOutro(data.intros[0]);
        } else {
          setIntrosError("Aucun fichier audio trouvé dans le dossier intros.");
        }
      })
      .catch(err => {
        setIntrosLoading(false);
        setIntrosError("Impossible de contacter le serveur pour charger les intros.");
        console.error("Erreur chargement intros", err);
      });
  };
 
  useEffect(() => { fetchIntros(); }, []);
 
  useEffect(() => {
    fetch('/voix.json')
      .then(res => res.json())
      .then(data => {
        const localData = data.map(v => ({ ...v, audio: `/audios/${v.nom}.mp3` }));
        setAvailableVoices(localData);
      })
      .catch(err => console.error("Erreur chargement voix", err));
  }, []);
 
  const [playingAudio, setPlayingAudio] = useState(null);
  const listAudioRef = useRef(null);
 
  useEffect(() => {
    listAudioRef.current = new Audio();
    return () => {
      if (listAudioRef.current) {
        listAudioRef.current.pause();
        listAudioRef.current.src = "";
      }
    };
  }, []);
 
  const handleListPlay = (audioUrl) => {
    if (!listAudioRef.current) return;
    if (playingAudio === audioUrl) {
      listAudioRef.current.pause();
      setPlayingAudio(null);
    } else {
      listAudioRef.current.src = audioUrl;
      listAudioRef.current.play().catch(e => console.error("Erreur lecture audio", e));
      setPlayingAudio(audioUrl);
      listAudioRef.current.onended = () => setPlayingAudio(null);
    }
  };
 
  const recentArchives = (archives || []).slice(0, 4);
 const hasLanguageMismatch = participants.some(name => {
  const voice = availableVoices.find(v => v.nom === name);
  if (!voice) return false;
  return language === "Français" ? voice.langue !== "fr" : voice.langue !== "en";
});
  return (
    <div className="builder-page">
      <div className="builder-container">
        <div className="builder-top">
          <div className="builder-logo">
            <img src={logo} height="50" alt="Logo" />
            <h1> Podcast</h1>
          </div>
          <p className="builder-subtitle">
            Transformez vos documents en podcasts pédagogiques intelligents.
          </p>
        </div>
 
        <div className="builder-grid">
          <div className="builder-panel">
            <h2 className="builder-panel-title">📂 Sources</h2>
 
            <div className="builder-section">
              <p className="builder-section-label">Fichiers</p>
 
              {selectedFiles.length === 0 ? (
                <p className="builder-empty">Aucun fichier ajouté</p>
              ) : (
                <div className="builder-list">
                  {selectedFiles.map((file, index) => (
                    <div key={index} className="builder-item">
                      <span className="builder-item-name">{file.name}</span>
                      <button
                        type="button"
                        className="builder-remove-btn"
                        onClick={() => removeFile(index)}
                        title="Supprimer ce fichier"
                      >
                        ❌
                      </button>
                    </div>
                  ))}
                </div>
              )}
 
              <button
                type="button"
                className="builder-action-btn secondary"
                onClick={handleAddFile}
              >
                ➕ Ajouter une source
              </button>
            </div>
 
            <div className="builder-section">
              <p className="builder-section-label">Liens</p>
 
              {links.length > 0 && (
                <div className="builder-list">
                  {links.map((link, index) => (
                    <div key={index} className="builder-item">
                      <span className="builder-link-icon">{getLinkIcon(link)}</span>
                      <span className="builder-item-name builder-link-text">
                        {getLinkLabel(link)}
                      </span>
                      <button
                        type="button"
                        className="builder-remove-btn"
                        onClick={() => removeLink(index)}
                        title="Supprimer ce lien"
                      >
                        ❌
                      </button>
                    </div>
                  ))}
                </div>
              )}
 
              <div className="builder-link-input-row">
                <input
                  className={`builder-link-input ${linkError ? "builder-link-input--error" : ""}`}
                  type="url"
                  placeholder="https://youtube.com/watch?v=... ou https://..."
                  value={linkInput}
                  onChange={(e) => { setLinkInput(e.target.value); setLinkError(""); }}
                  onKeyDown={handleLinkKeyDown}
                />
                <button
                  type="button"
                  className="builder-link-add-btn"
                  onClick={handleAddLink}
                  title="Ajouter le lien"
                  disabled={!linkInput.trim()}
                >
                  ＋
                </button>
              </div>
              {linkError && (
                <p className="builder-link-error">{linkError}</p>
              )}
            </div>
          </div>
 
          <div className="builder-panel">
            <h2 className="builder-panel-title">👥 Participants</h2>
 
            <div className="builder-section">
              <p className="builder-section-label">
                Participants (min 2, max 4)
              </p>
 
              <div className="builder-list">
                {participants.map((participant, index) => {
                  const cannotRemove = participants.length <= 2;
                  const voiceData = availableVoices.find(v => v.nom === participant);
 
                  return (
                    <div key={index} className="builder-item" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 15px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        {voiceData && (
                          <button
                            type="button"
                            onClick={() => handleListPlay(voiceData.audio)}
                            style={{ background: 'var(--primary)', border: 'none', borderRadius: '50%', width: '28px', height: '28px', color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '12px' }}
                            title="Écouter"
                          >
                            {playingAudio === voiceData.audio ? "⏸" : "▶"}
                          </button>
                        )}
                        <span className="builder-item-name" style={{ margin: 0, fontWeight: '500' }}>
                          {participant}
                        </span>
                        {voiceData && (
                          <span style={{ fontSize: '18px', display: 'flex', alignItems: 'center' }} title={voiceData.langue === 'fr' ? 'Français' : 'English'}>
                            {voiceData.langue === 'fr' ? '🇫🇷' : '🇬🇧'}
                          </span>
                        )}
                      </div>
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <button
                          type="button"
                          className="builder-remove-btn"
                          onClick={() => {
                            setIndexToReplace(index);
                            setShowVoiceModal(true);
                          }}
                          title="Remplacer cette voix"
                          style={{ fontSize: '16px', background: 'transparent', border: 'none', cursor: 'pointer', color: '#10b981' }}
                        >
                          🔄
                        </button>
                        <button
                          type="button"
                          className={`builder-remove-btn ${cannotRemove ? "disabled" : ""}`}
                          onClick={() => onRemoveParticipant(index)}
                          disabled={cannotRemove}
                          title={cannotRemove ? "Il faut au minimum 2 participants" : "Supprimer ce participant"}
                        >
                          ❌
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
 
              {(() => {
                const cannotAdd = participants.length >= 4;
                return (
                  <button
                    type="button"
                    className={`builder-action-btn secondary ${cannotAdd ? "disabled" : ""}`}
                    onClick={() => {
                      setIndexToReplace(null);
                      setShowVoiceModal(true);
                    }}
                    disabled={cannotAdd}
                    title={cannotAdd ? "Limite de 4 participants atteinte" : "Ajouter une voix"}
                  >
                    ➕ Ajouter une voix {cannotAdd && `(Max 4)`}
                  </button>
                );
              })()}
            </div>
 
            <div className="builder-section">
              <p className="builder-section-label">⚙️ Paramètres</p>
 
              <select
                className="builder-select"
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              >
                <option>Français</option>
                <option>English</option>
              </select>
 
              <select
                className="builder-select"
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
              >
                <option>Court (1-3 min)</option>
                <option>Moyen (3-5 min)</option>
                <option>Long (5-10 min)</option>
              </select>
 
              {/* SÉLECTEUR MOTEUR TTS */}
              <select
                className="builder-select"
                value={ttsEngine}
                onChange={(e) => setTtsEngine(e.target.value)}
              >
                <option value="fish">🐟 Fish Audio (cloud)</option>
                <option value="coqui">🐸 Coqui XTTS (local)</option>
              </select>
            </div>
 
            <div className="builder-section">
              <p className="builder-section-label">🎬 Habillage</p>
 
              {/* Intro Toggle */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '15px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', color: 'var(--text-light)', fontWeight: 500 }}>
                  <input type="checkbox" checked={useIntro} onChange={(e) => { setUseIntro(e.target.checked); if (e.target.checked && availableIntros.length === 0) fetchIntros(); }} style={{ transform: 'scale(1.2)' }} />
                  Activer une Intro
                </label>
                {useIntro && availableIntros.length > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginLeft: '25px' }}>
                    <select className="builder-select" style={{ flex: 1, margin: 0 }} value={selectedIntro} onChange={(e) => setSelectedIntro(e.target.value)}>
                      {availableIntros.map(intro => <option key={intro} value={intro}>{intro}</option>)}
                    </select>
                    <button type="button" onClick={() => handleListPlay(`http://127.0.0.1:8000/intros/${selectedIntro}`)} style={{ background: 'var(--primary)', border: 'none', borderRadius: '50%', width: '32px', height: '32px', flexShrink: 0, color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }} title="Écouter l'intro">
                      {playingAudio === `http://127.0.0.1:8000/intros/${selectedIntro}` ? "⏸" : "▶"}
                    </button>
                  </div>
                )}
                {useIntro && availableIntros.length === 0 && (
                  <div style={{ marginLeft: '25px', color: '#f87171', fontSize: '0.85rem' }}>
                    {introsLoading ? "Chargement..." : introsError || "Aucun fichier trouvé dans le dossier intros."}
                  </div>
                )}
              </div>
 
              {/* Outro Toggle */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', color: 'var(--text-light)', fontWeight: 500 }}>
                  <input type="checkbox" checked={useOutro} onChange={(e) => { setUseOutro(e.target.checked); if (e.target.checked && availableIntros.length === 0) fetchIntros(); }} style={{ transform: 'scale(1.2)' }} />
                  Activer une Outro
                </label>
                {useOutro && availableIntros.length > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginLeft: '25px' }}>
                    <select className="builder-select" style={{ flex: 1, margin: 0 }} value={selectedOutro} onChange={(e) => setSelectedOutro(e.target.value)}>
                      {availableIntros.map(outro => <option key={outro} value={outro}>{outro}</option>)}
                    </select>
                    <button type="button" onClick={() => handleListPlay(`http://127.0.0.1:8000/intros/${selectedOutro}`)} style={{ background: 'var(--primary)', border: 'none', borderRadius: '50%', width: '32px', height: '32px', flexShrink: 0, color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }} title="Écouter l'outro">
                      {playingAudio === `http://127.0.0.1:8000/intros/${selectedOutro}` ? "⏸" : "▶"}
                    </button>
                  </div>
                )}
                {useOutro && availableIntros.length === 0 && (
                  <div style={{ marginLeft: '25px', color: '#f87171', fontSize: '0.85rem' }}>
                    {introsLoading ? "Chargement..." : introsError || "Aucun fichier trouvé dans le dossier intros."}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
 
        <div className="builder-generate-wrap">
          {hasLanguageMismatch && (
            <div className="builder-error-box" style={{ marginBottom: "12px" }}>
              ⚠️ Certains participants ne correspondent pas à la langue sélectionnée. Veuillez remplacer les voix ou changer la langue.
            </div>
          )}
          <button
            type="button"
            className="builder-generate-btn"
            onClick={onGenerate}
            disabled={loadingScript || hasLanguageMismatch}
          >
            {loadingScript ? "⏳ Génération..." : "🚀 Générer le podcast"}
          </button>

          {error && <div className="builder-error-box">{error}</div>}
        </div>
        {/* SECTION ARCHIVES */}
        <div className="builder-archives-section">
          <div className="builder-archives-header">
            <span className="builder-archives-label">🗂️ Archives :</span>
          </div>
 
          {recentArchives.length === 0 ? (
            <div className="builder-archives-empty">
              <span>Aucun podcast généré pour le moment.</span>
              <span className="builder-archives-empty-hint">Vos podcasts apparaîtront ici après génération.</span>
            </div>
          ) : (
            <div className="builder-archives-row">
              {recentArchives.map((archive, index) => (
                <button
                  key={index}
                  className={`builder-archive-card ${!(archive.audio_url || archive.audio_path) ? "builder-archive-card--no-audio" : ""}`}
                  onClick={() => (archive.audio_url || archive.audio_path) && onPlayArchive && onPlayArchive(archive)}
                  title={(archive.audio_url || archive.audio_path) ? "Écouter" : "Audio non disponible"}
                  disabled={!(archive.audio_url || archive.audio_path)}
                >
                  <div className="builder-archive-play">▶</div>
                  <div className="builder-archive-info">
                    <span className="builder-archive-title">{archive.title || "Podcast sans titre"}</span>
                    <span className="builder-archive-date">{formatDate(archive.date || archive.generated_at)}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
 
          <div className="builder-archives-footer">
            <button
              className="builder-voir-tout-btn"
              onClick={onViewAllArchives}
            >
              Voir tout
            </button>
          </div>
        </div>
      </div>
 
      {showVoiceModal && (
        <VoiceSelectionModal
          availableVoices={availableVoices}
          currentParticipants={participants}
          language={language}          // ← ajoute ça
          onClose={() => {
            setShowVoiceModal(false);
            setIndexToReplace(null);
          }}
          onSelect={(nom) => {
            if (indexToReplace !== null) {
              onChangeParticipant(indexToReplace, nom);
            } else {
              onAddParticipant(nom);
            }
      }}
  />
)}
    </div>
  );
}
 
const VoiceSelectionModal = ({ onClose, onSelect, currentParticipants, availableVoices, language }) => {
  const [playingAudio, setPlayingAudio] = useState(null);
  const audioRef = useRef(null);
 
  useEffect(() => {
    audioRef.current = new Audio();
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.src = "";
      }
    };
  }, []);
 
  const handlePlay = (audioUrl) => {
    if (!audioRef.current) return;
 
    if (playingAudio === audioUrl) {
      audioRef.current.pause();
      setPlayingAudio(null);
    } else {
      audioRef.current.src = audioUrl;
      audioRef.current.play().catch(e => console.error("Erreur lecture audio", e));
      setPlayingAudio(audioUrl);
      audioRef.current.onended = () => setPlayingAudio(null);
    }
  };
 
const remainingVoices = availableVoices.filter(v =>
  !currentParticipants.includes(v.nom) &&
  (language === "Français" ? v.langue === "fr" : v.langue === "en")
); 
  return (
    <div className="modal-overlay">
      <div className="modal-content" style={{ maxWidth: '450px' }}>
        <div className="modal-header">
          <span className="modal-title">Sélectionner une voix</span>
          <button className="modal-close-btn" onClick={onClose}>&times;</button>
        </div>
        <div className="modal-body" style={{ maxHeight: '60vh', overflowY: 'auto' }}>
          {remainingVoices.length === 0 ? (
            <p style={{ textAlign: "center", color: "#888" }}>Toutes les voix disponibles ont été sélectionnées.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {remainingVoices.map((voice) => (
                <div key={voice.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', background: 'var(--surface-dark)', borderRadius: '8px', border: '1px solid var(--border)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
                    <button
                      onClick={() => handlePlay(voice.audio)}
                      style={{ background: 'var(--primary)', border: 'none', borderRadius: '50%', width: '36px', height: '36px', color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '14px' }}
                      title="Écouter l'aperçu"
                    >
                      {playingAudio === voice.audio ? "⏸" : "▶"}
                    </button>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                      <span style={{ fontWeight: 'bold', color: 'var(--text)', fontSize: '15px' }}>{voice.nom}</span>
                      <span style={{ fontSize: '12px', color: '#888', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{voice.langue === 'fr' ? '🇫🇷 Français' : '🇬🇧 English'}</span>
                    </div>
                  </div>
                  <button
                    onClick={() => { onSelect(voice.nom); onClose(); }}
                    style={{ background: 'var(--surface)', color: 'var(--text)', border: '1px solid var(--border)', padding: '6px 12px', borderRadius: '6px', cursor: 'pointer', fontWeight: '500', transition: 'all 0.2s' }}
                    onMouseOver={(e) => Object.assign(e.target.style, { background: 'var(--border)' })}
                    onMouseOut={(e) => Object.assign(e.target.style, { background: 'var(--surface)' })}
                  >
                    Ajouter
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
 
export default BuilderPage;