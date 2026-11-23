# auto-clipper

Automatischer Clip-Bot für US-Streamer: lädt YouTube-Videos beziehungsweise Livestream-Aufzeichnungen herunter, erstellt ein Transkript und nutzt Gemini zur Auswahl viraler Clips.

## Voraussetzungen

- Python 3.10 oder neuer
- `ffmpeg` im `PATH`
- Gemini API-Key

## Installation

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="dein_api_key"
```

## Nutzung

Alle konfigurierten Kanäle aus `channels.txt` einmal verarbeiten:

```bash
python clip_maker.py --once
```

Ein einzelnes YouTube-Video mit dem Gaming-Split-Layout verarbeiten:

```bash
python clip_maker.py --url "https://youtube.com/watch?v=XXXX" --layout gaming_top
```

Weitere Optionen:

```bash
python clip_maker.py --watch 30
python clip_maker.py --once --clips 6 --min-score 8
python clip_maker.py --once --no-subs --no-norm
python clip_maker.py --once --cookies-from-browser chrome
```
