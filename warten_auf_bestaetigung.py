#!/usr/bin/env python3
"""Verwalte Clips in der Warteschlange und warte auf manuelle Zustimmung."""

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable


DEFAULT_QUEUE = Path("pending_approval.json")
VALID_STATUSES = {"pending_approval", "approved", "rejected", "uploaded"}


def load_queue(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Warteschlange nicht gefunden: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ungültige JSON-Warteschlange: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("clips", []), list):
        raise ValueError("Warteschlange muss ein Objekt mit einer 'clips'-Liste enthalten")
    return data


def save_queue(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def print_status(clips: Iterable[dict]) -> None:
    clips = list(clips)
    if not clips:
        print("Keine Clips in der Warteschlange.")
        return

    for clip in clips:
        claude = "Claude:JA" if clip.get("claude_recommended") else "Claude:NEIN"
        print(
            f"[{clip.get('clip_id', 'ohne-ID')}] "
            f"Status={clip.get('approval_status', 'pending_approval')} | {claude} | "
            f"Score={clip.get('score', '-')} | {clip.get('duration', '-')}s | "
            f"Titel: {clip.get('title', '-')}"
        )


def interactive_review(clips: Iterable[dict]) -> int:
    """Only an explicit human action changes pending clips."""
    changed = 0
    for clip in clips:
        if clip.get("approval_status") != "pending_approval":
            continue

        print("\n--------------------------------------------------")
        print(f"Clip-ID : {clip.get('clip_id', 'unbekannt')} ({clip.get('streamer', '-')})")
        print(
            f"Dauer   : {clip.get('duration', '-')}s "
            f"({clip.get('start', '-')}s - {clip.get('end', '-')}s) | "
            f"Score: {clip.get('score', '-')}"
        )
        print(f"Titel   : {clip.get('title', '-')}")
        print(f"Hook    : {clip.get('viral_hook', '-')}")
        print(f"Datei   : {clip.get('output_file', '-')}")

        while True:
            answer = input("Upload freigeben? [j]a / [n]ein / [s]kip: ").strip().lower()
            if answer in {"j", "ja", "y", "yes"}:
                clip["approval_status"] = "approved"
                changed += 1
                break
            if answer in {"n", "nein", "no"}:
                clip["approval_status"] = "rejected"
                changed += 1
                break
            if answer in {"s", "skip", ""}:
                break
            print("Bitte j, n oder s eingeben.")
    return changed


def set_clip_status(clips: Iterable[dict], clip_ids: Iterable[str], status: str) -> int:
    targets = set(clip_ids)
    changed = 0
    for clip in clips:
        if clip.get("clip_id") not in targets:
            continue
        if clip.get("approval_status") == "pending_approval":
            clip["approval_status"] = status
            changed += 1
    return changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Wartende Clips verwalten und nur manuell freigeben oder ablehnen"
    )
    parser.add_argument("-q", "--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--list", action="store_true", help="Alle Clips und ihren Status anzeigen")
    parser.add_argument("--approve", nargs="+", metavar="CLIP_ID", help="Bestimmte Clips manuell freigeben")
    parser.add_argument("--reject", nargs="+", metavar="CLIP_ID", help="Bestimmte Clips manuell ablehnen")
    parser.add_argument("--interactive", action="store_true", help="Interaktiv Clip für Clip prüfen")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        data = load_queue(args.queue)
    except (FileNotFoundError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    clips = data.setdefault("clips", [])

    if args.list:
        print_status(clips)
        return 0

    changed = 0
    if args.approve:
        changed += set_clip_status(clips, args.approve, "approved")
    if args.reject:
        changed += set_clip_status(clips, args.reject, "rejected")
    if args.interactive:
        changed += interactive_review(clips)

    # Validate all statuses after updates, fail closed for unknown values.
    for clip in clips:
        status = clip.get("approval_status", "pending_approval")
        if status not in VALID_STATUSES:
            print(f"Ungültiger Status in Clip {clip.get('clip_id', 'unbekannt')}: {status}", file=sys.stderr)
            return 2

    if changed:
        save_queue(args.queue, data)

    print("Aktualisierter Status:")
    print_status(clips)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
