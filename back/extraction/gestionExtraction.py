# Version5/back/extraction/gestionExtraction.py
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import os
import re
import hashlib
import tempfile

import requests
import yt_dlp
import trafilatura
import fitz
import cairosvg

from faster_whisper import WhisperModel
from youtube_transcript_api import YouTubeTranscriptApi

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat

# ============================================================
# EXCEPTIONS PERSONNALISÉES
# ============================================================

class ResourceValidationError(Exception):
    """Ressource invalide avant tout traitement"""
    pass


class ExtractionError(Exception):
    """Échec pendant l'extraction de contenu"""
    pass


# ============================================================
# FONCTIONS DE VALIDATION
# ============================================================

def valider_fichier_local(chemin: str, extensions_autorisees: tuple):
    """Vérifie qu'un fichier local existe et a la bonne extension"""
    if not os.path.exists(chemin):
        raise ResourceValidationError(f"Fichier introuvable : '{chemin}'")

    if not os.path.isfile(chemin):
        raise ResourceValidationError(
            f"Le chemin ne pointe pas vers un fichier : '{chemin}'"
        )

    ext = Path(chemin).suffix.lower()
    if ext not in extensions_autorisees:
        raise ResourceValidationError(
            f"Extension '{ext}' non supportée. Extensions acceptées : {extensions_autorisees}"
        )


def valider_url(url: str):
    """Vérifie qu'une URL est bien formée et accessible."""
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ResourceValidationError(f"URL invalide (schéma incorrect) : '{url}'")

    if not parsed.netloc:
        raise ResourceValidationError(f"URL invalide (domaine manquant) : '{url}'")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.head(
            url,
            timeout=10,
            allow_redirects=True,
            headers=headers
        )

        # Certains sites comme Wikipedia bloquent HEAD
        if response.status_code in (403, 405):
            response = requests.get(
                url,
                timeout=10,
                allow_redirects=True,
                headers=headers
            )

        if response.status_code >= 400:
            raise ResourceValidationError(
                f"URL inaccessible (code {response.status_code}) : '{url}'"
            )

    except requests.exceptions.ConnectionError:
        raise ResourceValidationError(f"Impossible de se connecter à : '{url}'")
    except requests.exceptions.Timeout:
        raise ResourceValidationError(f"Timeout lors de la vérification de : '{url}'")
    except requests.exceptions.RequestException as e:
        raise ResourceValidationError(f"Erreur HTTP pour '{url}' : {e}")

