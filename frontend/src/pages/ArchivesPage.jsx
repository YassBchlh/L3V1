// Version5/frontend/src/pages/ArchivesPage.jsx
import { useState } from "react";
import "./ArchivesPage.css";
import logo from "../assets/logo-app.png";

const API_BASE_URL = "http://127.0.0.1:8000";

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

function ArchivesPage({ archives, onBack, onPlay }) {
  const [search, setSearch] = useState("");

  const filtered = archives.filter((a) =>
    (a.title || "").toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="archives-page">
      <div className="archives-container">

        {/* Header */}
        <div className="archives-header">
          <button className="archives-back-btn" onClick={onBack}>
            ← Retour
          </button>
          <div className="archives-title-row">
            <div className="builder-logo">
              <img src={logo} height="44" alt="Logo" />
              <h1>Podcast</h1>
            </div>
            <h2 className="archives-heading">🗂️ Tous les podcasts</h2>
          </div>
          <p className="archives-subtitle">
            {archives.length} podcast{archives.length !== 1 ? "s" : ""} généré{archives.length !== 1 ? "s" : ""}
          </p>

          {/* Search */}
          <div className="archives-search-wrap">
            <input
              className="archives-search"
              type="text"
              placeholder="🔍 Rechercher un podcast..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        {/* Grid */}
        {filtered.length === 0 ? (
          <div className="archives-empty">
            {search ? "Aucun résultat pour cette recherche." : "Aucun podcast archivé pour le moment."}
          </div>
        ) : (
          <div className="archives-grid">
            {filtered.map((archive, index) => (
              <ArchiveCard
                key={index}
                archive={archive}
                onPlay={() => onPlay && onPlay(archive)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ArchiveCard({ archive, onPlay }) {
  const hasAudio = !!(archive.audio_url || archive.audio_path);

  return (
    <div className="archive-card">
      <button
        className={`archive-play-btn ${!hasAudio ? "archive-play-btn--disabled" : ""}`}
        onClick={hasAudio ? onPlay : undefined}
        title={hasAudio ? "Écouter" : "Audio non disponible"}
        disabled={!hasAudio}
      >
        ▶
      </button>
      <div className="archive-card-info">
        <span className="archive-card-title">{archive.title || "Podcast sans titre"}</span>
        <span className="archive-card-date">{formatDate(archive.date || archive.generated_at)}</span>
      </div>
      {hasAudio && (
        <div className="archive-card-badge">Audio ✓</div>
      )}
    </div>
  );
}

export default ArchivesPage;
