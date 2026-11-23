import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("YouTubeUpload")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Privater YouTube-Upload eines Clips")
    parser.add_argument("video", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--privacy", choices=["private", "unlisted", "public"], default=os.getenv("YOUTUBE_UPLOAD_PRIVACY", "private"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.video.exists():
        logger.error("Video existiert nicht: %s", args.video)
        return 2

    if args.privacy != "private":
        logger.error("Aus Sicherheitsgründen erlaubt dieses Skript standardmäßig nur private oder unlisted Uploads.")
        if args.privacy == "public":
            return 2

    client_file = os.getenv("YOUTUBE_OAUTH_CLIENT_JSON", "credentials/google-oauth.json")
    if not Path(client_file).exists():
        logger.error("OAuth-Datei fehlt: %s", client_file)
        return 2

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        logger.error("YouTube-Upload-Abhängigkeiten fehlen: %s", exc)
        return 2

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    flow = InstalledAppFlow.from_client_secrets_file(client_file, scopes)
    credentials = flow.run_local_server(port=0, open_browser=True)

    youtube = build("youtube", "v3", credentials=credentials)
    body = {
        "snippet": {"title": args.title, "description": args.description},
        "status": {"privacyStatus": args.privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(str(args.video), mimetype="video/*", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = request.execute()
    logger.info("Upload erstellt: https://youtu.be/%s (Status: %s)", response["id"], args.privacy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