def valider_url_youtube(url: str):
    """Vérifie qu'une URL YouTube contient bien un identifiant vidéo."""
    if "v=" not in url and "youtu.be/" not in url:
        raise ResourceValidationError(
            f"URL YouTube invalide (identifiant vidéo introuvable) : '{url}'"
        )

    try:
        ydl_opts = {"quiet": True, "no_warnings": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                raise ResourceValidationError(f"Vidéo YouTube introuvable : '{url}'")
    except yt_dlp.utils.DownloadError as e:
        raise ResourceValidationError(f"Vidéo YouTube inaccessible : {e}")


# ============================================================
# CLASSE ABSTRAITE SOURCE
# ============================================================

class ContentSource(ABC):
    def __init__(self):
        """
        Chaque type de document est au moins caractérisé
        par un identifiant unique, un titre, et sa date d'importation.
        """
        self.sourceID = None
        self.title = None
        self.importedAt = None

    @abstractmethod
    def extract_text(self):
        pass

    @abstractmethod
    def validate(self):
        pass

    @abstractmethod
    def clean_text(self, extracted_text):
        pass

    def set_importedAt(self):
        self.importedAt = datetime.now(timezone.utc)

    @abstractmethod
    def set_title(self):
        pass

    @abstractmethod
    def set_sourceID(self):
        pass

    @abstractmethod
    def final_info(self):
        pass


# ============================================================
# LIENS WEB
# ============================================================

class WebLinkSource(ContentSource):
    def __init__(self, url):
        super().__init__()
        self.url = url

    def set_title(self):
        downloaded = trafilatura.fetch_url(self.url)
        metadata = trafilatura.extract_metadata(downloaded)
        self.title = metadata.title if metadata and metadata.title else self.url

    def set_sourceID(self):
        self.url = self.url.strip().lower()
        parsed = urlparse(self.url)
        clean_url = f"{parsed.netloc}{parsed.path}".rstrip("/")
        self.sourceID = hashlib.md5(clean_url.encode()).hexdigest()

    def validate(self):
        valider_url(self.url)

    def extract_text(self):
        downloads = trafilatura.fetch_url(self.url)
        if downloads is None:
            raise ExtractionError(f"Échec du téléchargement pour {self.url}")

        text = trafilatura.extract(downloads, output_format="markdown")
        if text is None:
            return "Contenu illisible ou vide"

        return text

    def clean_text(self, extracted_text):
        if not extracted_text:
            return ""

        text = re.sub(r"\n{3,}", "\n\n", extracted_text)
        text = re.sub(r" +", " ", text)
        return text.strip()

    def final_info(self):
        self.set_title()
        self.set_sourceID()
        self.set_importedAt()
        text = self.extract_text()

        data = {
            "type": "website",
            "title": self.title,
            "sourceID": self.sourceID,
            "importedAt": self.importedAt,
            "text": self.clean_text(text),
        }
        return data


# ============================================================
# IMAGES
# ============================================================

def svg_to_png_bytes(svg_path: str) -> bytes:
    """
    Convertit un fichier SVG en image PNG (sous forme de bytes)
    si jamais tu veux le réutiliser plus tard.
    """
    return cairosvg.svg2png(url=svg_path)


EXTENSIONS_IMAGES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".heic")


class ImageSource(ContentSource):
    def __init__(self, imagePath: str):
        super().__init__()
        self.imagePath = imagePath

    def set_title(self):
        if self.imagePath.startswith("https://"):
            path = urlparse(self.imagePath).path
            filename = os.path.basename(path)
            title = os.path.splitext(filename)[0].replace("-", " ")
            self.title = title if title else "image distante"
        else:
            self.title = os.path.basename(self.imagePath).split(".")[0]

    def set_sourceID(self):
        if self.imagePath.startswith("https://"):
            clean_value = self.imagePath.strip().lower()
        else:
            clean_value = os.path.abspath(self.imagePath)

        self.sourceID = hashlib.md5(clean_value.encode()).hexdigest()

    def validate(self):
        if self.imagePath.startswith("https://"):
            valider_url(self.imagePath)
        else:
            valider_fichier_local(self.imagePath, EXTENSIONS_IMAGES)

    def extract_text(self):
        """
        Fallback sans modèle multimodal :
        on retourne un texte neutre décrivant la présence de l'image.
        """
        filename = os.path.basename(self.imagePath)
        return (
            f"Image importée : {filename}. "
            "Analyse automatique détaillée du contenu image indisponible "
            "car aucun modèle multimodal local n'est configuré."
        )

    def clean_text(self, extracted_text):
        return extracted_text.strip() if extracted_text else ""

    def final_info(self):
        self.set_title()
        self.set_sourceID()
        self.set_importedAt()
        text = self.extract_text()

        data = {
            "type": "image",
            "title": self.title,
            "sourceID": self.sourceID,
            "importedAt": self.importedAt,
            "text": self.clean_text(text),
        }
        return data


# ============================================================
# YOUTUBE
# ============================================================

