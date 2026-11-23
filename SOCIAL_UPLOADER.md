## Queue-Uploader

`social_uploader.py` lädt ausschließlich Clips, deren Status `approved` und deren
`rights_confirmed`-Feld `true` ist. Standardmäßig ist das Programm ein Dry-Run;
erst `--upload` startet die Uploadversuche.

```bash
python social_uploader.py --dry-run
python social_uploader.py --upload --yt-privacy private
python social_uploader.py --upload --platforms tiktok
```

YouTube verwendet standardmäßig `private`. TikTok verwendet standardmäßig den
Inbox/Draft-Endpunkt; `--tiktok-direct` ist nur für direktes Posten vorgesehen.
Zugangsdaten werden über `YOUTUBE_ACCESS_TOKEN` und `TIKTOK_ACCESS_TOKEN`
gelesen und gehören nicht ins Repository.

Vor dem Speichern liest der Uploader die Warteschlange erneut ein und aktualisiert
nur erkannte Clip-IDs. Damit werden Status und Listen aus gleichzeitigen Änderungen
nicht pauschal überschrieben.
