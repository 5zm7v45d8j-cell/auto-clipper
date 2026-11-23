# Warten auf Bestätigung

Das Skript `warten_auf_bestaetigung.py` verwaltet `pending_approval.json`.
Nur manuelle Aktionen ändern den Status; Claude-Empfehlungen gelten nicht als
Upload-Freigabe.

```bash
python warten_auf_bestaetigung.py --list
python warten_auf_bestaetigung.py --interactive
python warten_auf_bestaetigung.py --approve CLIP_ID_1 CLIP_ID_2
python warten_auf_bestaetigung.py --reject CLIP_ID_1
```

Zulässige Statuswerte sind `pending_approval`, `approved`, `rejected` und
`uploaded`. Die Datei wird atomar über eine temporäre Datei gespeichert.
