"""Poll explicitly authorized Twitch channels and record streams while live.

This records only entries in channels.txt marked rights_confirmed=true. It does not
bypass subscriber restrictions or platform access controls.
"""
import argparse
import json
import logging
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("TwitchWatcher")


@dataclass(frozen=True)
class TwitchChannel:
    login: str
    rights_confirmed: bool


def read_twitch_channels(path: Path) -> List[TwitchChannel]:
    """Parse lines formatted as twitch|login|rights_confirmed=true; fail closed."""
    channels: List[TwitchChannel] = []
    if not path.is_file():
        return channels
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 3 or parts[0].lower() != "twitch":
            continue
        login = parts[1].lower()
        if not re.fullmatch(r"[a-z0-9_]{1,25}", login):
            log.warning("Ungültiger Twitch-Login übersprungen")
            continue
        rights = parts[2].lower() == "rights_confirmed=true"
        if rights:
            channels.append(TwitchChannel(login, True))
        else:
            log.warning("Twitch-Kanal ohne bestätigte Rechte übersprungen: %s", login)
    return channels


def twitch_app_token(client_id: str, client_secret: str) -> str:
    query = urllib.parse.urlencode({"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"})
    request = urllib.request.Request(f"https://id.twitch.tv/oauth2/token?{query}", method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    token = data.get("access_token")
    if not token:
        raise RuntimeError("Twitch hat kein App-Access-Token zurückgegeben")
    return token


def live_streams(client_id: str, token: str, logins: List[str]) -> Dict[str, dict]:
    live: Dict[str, dict] = {}
    for login in logins:
        query = urllib.parse.urlencode({"user_login": login})
        request = urllib.request.Request(
            f"https://api.twitch.tv/helix/streams?{query}",
            headers={"Client-Id": client_id, "Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        for stream in data.get("data", []):
            live[login] = stream
    return live


def record_stream(login: str, out_dir: Path, max_seconds: int = 0) -> Optional[Path]:
    """Record an authorized public live stream via yt-dlp; 0 means until it ends."""
    out_dir.mkdir(parents=True, exist_ok=True)
    template = out_dir / f"{login}_%(epoch)s.%(ext)s"
    command = ["yt-dlp", "--no-part", "--hls-use-mpegts", "--output", str(template), f"https://www.twitch.tv/{login}"]
    if max_seconds > 0:
        command.extend(["--external-downloader", "ffmpeg", "--external-downloader-args", f"ffmpeg_i:-t {max_seconds}"])
    log.info("Aufzeichnung startet für freigegebenen Live-Kanal %s", login)
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("yt-dlp ist nicht installiert oder nicht im PATH") from exc
    except subprocess.CalledProcessError as exc:
        log.error("Aufzeichnung für %s endete mit Fehlercode %s", login, exc.returncode)
        return None
    matches = sorted(out_dir.glob(f"{login}_*"), key=lambda file: file.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Überwacht freigegebene Twitch-Kanäle und zeichnet Live-Streams auf")
    parser.add_argument("--channels", type=Path, default=Path("channels.txt"))
    parser.add_argument("--output", type=Path, default=Path("recordings"))
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--max-seconds", type=int, default=0, help="0 = bis zum Stream-Ende aufzeichnen")
    parser.add_argument("--once", action="store_true", help="Einmal prüfen und ggf. gestartete Aufzeichnungen ausführen")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.poll_seconds < 10 or args.max_seconds < 0:
        log.error("Poll-Intervall muss mindestens 10 Sekunden sein; max-seconds darf nicht negativ sein")
        return 2
    channels = read_twitch_channels(args.channels)
    if not channels:
        log.error("Keine Twitch-Kanäle mit rights_confirmed=true in %s", args.channels)
        return 2
    client_id, secret = os.getenv("TWITCH_CLIENT_ID"), os.getenv("TWITCH_CLIENT_SECRET")
    if not client_id or not secret:
        log.error("TWITCH_CLIENT_ID und TWITCH_CLIENT_SECRET müssen gesetzt sein")
        return 2
    try:
        token = twitch_app_token(client_id, secret)
        recorded = set()
        while True:
            live = live_streams(client_id, token, [channel.login for channel in channels])
            for channel in channels:
                if channel.login in live and channel.login not in recorded:
                    log.info("Freigegebener Kanal ist live: %s", channel.login)
                    path = record_stream(channel.login, args.output, args.max_seconds)
                    if path:
                        log.info("Aufzeichnung gespeichert: %s", path)
                    recorded.add(channel.login)
                elif channel.login not in live:
                    recorded.discard(channel.login)
            if args.once:
                return 0
            time.sleep(args.poll_seconds)
    except (urllib.error.URLError, TimeoutError, ValueError, RuntimeError) as exc:
        log.error("Twitch-Monitor abgebrochen: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
