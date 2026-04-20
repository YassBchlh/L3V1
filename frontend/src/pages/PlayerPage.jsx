// Version5/frontend/src/pages/PlayerPage.jsx
import { useRef, useState, useEffect } from "react";
import "./PlayerPage.css";
import logo from "../assets/logo-app.png";
import { Play, Pause, Download, Plus, Mic, Clock, CheckCircle2, AlertCircle, Loader2, Copy, ExternalLink, X } from 'lucide-react';
import "./BuilderPage.css";
import { supabase } from "../services/supabaseClient";

function PlayerPage({ generatedData, onBack, onNewPodcast }) {
  const audioRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [actionMessage, setActionMessage] = useState("");
  const [showDownloadMenu, setShowDownloadMenu] = useState(false);
  const [showSpotifyModal, setShowSpotifyModal] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("idle");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [rssUrl, setRssUrl] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  const audioSrc = generatedData.audioUrl || generatedData.audioPath || "";

  const togglePlay = async () => {
    if (!audioRef.current) return;

    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      try {
        await audioRef.current.play();
        setIsPlaying(true);
      } catch (error) {
        console.error("Erreur lecture audio :", error);
      }
    }
  };

  const handleTimeUpdate = () => {
    if (!audioRef.current) return;
    setCurrentTime(audioRef.current.currentTime);
  };

  const handleLoadedMetadata = () => {
    if (!audioRef.current) return;
    setDuration(audioRef.current.duration || 0);
  };

  const handleProgressClick = (e) => {
    if (!audioRef.current || !duration) return;

    const rect = e.currentTarget.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const ratio = clickX / rect.width;

    audioRef.current.currentTime = ratio * duration;
    setCurrentTime(audioRef.current.currentTime);
  };

  const handleSpeedChange = () => {
    if (!audioRef.current) return;

    const speeds = [1, 1.25, 1.5, 2];
    const currentIndex = speeds.indexOf(playbackRate);
    const nextSpeed = speeds[(currentIndex + 1) % speeds.length];

    audioRef.current.playbackRate = nextSpeed;
    setPlaybackRate(nextSpeed);
  };

  const handleDownload = async (format = "mp3") => {
    if (!generatedData.id) {
      setActionMessage("Impossible de télécharger : ID manquant.");
      return;
    }

    try {
      setActionMessage(`Préparation du fichier ${format.toUpperCase()}...`);
      const response = await fetch(`http://localhost:8000/api/download/${generatedData.id}?format=${format}`);

      if (!response.ok) {
        throw new Error("Impossible de télécharger l'audio.");
      }

      const blob = await response.blob();
      const blobUrl = window.URL.createObjectURL(blob);

      const a = document.createElement("a");
      a.href = blobUrl;
      const fileName = generatedData.title ? generatedData.title.replace(/\s+/g, "_") : "podcast";
      a.download = `${fileName}.${format}`;

      document.body.appendChild(a);
      a.click();
      a.remove();

      window.URL.revokeObjectURL(blobUrl);
      setActionMessage(`Audio (${format.toUpperCase()}) téléchargé.`);
    } catch (error) {
      console.error("Erreur téléchargement audio :", error);
      setActionMessage("Erreur lors du téléchargement.");
    }
  };

  const handleSpotifyExport = () => {
    if (!generatedData.id || !audioSrc) return;
    setShowSpotifyModal(true);
    setUploadStatus("config");
    setErrorMsg("");
  };

  const performSpotifyExport = async (email, coverFile) => {
    setUploadStatus("uploading");
    setUploadProgress(10);
    setErrorMsg("");

    try {
      console.log("🛠️ Début de l'export Spotify...");
      const fileName = `podcast_${generatedData.id}`;
      const audioFileName = `${fileName}.mp3`;
      const coverFileName = `cover_${generatedData.id}_${Date.now()}.${coverFile.name.split('.').pop()}`;
      const rssFileName = `${fileName}.xml`;

      // 1. Upload de l'image cover
      setUploadProgress(15);
      const { data: coverData, error: coverError } = await supabase.storage
        .from('podcast-audio')
        .upload(coverFileName, coverFile, { upsert: true });

      if (coverError) {
        console.error("❌ Erreur Supabase Storage Cover :", coverError);
        throw coverError;
      }
      const { data: coverPublicUrl } = supabase.storage
        .from('podcast-audio')
        .getPublicUrl(coverFileName);

      // 2. Récupérer le fichier audio local
      setUploadProgress(30);
      const cleanAudioSrc = audioSrc.replace('localhost', 'localhost');

      const audioResponse = await fetch(cleanAudioSrc);
      if (!audioResponse.ok) throw new Error(`Impossible de lire le fichier audio local`);
      const audioBlob = await audioResponse.blob();

      // 3. Upload Audio vers Supabase Storage
      setUploadProgress(50);
      const { data: audioData, error: audioError } = await supabase.storage
        .from('podcast-audio')
        .upload(audioFileName, audioBlob, { upsert: true });

      if (audioError) throw audioError;

      const { data: audioPublicUrl } = supabase.storage
        .from('podcast-audio')
        .getPublicUrl(audioFileName);

      // 4. Générer le RSS
      setUploadProgress(70);
      const durationSeconds = Math.round(duration || 0);

      const rssContent = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>${generatedData.title || "Podcast"}</title>
    <description>${generatedData.summary || "Podcast généré à partir de ressources."}</description>
    <link>https://ton-site.com</link>
    <language>fr</language>

    <!-- Champs obligatoires iTunes -->
    <itunes:author>Pod-Ed</itunes:author>
    <itunes:owner>
      <itunes:name>Pod-Ed</itunes:name>
      <itunes:email>${email}</itunes:email>
    </itunes:owner>
    <itunes:image href="${coverPublicUrl.publicUrl}"/>

    <!-- Recommandé -->
    <itunes:category text="News"/>
    <itunes:explicit>no</itunes:explicit>

    <item>
      <title>${generatedData.title || "Episode"}</title>
      <description>${generatedData.summary || ""}</description>
      <pubDate>${new Date().toUTCString()}</pubDate>
      <enclosure url="${audioPublicUrl.publicUrl}" type="audio/mpeg" length="${audioBlob.size}"/>
      <guid>${generatedData.id}</guid>
      <itunes:duration>${durationSeconds}</itunes:duration>
    </item>
  </channel>
</rss>`;

      const rssBlob = new Blob([rssContent], { type: 'application/xml' });
      const { data: rssData, error: rssError } = await supabase.storage
        .from('podcast-audio')
        .upload(rssFileName, rssBlob, { upsert: true });

      if (rssError) throw rssError;

      const { data: rssPublicUrl } = supabase.storage
        .from('podcast-audio')
        .getPublicUrl(rssFileName);

      setUploadProgress(100);
      setRssUrl(rssPublicUrl.publicUrl);
      setUploadStatus("success");
    } catch (error) {
      console.error("💥 ERREUR GLOBALE EXPORT :", error);
      setErrorMsg(error.message || "Une erreur est survenue lors de l'export.");
      setUploadStatus("error");
    }
  };

  const formatTime = (value) => {
    if (!value || Number.isNaN(value)) return "00:00";
    const minutes = Math.floor(value / 60);
    const seconds = Math.floor(value % 60);
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(
      2,
      "0"
    )}`;
  };

  return (
    <div className="player-page">
      <button className="player-back-btn" onClick={onBack}>
        Retour
      </button>

      <div className="player-container">
        <div className="player-header-row">
          <div className="builder-logo">
            <img src={logo} height="50" alt="Logo" />
            <h1> Podcast</h1>
          </div>
          <h1 className="player-title">{generatedData.title}</h1>
        </div>

        <div className="player-metadata-row">
          <div className="player-metadata-item">
            {generatedData.date || generatedData.generated_at || "Date inconnue"}
          </div>
          <div className="player-metadata-item">
            {generatedData.segmentsCount || generatedData.segments_count || 0} segments
          </div>
        </div>

        <p className="player-description">
          {generatedData.description ||
            generatedData.summary ||
            "Votre podcast a été généré avec succès."}
        </p>

        <div className="player-audio-box">
          <button className="player-play-btn" onClick={togglePlay}>
            {isPlaying ? "⏸" : "▶"}
          </button>

          <span className="player-time-text">{formatTime(currentTime)}</span>

          <div
            className="player-progress-container"
            onClick={handleProgressClick}
          >
            <div
              className="player-progress-bar"
              style={{
                width: duration ? `${(currentTime / duration) * 100}%` : "0%",
              }}
            />
          </div>

          <span className="player-time-text">{formatTime(duration)}</span>

          <button className="player-speed-btn" onClick={handleSpeedChange}>
            x{playbackRate}
          </button>
        </div>

        <div className="player-button-row">
          <div className="dropdown-container">
            <button
              className="player-action-btn player-action-btn-primary"
              onClick={() => setShowDownloadMenu(!showDownloadMenu)}
            >
              ⬇ Télécharger
            </button>
            {showDownloadMenu && (
              <div className="download-dropdown">
                <button className="dropdown-item" onClick={() => { handleDownload("mp3"); setShowDownloadMenu(false); }}>
                  <i>🎵</i> MP3 (Compact)
                </button>
                <button className="dropdown-item" onClick={() => { handleDownload("wav"); setShowDownloadMenu(false); }}>
                  <i>🔊</i> WAV (Haute Qualité)
                </button>
              </div>
            )}
          </div>

          <button
            className="player-action-btn player-action-btn-primary"
            style={{ backgroundColor: '#1DB954', backgroundImage: 'none', boxShadow: '0 8px 24px rgba(29,185,84,0.3)' }}
            onClick={handleSpotifyExport}
          >
            <SpotifyLogo /> Export Spotify
          </button>

          <button
            className="player-action-btn"
            style={{ backgroundColor: 'var(--primary)', backgroundImage: 'none', boxShadow: '0 8px 24px var(--primary-glow)', display: 'flex', alignItems: 'center', gap: '8px' }}
            onClick={onNewPodcast}
            title="Créer un nouveau podcast"
          >
            <Plus size={18} /> Nouveau Podcast
          </button>
        </div>

        {actionMessage && (
          <div className="player-result-box">
            <p>{actionMessage}</p>
          </div>
        )}

        {audioSrc ? (
          <audio
            ref={audioRef}
            src={audioSrc}
            onTimeUpdate={handleTimeUpdate}
            onLoadedMetadata={handleLoadedMetadata}
            onEnded={() => setIsPlaying(false)}
          />
        ) : (
          <div className="player-error-box">Aucun audio disponible.</div>
        )}
      </div>

      {showSpotifyModal && (
        <SpotifyModal
          status={uploadStatus}
          progress={uploadProgress}
          rssUrl={rssUrl}
          error={errorMsg}
          onClose={() => setShowSpotifyModal(false)}
          onConfirm={performSpotifyExport}
        />
      )}
    </div>
  );
}

