# auto-clipper

Werkzeuge für lokale Clip-Erstellung aus **ausdrücklich freigegebenen** YouTube-Videos und Twitch-Livestreams. Twitch-Monitoring prüft über Helix, ob ein freigegebener Kanal live ist, und zeichnet den Stream auf. Clips werden lokal geschnitten; Uploads führen vorab eine Claude-Inhaltsprüfung aus.

## Rechte und Sicherheitsgrenzen

Nur Quellen verarbeiten und veröffentlichen, für die Bearbeitungs- und Upload-Rechte vorliegen. Eine Streamer-Liste oder ein öffentlicher Stream ist keine Erlaubnis. Die Allowlist ist eine bewusste Selbstbestätigung und kein juristischer Rechtebeleg. Claude kann Inhalte auf erkennbare Sicherheits-/Policy-Risiken prüfen, aber Urheberrechte nicht feststellen. YouTube-Uploads bleiben privat; TikTok wird als Inbox-Entwurf hochgeladen und muss in TikTok geprüft/fertiggestellt werden. Keine automatische öffentliche Veröffentlichung.

## Installation

- Python 3.10+
- FFmpeg im PATH
- Twitch Developer App (Client ID und Secret)
- YouTube Data API OAuth Client-Datei für Upload
- TikTok OAuth Access Token mit Content Posting `video.upload`-Berechtigung
- Anthropic API-Key für vorgeschaltete Claude-Prüfung

```bash
pip install -r requirements.txt
cp .env.example .env
```

Speichere echte Schlüssel nur lokal in `.env`; `.env` und `credentials/` werden ignoriert. Zugangsdaten nicht committen.

## Quellen-Allowlist

In `channels.txt` nur Quellen mit bestätigten Rechten eintragen:

```text
https://www.youtube.com/@your_authorized_channel|approved=true|rights_confirmed=true
twitch|your_authorized_login|rights_confirmed=true
```

YouTube-VOD-Recherche/Verarbeitung kann über `clip_pipeline.py --once` gestartet werden. Ein API-Key dient der Metadatensuche; er ist keine Upload-Autorisierung.

## Twitch-Livestreams mitschneiden

```bash
python twitch_live.py --once
python twitch_live.py --poll-seconds 60 --output recordings
```

`--once` prüft einmalig und wartet bei einem Live-Treffer, bis der Stream endet. Ohne `--once` überwacht der Prozess fortlaufend und startet die Aufzeichnung eines freigegebenen Kanals, sobald er live ist. `--max-seconds 3600` begrenzt eine einzelne Aufzeichnung auf eine Stunde. Aufzeichnungen werden nicht automatisch veröffentlicht.

## Claude-Prüfung und Upload

Für beide Uploads ist ein Transkript erforderlich; das kann ein Transkript aus deinem autorisierten Clip-Prozess sein. Uploads benötigen außerdem die explizite Rechtebestätigung:

```bash
python upload_youtube.py clip.mp4 --title "Titel" --description "Beschreibung" --transcript transcript.txt --source-url "https://..." --rights-confirmed
python upload_tiktok.py clip.mp4 --title "Titel" --description "Beschreibung" --transcript transcript.txt --source-url "https://..." --rights-confirmed
```

YouTube wird privat hochgeladen. TikTok verwendet den Inbox/Draft-Weg, sofern dein TikTok-App-Zugang für `video.upload` eingerichtet ist; die Fertigstellung erfolgt in TikTok. API-Key allein genügt nicht: OAuth, Nutzerzustimmung und ggf. Plattformfreigaben sind erforderlich.

## Tests

```bash
python -m unittest discover -s tests
```

Die Integration benötigt lokale Laufzeit, Plattform-OAuth und Freigaben; diese API-/Medientests müssen in deiner Umgebung durchgeführt werden.
