# auto-clipper

Automatische Recherche und Erstellung kurzer Clips aus **rechtlich freigegebenen** YouTube-Videos und Livestream-Aufzeichnungen.

## Sicherheit

- `channels.txt` enthält nur explizit freigegebene Kanäle im Format:

  ```text
  https://www.youtube.com/@IShowSpeed|approved=true
  ```

- Ohne `approved=true` wird ein Kanal nicht verarbeitet.
- Ohne ausdrückliche Erlaubnis dürfen fremde Videos nicht heruntergeladen oder veröffentlicht werden.
- YouTube-Uploads sind standardmäßig `private`.
- API-Schlüssel und OAuth-Dateien dürfen niemals ins Repository committed werden.

## Voraussetzungen

- Python 3.10 oder neuer
- FFmpeg im `PATH`
- Optional: Anthropic API-Key
- Optional: YouTube Data API-Key
- Für YouTube-Uploads: Google-OAuth-Client-ID und OAuth-Client-Geheimnis

## Installation

```bash
pip install -r requirements.txt
cp .env.example .env
```

Beispiel für `.env`:

```text
ANTHROPIC_API_KEY=...
YOUTUBE_API_KEY=...
YOUTUBE_OAUTH_CLIENT_JSON=credentials/google-oauth.json
YOUTUBE_UPLOAD_PRIVACY=private
```

## Nutzung

Multi-Signal-Analyse eines lokalen Videos:

```bash
python auto_clipper.py eingabe.mp4 --dry-run
python auto_clipper.py eingabe.mp4 -o clips_out
```

Freigegebene YouTube-Kanäle recherchieren und verarbeiten:

```bash
python clip_pipeline.py --once --dry-run
python clip_pipeline.py --once --clips 6 --min-score 0.62
```

YouTube-Clip privat hochladen:

```bash
python upload_youtube.py clip.mp4 --title "Clip-Titel" --description "Beschreibung"
```

Weitere Parameter werden durch `python clip_pipeline.py --help` angezeigt.

## Geplante Länge

Standardmäßig werden Clips zwischen 30 und 90 Sekunden erstellt. Die Pipeline passt bestehende Mindest-/Maximalwerte entsprechend an.