const SpotifyLogo = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.49 17.31c-.22.36-.67.47-1.03.25-2.85-1.74-6.43-2.13-10.66-1.16-.41.09-.82-.16-.91-.57-.09-.41.16-.82.57-.91 4.63-1.06 8.57-.61 11.77 1.34.37.23.49.68.27 1.05zm1.46-3.26c-.28.45-.87.59-1.32.31-3.25-2-8.2-2.59-12.04-1.42-.51.15-1.04-.14-1.19-.65-.15-.5.14-1.04.65-1.19 4.39-1.33 9.87-.66 13.59 1.63.45.27.6.86.31 1.32zm.12-3.41c-3.9-2.31-10.32-2.52-14.07-1.38-.6.18-1.24-.16-1.42-.76-.18-.6.16-1.24.76-1.42 4.32-1.31 11.41-1.06 15.93 1.62.54.32.72 1.02.4 1.56-.32.53-1.02.71-1.56.4z" />
  </svg>
);




const SpotifyModal = ({ status, progress, rssUrl, error, onClose, onConfirm }) => {
  const [email, setEmail] = useState(localStorage.getItem("podEdEmail") || "");
  const [coverFile, setCoverFile] = useState(null);
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (rssUrl) {
      navigator.clipboard.writeText(rssUrl).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2500);
      });
    }
  };

  const handleStartExport = () => {
    if (!email || !coverFile) {
      alert("Veuillez remplir l'adresse email et sélectionner une image de couverture.");
      return;
    }
    localStorage.setItem("podEdEmail", email);
    onConfirm(email, coverFile);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="modal-header">
          <span className="modal-title">Export Spotify</span>
          <button className="modal-close-btn" onClick={onClose}>&times;</button>
        </div>
        <div className="modal-body">
          {status === "config" && (
            <div className="modal-status-container" style={{ alignItems: 'flex-start', textAlign: 'left' }}>
              <span className="status-title">Configuration du Podcast</span>
              <p className="status-desc" style={{ marginBottom: '20px' }}>
                Veuillez fournir les informations manquantes (requises par Spotify).
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '15px', width: '100%' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px', fontWeight: 'bold' }}>Auteur</label>
                  <input
                    type="text"
                    value="Pod-Ed"
                    disabled
                    style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid var(--border)', background: 'var(--surface-dark)', color: '#888', cursor: 'not-allowed' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px', fontWeight: 'bold' }}>Email de contact (itunes:email)</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="exemple@gmail.com"
                    style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid var(--border)', background: 'var(--surface)', color: 'white' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px', fontWeight: 'bold' }}>Image de couverture</label>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={(e) => setCoverFile(e.target.files[0])}
                    style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid var(--border)', background: 'var(--surface)', color: 'white' }}
                  />
                </div>
              </div>

              <button
                className="modal-action-btn spotify-btn"
                style={{ marginTop: '25px', width: '100%' }}
                onClick={handleStartExport}
              >
                Lancer la diffusion
              </button>
            </div>
          )}

          {status === "uploading" && (
            <div className="modal-status-container">
              <span className="status-title">🚀 Export en cours...</span>
              <span className="status-desc">Transfert de l'audio, de la couverture et génération du flux RSS</span>
              <div className="progress-bar-container">
                <div className="progress-bar-fill" style={{ width: `${progress}%` }}></div>
              </div>
            </div>
          )}

          {status === "success" && (
            <div className="modal-status-container">
              <span className="status-title">✅ Export réussi !</span>
              <p className="status-desc">Ton podcast est prêt à être diffusé.</p>
              <div className="rss-box">
                <div className="rss-url-text">{rssUrl}</div>
                <button className="copy-btn" onClick={handleCopy}>
                  {copied ? <CheckCircle2 size={16} color="#1DB954" /> : <Copy size={16} />}
                  {copied ? 'Copié !' : 'Copier'}
                </button>
              </div>
              <button
                className="modal-action-btn spotify-btn"
                onClick={() => window.open("https://podcasters.spotify.com/", "_blank")}
              >
                Ouvrir Spotify for Podcasters
              </button>
            </div>
          )}

          {status === "error" && (
            <div className="modal-status-container">
              <span className="status-title" style={{ color: '#ef4444' }}>❌ Erreur</span>
              <p className="status-desc">{error}</p>
              <button className="modal-action-btn" onClick={onClose} style={{ border: '1px solid var(--border)', background: 'transparent', color: 'var(--text)' }}>
                Fermer
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};



export default PlayerPage;