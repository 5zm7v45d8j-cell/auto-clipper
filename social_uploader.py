#!/usr/bin/env python3
"""Safe queue uploader for already-approved clips.

Uploads only after: (1) approval_status=approved and (2) rights_confirmed=true.
TikTok defaults to the inbox/draft endpoint. YouTube defaults to private.
The queue is re-read before every save and changes are merged by clip_id.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SocialUploader")

YOUTUBE_UPLOAD_API = "https://www.googleapis.com/upload/youtube/v3/videos"
TIKTOK_INBOX_API = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
TIKTOK_DIRECT_API = "https://open.tiktokapis.com/v2/post/publish/video/init/"


def load_queue(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Warteschlange nicht gefunden: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ungültige Warteschlange: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("clips", []), list):
        raise ValueError("Warteschlange muss ein Objekt mit einer clips-Liste sein")
    return data


def save_queue_merged(path: Path, updates: Dict[str, Dict]) -> None:
    """Re-read live queue and merge only uploaded_targets/status for known clip IDs."""
    live = load_queue(path)
    by_id = {c.get("clip_id"): c for c in live.get("clips", []) if c.get("clip_id")}
    for clip_id, update in updates.items():
        clip = by_id.get(clip_id)
        if not clip:
            continue
        if update.get("_live_approved") is True:
            clip["uploaded_targets"] = sorted(set(update.get("uploaded_targets", [])))
            if set(update.get("requested_platforms", [])).issubset(set(clip.get("uploaded_targets", []))):
                clip["approval_status"] = "uploaded"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(live, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def json_response(response) -> dict:
    return json.loads(response.read().decode("utf-8"))


def upload_to_youtube(clip: Dict, access_token: str, privacy_status: str = "private") -> str:
    video_path = Path(clip["output_file"])
    if not video_path.is_file():
        raise FileNotFoundError(f"Clip fehlt: {video_path}")

    metadata = {
        "snippet": {
            "title": str(clip.get("title", "Viral Clip"))[:100],
            "description": str(clip.get("description", "")),
            "tags": clip.get("tags", ["Shorts"]),
            "categoryId": "20",
        },
        "status": {"privacyStatus": privacy_status, "selfDeclaredMadeForKids": False},
    }
    url = YOUTUBE_UPLOAD_API + "?uploadType=resumable&part=snippet,status"
    init_req = urllib.request.Request(
        url,
        data=json.dumps(metadata).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(video_path.stat().st_size),
            "X-Upload-Content-Type": "video/mp4",
        },
        method="POST",
    )
    with urllib.request.urlopen(init_req, timeout=30) as response:
        upload_url = response.headers.get("Location")
    if not upload_url:
        raise RuntimeError("YouTube hat keine Upload-URL zurückgegeben")

    content = video_path.read_bytes()
    put_req = urllib.request.Request(
        upload_url,
        data=content,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "video/mp4",
            "Content-Length": str(len(content)),
        },
        method="PUT",
    )
    with urllib.request.urlopen(put_req, timeout=180) as response:
        result = json_response(response)
    return str(result.get("id", ""))


def upload_to_tiktok(clip: Dict, token: str, direct_post: bool = False) -> str:
    video_path = Path(clip["output_file"])
    if not video_path.is_file():
        raise FileNotFoundError(f"Clip fehlt: {video_path}")

    size = video_path.stat().st_size
    if size <= 0:
        raise ValueError("Videodatei ist leer")

    body: Dict = {
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": size,
            "total_chunk_count": 1,
        }
    }
    if direct_post:
        body["post_info"] = {
            "title": str(clip.get("title", ""))[:150],
            "privacy_level": "SELF_ONLY",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        }

    endpoint = TIKTOK_DIRECT_API if direct_post else TIKTOK_INBOX_API
    init_req = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
        method="POST",
    )
    with urllib.request.urlopen(init_req, timeout=45) as response:
        init = json_response(response)

    if init.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok-Init fehlgeschlagen: {init['error']}")
    data = init.get("data", {})
    upload_url = data.get("upload_url")
    publish_id = data.get("publish_id", "")
    if not upload_url:
        raise RuntimeError("TikTok lieferte keine upload_url")

    content = video_path.read_bytes()
    put_req = urllib.request.Request(
        upload_url,
        data=content,
        headers={
            "Content-Type": "video/mp4",
            "Content-Length": str(size),
            "Content-Range": f"bytes 0-{size - 1}/{size}",
        },
        method="PUT",
    )
    with urllib.request.urlopen(put_req, timeout=180) as response:
        if response.status not in (200, 201, 206):
            raise RuntimeError(f"TikTok-Datei-Upload fehlgeschlagen: HTTP {response.status}")
    return str(publish_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lädt nur ausdrücklich freigegebene Clips hoch")
    parser.add_argument("-q", "--queue", type=Path, default=Path("pending_approval.json"))
    parser.add_argument("--platforms", nargs="+", choices=["youtube", "tiktok"], default=["youtube", "tiktok"])
    parser.add_argument("--yt-privacy", choices=["private", "unlisted", "public"], default="private")
    parser.add_argument("--tiktok-direct", action="store_true", help="Direkt posten; Standard ist Inbox/Draft")
    parser.add_argument("--upload", action="store_true", help="Ohne diese Flag läuft alles nur als Trockenlauf")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        data = load_queue(args.queue)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    clips = [c for c in data.get("clips", []) if c.get("approval_status") == "approved"]
    eligible = [
        c for c in clips
        if c.get("rights_confirmed") is True
        and c.get("clip_id")
    ]

    if not eligible:
        logger.info("Keine Clips mit approval_status=approved und rights_confirmed=true.")
        return 0

    yt_token = os.getenv("YOUTUBE_ACCESS_TOKEN", "")
    tt_token = os.getenv("TIKTOK_ACCESS_TOKEN", "")
    updates: Dict[str, Dict] = {}

    for clip in eligible:
        clip_id = str(clip["clip_id"])
        targets_done = set(clip.get("uploaded_targets", []))
        requested = set(args.platforms)
        logger.info("Freigegebener Clip: %s (%s)", clip_id, clip.get("title", "-"))

        if not args.upload:
            logger.info("[TROCKENLAUF] Würde hochladen auf: %s", sorted(requested - targets_done))
            continue

        if "youtube" in requested and "youtube" not in targets_done:
            if not yt_token:
                logger.warning("YOUTUBE_ACCESS_TOKEN fehlt – YouTube übersprungen")
            else:
                try:
                    video_id = upload_to_youtube(clip, yt_token, args.yt_privacy)
                    targets_done.add("youtube")
                    logger.info("YouTube OK: %s", video_id)
                except (OSError, ValueError, urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                    logger.error("YouTube fehlgeschlagen: %s", exc)

        if "tiktok" in requested and "tiktok" not in targets_done:
            if not tt_token:
                logger.warning("TIKTOK_ACCESS_TOKEN fehlt – TikTok übersprungen")
            else:
                try:
                    publish_id = upload_to_tiktok(clip, tt_token, args.tiktok_direct)
                    targets_done.add("tiktok")
                    logger.info("TikTok OK: %s", publish_id)
                except (OSError, ValueError, urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                    logger.error("TikTok fehlgeschlagen: %s", exc)

        updates[clip_id] = {
            "_live_approved": True,
            "uploaded_targets": sorted(targets_done),
            "requested_platforms": sorted(requested),
        }

    if updates:
        try:
            save_queue_merged(args.queue, updates)
        except (ValueError, OSError) as exc:
            logger.error("Warteschlange konnte nicht sicher aktualisiert werden: %s", exc)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
