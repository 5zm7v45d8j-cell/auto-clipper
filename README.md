# auto-clipper

Automatische lokale Clip-Erstellung für Videos, die du rechtlich bearbeiten darfst. Ermittelt Audio-/Szenen-Peaks, transkribiert optional mit faster-whisper, lässt Claude Transkript-Kontext bewerten und kann aktuelle Themen mit Gemini plus Google Search Grounding recherchieren.

## Rechtliche Nutzung und Uploads

Verarbeite und veröffentliche ausschließlich Videos, für die du Rechte oder eine ausdrückliche Erlaubnis hast. Die Streamer-Liste ist lediglich eine Referenz, keine Nutzungserlaubnis. Das Skript lädt keine fremden Streams/Videos herunter und veröffentlicht nichts automatisch. Der separate YouTube-Uploader bleibt ein expliziter manueller Schritt und verwendet standardmäßig `private`.

## Voraussetzungen

- Python 3.10+
- FFmpeg im PATH
- Optional: `GEMINI_API_KEY` für aktuelle Recherche und Quellenmetadaten
- Optional: `ANTHROPIC_API_KEY` für Titel/Hook-Bewertung aus Transkript-Kontext
- Optional: `YOUTUBE_API_KEY` für YouTube-Suchmetadaten (kein Upload-Zugang)

```bash
pip install -r requirements.txt
cp .env.example .env
```

Trage Schlüssel lokal in `.env` ein. `.env` und OAuth-Credentials sind ignoriert und gehören nicht ins Git-Repository.

## Start

```bash
python auto_clipper.py --list-streamers
python auto_clipper.py video.mp4 --streamer "IShowSpeed" --topic "GTA 6" --dry-run
python auto_clipper.py video.mp4 --streamer "IShowSpeed" --topic "GTA 6" -o clips_out
```

`--dry-run` erstellt ein JSON-Manifest mit Transkript, gefundenen Kandidaten, Recherche-Zusammenfassung und Gemini-Quellen-URLs; es rendert keine Clips. Verwende `--no-transcript` oder `--no-research`, um diese optionalen Schritte abzuschalten. Whisper kann beim ersten Start sein Modell herunterladen.

Clips werden auf 30–90 Sekunden begrenzt. Kurzvideos unter der gewählten Mindestlänge ergeben keine Clips. Gemini-Recherche und YouTube-Metadatensuche sind getrennte Dienste; Google Search Grounding benötigt `GEMINI_API_KEY`, YouTube-Suche `YOUTUBE_API_KEY`.

## YouTube Upload

Für Uploads brauchst du OAuth-Zugang und die YouTube Data API. Ein API-Key allein reicht nicht. Upload weiterhin manuell und zunächst privat:

```bash
python upload_youtube.py clip.mp4 --title "Titel" --description "Beschreibung"
```
