"""Send authorized videos to TikTok's inbox/draft flow (not public direct posting)."""
import argparse
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

from content_review import review_with_claude

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("TikTokUpload")
API = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lädt einen von Claude geprüften Clip als TikTok-Inbox-Entwurf hoch")
    parser.add_argument("video", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--transcript", type=Path, required=True, help="Transkript-Datei für Claude-Prüfung")
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--rights-confirmed", action="store_true", help="Bestätigt, dass Upload-/Bearbeitungsrechte vorliegen")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.rights_confirmed:
        log.error("Upload abgebrochen: --rights-confirmed fehlt")
        return 2
    if not args.video.is_file() or not args.transcript.is_file():
        log.error("Videodatei oder Transkript fehlt")
        return 2
    token = os.getenv("TIKTOK_ACCESS_TOKEN")
    if not token:
        log.error("TIKTOK_ACCESS_TOKEN fehlt; TikTok OAuth mit video.upload muss eingerichtet sein")
        return 2
    try:
        text = args.transcript.read_text(encoding="utf-8")
        review = review_with_claude(args.title, args.description, text, args.source_url)
        log.info("Claude-Prüfung: %s", json.dumps(review, ensure_ascii=False))
        if not review["approved"]:
            log.error("Claude hat den Upload abgelehnt; Gründe: %s", review.get("reasons", []))
            return 3
        size = args.video.stat().st_size
        if size <= 0:
            log.error("Videodatei ist leer")
            return 2
        body = {"source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}}
        request = urllib.request.Request(API, data=json.dumps(body).encode("utf-8"), headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
        }, method="POST")
        with urllib.request.urlopen(request, timeout=45) as response:
            init = json.loads(response.read().decode("utf-8"))
        if init.get("error", {}).get("code") not in (None, "ok"):
            raise RuntimeError(f"TikTok-Init fehlgeschlagen: {init['error']}")
        data = init.get("data", {})
        upload_url, publish_id = data.get("upload_url"), data.get("publish_id")
        if not upload_url or not publish_id:
            raise RuntimeError("TikTok lieferte keine upload_url/publish_id")
        content = args.video.read_bytes()
        upload = urllib.request.Request(upload_url, data=content, headers={
            "Content-Type": "video/mp4", "Content-Length": str(size), "Content-Range": f"bytes 0-{size - 1}/{size}",
        }, method="PUT")
        with urllib.request.urlopen(upload, timeout=180) as response:
            if response.status not in (200, 201, 206):
                raise RuntimeError(f"TikTok-Datei-Upload fehlgeschlagen: HTTP {response.status}")
        log.info("TikTok-Inbox-Entwurf initialisiert (publish_id=%s). Öffne TikTok, um den Upload zu prüfen und fertigzustellen.", publish_id)
        return 0
    except (OSError, ValueError, urllib.error.URLError, TimeoutError, RuntimeError) as exc:
        log.error("TikTok-Upload abgebrochen: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
