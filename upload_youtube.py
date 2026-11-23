"""Upload a rights-cleared clip to YouTube as private after Claude review."""
import argparse
import json
import logging
import os
from pathlib import Path

from content_review import review_with_claude

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("YouTubeUpload")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Claude-Prüfung und privater YouTube-Upload")
    parser.add_argument("video", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--rights-confirmed", action="store_true", help="Bestätigt, dass Upload-/Bearbeitungsrechte vorliegen")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.rights_confirmed:
        logger.error("Upload abgebrochen: --rights-confirmed fehlt")
        return 2
    if not args.video.is_file() or not args.transcript.is_file():
        logger.error("Videodatei oder Transkript fehlt")
        return 2
    client_file = Path(os.getenv("YOUTUBE_OAUTH_CLIENT_JSON", "credentials/google-oauth.json"))
    if not client_file.is_file():
        logger.error("Google OAuth Client-Datei fehlt: %s", client_file)
        return 2
    try:
        review = review_with_claude(args.title, args.description, args.transcript.read_text(encoding="utf-8"), args.source_url)
        logger.info("Claude-Prüfung: %s", json.dumps(review, ensure_ascii=False))
        if not review["approved"]:
            logger.error("Claude hat den Upload abgelehnt: %s", review.get("reasons", []))
            return 3
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        scopes = ["https://www.googleapis.com/auth/youtube.upload"]
        flow = InstalledAppFlow.from_client_secrets_file(str(client_file), scopes)
        credentials = flow.run_local_server(port=0, open_browser=True)
        youtube = build("youtube", "v3", credentials=credentials)
        body = {
            "snippet": {"title": args.title[:100], "description": args.description},
            "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False},
        }
        media = MediaFileUpload(str(args.video), mimetype="video/mp4", resumable=True)
        response = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
        logger.info("Privater Upload erstellt: https://youtu.be/%s", response["id"])
        return 0
    except Exception as exc:
        logger.error("YouTube-Upload abgebrochen: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