class YoutubeSource(ContentSource):
    def __init__(self, video_url, transcript_language):
        super().__init__()
        self.video_url = video_url
        self.transcript_language = transcript_language

    def set_title(self):
        with yt_dlp.YoutubeDL() as ydl:
            info = ydl.extract_info(self.video_url, download=False)
            self.title = info.get("title", "Vidéo YouTube")

    def set_sourceID(self):
        if "v=" in self.video_url:
            self.sourceID = self.video_url.split("v=")[1].split("&")[0]
        elif "youtu.be/" in self.video_url:
            self.sourceID = self.video_url.split("youtu.be/")[1].split("?")[0]
        else:
            self.sourceID = hashlib.md5(self.video_url.encode()).hexdigest()

    def validate(self):
        valider_url_youtube(self.video_url)

    def extract_text(self):
        """
        Si la vidéo possède des sous-titres alors on utilise YouTubeTranscriptApi.
        Sinon, on extrait le contenu avec Whisper.
        """
        try:
            if "v=" in self.video_url:
                video_id = self.video_url.split("v=")[1].split("&")[0]
            else:
                video_id = self.video_url.split("youtu.be/")[1].split("?")[0]

            ytt = YouTubeTranscriptApi()
            transcript_list = ytt.list(video_id)

            try:
                transcript = transcript_list.find_transcript([self.transcript_language])
            except Exception:
                transcript = transcript_list.find_generated_transcript(
                    [self.transcript_language, "en"]
                )

            fetched = transcript.fetch()
            texte = " ".join(snippet.text for snippet in fetched)
            print("[INFO] Sous-titres récupérés directement depuis YouTube")
            return texte

        except Exception as e:
            print(f"[INFO] Sous-titres indisponibles : {e}, transcription Whisper...")
            return self.extract_with_whisper()

    def extract_with_whisper(self):
        """
        Extraction du contenu d'une vidéo YouTube avec yt-dlp + Whisper.
        """
        model_name = "base"
        temp_dir = tempfile.mkdtemp()
        audio_path = os.path.join(temp_dir, "audio.mp3")

        try:
            ydl_opts = {
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
                "outtmpl": os.path.join(temp_dir, "audio.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
            }

            print(f"Téléchargement de l'audio depuis {self.video_url}...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.video_url])

            print(f"Chargement du modèle Whisper '{model_name}'...")
            model = WhisperModel(model_name, device="cpu", compute_type="int8")
            segments, _info = model.transcribe(
                audio_path,
                beam_size=5,
                language=self.transcript_language
            )

            full_text = ""
            for segment in segments:
                full_text += f"{segment.text}"
            return full_text

        finally:
            try:
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                os.rmdir(temp_dir)
            except Exception:
                pass

    def clean_text(self, extracted_text):
        if not extracted_text:
            return ""

        text = extracted_text.replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"([.!?])\s*", r"\1\n", text)
        text = re.sub(r"\n{2,}", "\n\n", text)

        return text.strip()

    def final_info(self):
        self.set_title()
        self.set_sourceID()
        self.set_importedAt()
        text = self.extract_text()

        data = {
            "type": "Youtube",
            "title": self.title,
            "sourceID": self.sourceID,
            "importedAt": self.importedAt,
            "text": self.clean_text(text),
        }
        return data


# ============================================================
# DOCUMENTS
# ============================================================

class DocumentFileFormat(Enum):
    PDF = 1
    DOCX = 2
    TXT = 3
    MD = 4


FORMATS_SUPPORTES = (".pdf", ".docx", ".md", ".txt")


class DocumentFileSource(ContentSource):
    def __init__(self, filePath, fileFormat):
        super().__init__()
        self.filePath = filePath
        self.fileFormat = fileFormat

    def set_title(self):
        self.title = os.path.basename(self.filePath).split(".")[0]

    def set_sourceID(self):
        with open(self.filePath, "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
            self.sourceID = file_hash

    def validate(self):
        valider_fichier_local(self.filePath, FORMATS_SUPPORTES)

    def detecter_type_pdf(self) -> str:
        """Détecte le type de PDF : scanné, diaporama ou texte."""
        doc = fitz.open(self.filePath)
        nb_pages = len(doc)
        texte_total = ""
        nb_pages_paysage = 0
        total_mots = 0

        metadata = doc.metadata
        createur = (metadata.get("creator") or "").lower()
        producteur = (metadata.get("producer") or "").lower()

        outils_diapo = ["powerpoint", "keynote", "impress", "presentation"]
        est_cree_par_diapo = any(
            outil in createur or outil in producteur
            for outil in outils_diapo
        )

        for page in doc:
            texte = page.get_text()
            texte_total += texte
            total_mots += len(texte.split())

            if page.rect.width > page.rect.height:
                nb_pages_paysage += 1

        doc.close()

        moyenne_mots_par_page = total_mots / nb_pages if nb_pages > 0 else 0
        ratio_paysage = nb_pages_paysage / nb_pages if nb_pages > 0 else 0

        if len(texte_total.strip()) < 100:
            return "scanne"

        if est_cree_par_diapo or (ratio_paysage > 0.8 and moyenne_mots_par_page < 100):
            return "diaporama"

        return "texte"

    def _extraire_diaporama(self) -> str:
        doc = fitz.open(self.filePath)
        slides_textes = []

        for i, page in enumerate(doc):
            contenu_slide = ""

            texte = page.get_text().strip()
            if texte:
                contenu_slide += texte

            tableaux = page.find_tables()
            if tableaux.tables:
                for tableau in tableaux.tables:
                    df = tableau.to_pandas()
                    contenu_slide += "\n" + df.to_markdown(index=False)

            if contenu_slide.strip():
                slides_textes.append(contenu_slide.strip())

        doc.close()

        toutes_les_lignes = []
        for texte in slides_textes:
            toutes_les_lignes.extend(texte.split("\n"))

        frequence = Counter(
            ligne.strip() for ligne in toutes_les_lignes if ligne.strip()
        )
        nb_slides = len(slides_textes)
        lignes_repetitives = {
            ligne for ligne, count in frequence.items()
            if count >= nb_slides * 0.5
        }

        slides_nettoyees = ""
        for i, texte in enumerate(slides_textes):
            lignes = [
                ligne for ligne in texte.split("\n")
                if ligne.strip() not in lignes_repetitives
            ]
            contenu = "\n".join(lignes).strip()
            if contenu:
                slides_nettoyees += f"\n--- Slide {i+1} ---\n{contenu}"

        return slides_nettoyees

    def extract_text(self):
        ext = Path(self.filePath).suffix.lower()

        if not os.path.exists(self.filePath):
            raise FileNotFoundError(f"Fichier introuvable : {self.filePath}")

        if ext not in FORMATS_SUPPORTES:
            raise ValueError(f"Extension non supporté : {ext}")

        if ext in (".md", ".txt"):
            return Path(self.filePath).read_text(encoding="utf-8")

        if ext in (".pdf", ".docx"):
            try:
                converter = DocumentConverter()
                est_scanne = False

                if ext == ".pdf":
                    type_pdf = self.detecter_type_pdf()

                    if type_pdf == "diaporama":
                        return self._extraire_diaporama()

                    est_scanne = type_pdf == "scanne"

                    pipeline_options = PdfPipelineOptions()
                    pipeline_options.do_table_structure = True
                    pipeline_options.do_ocr = est_scanne

                    converter = DocumentConverter(
                        format_options={
                            InputFormat.PDF: PdfFormatOption(
                                pipeline_options=pipeline_options
                            )
                        }
                    )

                result = converter.convert(self.filePath)

                if est_scanne:
                    doc = result.document.export_to_text()
                else:
                    doc = result.document.export_to_markdown()

                return doc

            except Exception as e:
                raise RuntimeError(f"Erreur lors de l'extraction : {e}")

    def clean_text(self, extracted_text):
        if not extracted_text:
            return ""

        ext = Path(self.filePath).suffix.lower()

        if ext == ".pdf":
            typePDF = self.detecter_type_pdf()
        else:
            typePDF = "texte"

        text = extracted_text.replace("\xa0", " ")
        text = re.sub(r"-\n", "", text)
        text = re.sub(r"^\d+$", "", text, flags=re.MULTILINE)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        text = re.sub(r"- \[ \]", "", text)
        text = re.sub(r"- \[x\]", "", text, flags=re.IGNORECASE)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"^\s+$", "", text, flags=re.MULTILINE)

        if typePDF == "scanne":
            text = re.sub(r"([A-Z])([A-Z]{2,})", r"\1 \2", text)

        return text.strip()

    def final_info(self):
        self.set_title()
        self.set_sourceID()
        self.set_importedAt()
        ext = Path(self.filePath).suffix.lower()
        text = self.extract_text()

        data = {
            "type": ext,
            "title": self.title,
            "sourceID": self.sourceID,
            "importedAt": self.importedAt,
            "text": self.clean_text(text),
        }
        return data


# ============================================================
# EXTRACTION FINALE
# ============================================================

def extraction_final(ressources: list, fichier_sortie: str = None):
    """
    Extrait le contenu de chaque ressource et écrit les résultats dans un fichier Markdown.
    """
    if not ressources:
        print("Il n'y a pas de ressources")
        return ""

    extensions_images = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".heic")
    resultats = {}
    erreurs = []

    def traiter_ressource(ressource):
        if ressource.endswith(extensions_images):
            source = ImageSource(ressource)
            source.validate()
            return source.final_info()

        elif ressource.startswith("https://"):
            if ressource.startswith("https://www.youtube.com") or ressource.startswith("https://youtu.be"):
                source = YoutubeSource(ressource, "fr")
                source.validate()
                return source.final_info()
            else:
                source = WebLinkSource(ressource)
                source.validate()
                return source.final_info()

        elif ressource.endswith((".pdf", ".docx", ".md", ".txt")):
            extension = ressource.split(".")[-1]
            source = DocumentFileSource(ressource, extension)
            source.validate()
            return source.final_info()

        else:
            raise ResourceValidationError(f"Ressource non supportée : {ressource}")

    with ThreadPoolExecutor(max_workers=min(len(ressources), 8)) as executor:
        futures = {
            executor.submit(traiter_ressource, ressource): ressource
            for ressource in ressources
        }

        for future in as_completed(futures):
            ressource = futures[future]
            try:
                resultats[ressource] = future.result()
            except ResourceValidationError as e:
                msg = f"[VALIDATION] {ressource} → {e}"
                print(msg)
                erreurs.append(msg)
            except ExtractionError as e:
                msg = f"[EXTRACTION] {ressource} → {e}"
                print(msg)
                erreurs.append(msg)
            except Exception as e:
                msg = f"[ERREUR INATTENDUE] {ressource} → {e}"
                print(msg)
                erreurs.append(msg)

    if erreurs:
        print(f"\n{len(erreurs)} ressource(s) ont échoué :")
        for err in erreurs:
            print(f"  - {err}")

    if fichier_sortie is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fichier_sortie = f"extraction_{timestamp}.md"

    with open(fichier_sortie, "w", encoding="utf-8") as f:
        generation_date = datetime.now().strftime("%d/%m/%Y à %H:%M:%S")
        f.write("# Extraction des ressources\n\n")
        f.write(f"**Générée le :** {generation_date}  \n")
        f.write(f"**Nombre de ressources :** {len(resultats)}\n\n")
        f.write("---\n\n")

        for i, ressource in enumerate(ressources, start=1):
            if ressource not in resultats:
                continue

            info = resultats[ressource]

            imported_at = info.get("importedAt")
            if isinstance(imported_at, datetime):
                imported_at = imported_at.strftime("%d/%m/%Y %H:%M:%S UTC")

            f.write(f"## Ressource {i} — {info.get('title', 'Sans titre')}\n\n")
            f.write("| Champ       | Valeur |\n")
            f.write("|-------------|--------|\n")
            f.write(f"| **Type**    | `{info.get('type', '?')}` |\n")
            f.write(f"| **ID**      | `{info.get('sourceID', '?')}` |\n")
            f.write(f"| **Importé** | {imported_at or '?'} |\n\n")
            f.write("### Contenu\n\n")
            f.write(f"{info.get('text', '').strip()}\n\n")
            f.write("---\n\n")

    print(f"\nExtraction terminée → {fichier_sortie} ({len(resultats)} ressource(s))")
    return fichier_sortie


if __name__ == "__main__":
    print(
        extraction_final([
            "https://www.youtube.com/watch?v=byKDHPZG1t0",
            "C1-Réseaux Informatiques (2).pdf",
            "Capture.png",
            "https://www.waytonowhere.fr/maroc-arabe-marocain-le-darija-1-quelques-bases/",
            "Images_2.pdf",
        ])
    )