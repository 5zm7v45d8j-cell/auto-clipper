import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ClipPipeline")


def approved_channels(path: Path) -> List[str]:
    """Return only explicitly approved YouTube channel URLs."""
    if not path.exists():
        return []

    channels: List[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|approved=true" not in line:
            logger.warning("Kanal ohne Freigabe übersprungen: %s", line)
            continue
        url = line.split("|", 1)[0].strip()
        if url:
            channels.append(url)
    return channels


def search_via_youtube_api(query: str, max_results: int = 10) -> List[dict]:
    """Optional YouTube-Data-API search. Returns [] if no API key exists."""
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        logger.info("YOUTUBE_API_KEY nicht gesetzt; verwende yt-dlp-Kanalauflistung.")
        return []

    try:
        from googleapiclient.discovery import build
    except ImportError:
        logger.warning("google-api-python-client ist nicht installiert.")
        return []

    service = build("youtube", "v3", developerKey=api_key)
    response = (
        service.search()
        .list(q=query, type="video", part="snippet", maxResults=max_results, order="date")
        .execute()
    )
    return [
        {
            "id": item["id"]["videoId"],
            "title": item["snippet"].get("title", ""),
            "published": item["snippet"].get("publishedAt", ""),
            "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}",
        }
        for item in response.get("items", [])
    ]


def search_via_ytdlp(channel_url: str, max_results: int) -> List[dict]:
    """Get recent videos from an approved channel using yt-dlp."""
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--playlist-end", str(max_results),
        "--print", "%(id)s\t%(title)s\t%(duration)s\t%(webpage_url)s",
        channel_url.rstrip("/") + "/videos",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    results: List[dict] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t", 3)
        if len(parts) == 4:
            video_id, title, duration, url = parts
            results.append({"id": video_id, "title": title, "duration": duration, "url": url})
    return results


def download_video(url: str, output_dir: Path) -> Optional[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    template = str(output_dir / "%(title)s-%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--format", "bv*+ba/b",
        "--merge-output-format", "mp4",
        "--output", template,
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.error("Download fehlgeschlagen: %s", proc.stderr[-1000:])
        return None

    candidates = sorted(output_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def anthropic_rank_manifest(manifest_path: Path, title: str) -> Optional[List[int]]:
    """Ask Anthropic to rank local clip candidates; no public API calls to retrieve sources."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.info("ANTHROPIC_API_KEY nicht gesetzt; verwende lokale Signalauswahl.")
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic-Paket ist nicht installiert.")
        return None

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    prompt = (
        "Bewerte diese bereits lokal erzeugten Highlight-Kandidaten für virale 30- bis 90-Sekunden-Clips. "
        "Antworte ausschließlich mit einem JSON-Array von Clip-Indices, sortiert nach viraler Wahrscheinlichkeit. "
        "Berücksichtige: starke Emotion, Überraschung, Gaming-Moment, Diskussion oder Szenewechsel. "
        "Verwerfe Kandidaten, die kein klarer eigenständiger Moment sind.\n"
        f"Titel: {title}\n"
        f"Manifest: {json.dumps(data, ensure_ascii=False)}"
    )

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    try:
        indices = json.loads(text)
        return [int(i) for i in indices if isinstance(i, (int, float))]
    except json.JSONDecodeError:
        logger.warning("Anthropic-Antwort war kein JSON-Array: %s", text)
        return None


def run_clipper(video: Path, clips_dir: Path, dry_run: bool) -> Optional[Path]:
    cmd = [
        "python", "auto_clipper.py", str(video),
        "-o", str(clips_dir),
        "--min-len", "30",
        "--max-len", "90",
    ]
    if dry_run:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        return None
    manifest = clips_dir / "manifest.json"
    return manifest if manifest.exists() else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recherche und Clip-Erstellung aus freigegebenen YouTube-Kanälen")
    parser.add_argument("--once", action="store_true", help="Alle freigegebenen Kanäle einmal verarbeiten")
    parser.add_argument("--channels", type=Path, default=Path("channels.txt"), help="Allowlist-Datei")
    parser.add_argument("--downloads", type=Path, default=Path("downloads"), help="Download-Zielordner")
    parser.add_argument("--output", type=Path, default=Path("clips_out"), help="Clip-Zielordner")
    parser.add_argument("--max-videos", type=int, default=3, help="Neueste Videos pro Kanal")
    parser.add_argument("--clips", type=int, default=6, help="Gewünschte Anzahl Clips")
    parser.add_argument("--min-score", type=float, default=0.62, help="Lokale Score-Schwelle")
    parser.add_argument("--dry-run", action="store_true", help="Nur herunterladen und analysieren; keine neuen Videoclips rendern")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    channels = approved_channels(args.channels)
    if not channels:
        logger.error("Keine freigegebenen Kanäle gefunden. Nutze URL|approved=true in %s", args.channels)
        return 2

    if not args.once:
        logger.error("Aktuell wird nur --once unterstützt.")
        return 2

    for channel in channels:
        logger.info("Verarbeite freigegebenen Kanal: %s", channel)
        api_results = search_via_youtube_api(channel.rstrip("/").rsplit("/", 1)[-1].lstrip("@"), args.max_videos)
        videos = api_results or search_via_ytdlp(channel, args.max_videos)

        for video in videos:
            downloaded = download_video(video["url"], args.downloads)
            if downloaded is None:
                continue

            clips_dir = args.output / downloaded.stem
            manifest = run_clipper(downloaded, clips_dir, args.dry_run)
            if manifest:
                ranked = anthropic_rank_manifest(manifest, video.get("title", downloaded.stem))
                logger.info("Manifest: %s | Anthropic-Ranking: %s", manifest, ranked)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
