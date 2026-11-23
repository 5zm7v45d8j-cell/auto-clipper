# Unverbindlicher Rechte-Check für Clip-Projekte

`clip_recht_check.py` ist eine interaktive Checkliste und ein Generator für einen Quellenhinweis-Entwurf.

## Wichtig

- Das Tool ist **keine Rechtsberatung** und trifft keine verbindliche Aussage zur Zulässigkeit eines Clips.
- Ein Häkchen, eine Quellenangabe, eine kurze Clipdauer, Untertitel oder Spiegelung begründen für sich allein keine Nutzungsrechte.
- Eine schriftliche Lizenz sollte Bearbeitung, Plattformen (z. B. YouTube und TikTok), Umfang, Gebiet, Laufzeit und Monetarisierung abdecken. Drittmaterial kann zusätzliche Rechte erfordern.
- Zitatrecht sowie Karikatur/Parodie/Pastiche hängen vom Einzelfall ab. Das Tool gibt dafür ausdrücklich keine Upload-Freigabe.
- Plattforminterne Remix-Funktionen sind an aktuelle Bedingungen gebunden und erlauben nicht automatisch Download oder Reupload auf anderen Plattformen.
- Der Quellenhinweis ist nur ein Entwurf. Ob und wie eine Quellenangabe erforderlich ist, hängt vom konkreten Kontext ab; sie ersetzt keine Erlaubnis.

Bei Unsicherheit vor Veröffentlichung qualifizierte urheberrechtliche Beratung einholen.

## Start

```bash
python uhrheberrecht/clip_recht_check.py
```

Das Skript verwendet nur die Python-Standardbibliothek. Unter Linux kann zum automatischen Kopieren `xclip` oder `xsel` installiert sein; dies ist optional.

## Tests

```bash
python -m unittest uhrheberrecht/test_clip_recht_check.py
```
