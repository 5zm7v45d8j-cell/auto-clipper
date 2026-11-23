#!/usr/bin/env python3
"""Guided, fail-safe daily workflow for auto-clipper.

This wrapper never performs a live upload unless the explicit upload mode
is selected after human review. It uses only existing local scripts.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(command: list[str]) -> int:
    completed = subprocess.run(command, check=False)
    return completed.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tagesablauf für Auto-Clipper")
    sub = parser.add_subparsers(dest="mode", required=True)

    generate = sub.add_parser("generieren", help="Clips analysieren und wartende Queue erstellen")
    generate.add_argument("input_video", type=Path)
    generate.add_argument("--streamer", default="Streamer")
    generate.add_argument("--topic", default="GTA 6")
    generate.add_argument("--queue", type=Path, default=Path("pending_approval.json"))
    generate.add_argument("--min-len", type=float, default=30.0)
    generate.add_argument("--max-len", type=float, default=90.0)

    sub.add_parser("pruefen", help="Interaktive Rechte- und Clipprüfung")
    sub.add_parser("status", help="Warteschlangenstatus anzeigen")
    sub.add_parser("trockenlauf", help="Uploads nur simulieren")

    upload = sub.add_parser("hochladen", help="Nach menschlicher Freigabe hochladen")
    upload.add_argument("--platforms", nargs="+", choices=["youtube", "tiktok"], default=["youtube", "tiktok"])
    upload.add_argument("--yt-privacy", choices=["private", "unlisted", "public"], default="private")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.mode == "generieren":
        if not args.input_video.is_file():
            print(f"Eingabedatei fehlt: {args.input_video}", file=sys.stderr)
            return 2
        command = [
            sys.executable, "auto_clipper.py", str(args.input_video),
            "--streamer", args.streamer, "--topic", args.topic,
            "--queue-file", str(args.queue),
            "--min-len", str(args.min_len), "--max-len", str(args.max_len),
        ]
        return run(command)

    if args.mode == "pruefen":
        return run([sys.executable, "warten_auf_bestaetigung.py", "--interactive"])

    if args.mode == "status":
        return run([sys.executable, "warten_auf_bestaetigung.py", "--list"])

    if args.mode == "trockenlauf":
        return run([sys.executable, "social_uploader.py"])

    if args.mode == "hochladen":
        command = [
            sys.executable, "social_uploader.py", "--upload",
            "--platforms", *args.platforms,
            "--yt-privacy", args.yt_privacy,
        ]
        print("ECHTER UPLOAD wird gestartet. Nur approved+rights_confirmed=true Clips werden verarbeitet.")
        return run(command)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
