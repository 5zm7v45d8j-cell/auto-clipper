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
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def print_status(clips: Iterable[dict]) -> None:
    clips = list(clips)
    if not clips:
        print("Keine Clips in der Warteschlange.")
        return
    for clip in clips:
        rights = "RECHTE:JA" if clip.get("rights_confirmed") is True else "RECHTE:NEIN"
        print(
            f"[{clip.get('clip_id', 'ohne-ID')}] "
            f"Status={clip.get('approval_status', 'pending_approval')} | {rights} | "
            f"Score={clip.get('score', '-')} | {clip.get('duration', '-')}s | "
            f"Titel: {clip.get('title', '-')}"
        )


def confirm_rights(clips: Iterable[dict], clip_ids: Iterable[str]) -> int:
    targets = set(clip_ids)
    changed = 0
    for clip in clips:
        if clip.get("clip_id") not in targets:
            continue
        if clip.get("approval_status") not in {"pending_approval", "approved"}:
            continue
        answer = input("Hast du für diesen Clip Upload-/Bearbeitungsrechte geprüft und bestätigt? [ja/nein]: ").strip().lower()
        if answer in {"ja", "j", "yes", "y"}:
            clip["rights_confirmed"] = True
            changed += 1
        elif answer in {"nein", "n", "no"}:
            clip["rights_confirmed"] = False
            changed += 1
    return changed


def interactive_review(clips: Iterable[dict]) -> int:
    changed = 0
    for clip in clips:
        if clip.get("approval_status") != "pending_approval":
            continue
        print("\n--------------------------------------------------")
        print(f"Clip-ID : {clip.get('clip_id', 'unbekannt')} ({clip.get('streamer', '-')})")
        print(f"Titel   : {clip.get('title', '-')}")
        print(f"Datei   : {clip.get('output_file', '-')}")

        rights = input("Rechte für Bearbeitung und Upload ausdrücklich geprüft? [j]a/[n]ein/[s]kip: ").strip().lower()
        if rights in {"j", "ja", "y", "yes"}:
            clip["rights_confirmed"] = True
            changed += 1
        elif rights in {"n", "nein", "no"}:
            clip["rights_confirmed"] = False
            changed += 1
        else:
            continue

        if clip.get("rights_confirmed") is not True:
            continue

        while True:
            answer = input("Upload freigeben? [j]a/[n]ein/[s]kip: ").strip().lower()
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
        if clip.get("approval_status") != "pending_approval":
            continue
        if status == "approved" and clip.get("rights_confirmed") is not True:
            continue
        clip["approval_status"] = status
        changed += 1
    return changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wartende Clips verwalten")
    parser.add_argument("-q", "--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--approve", nargs="+", metavar="CLIP_ID")
    parser.add_argument("--reject", nargs="+", metavar="CLIP_ID")
    parser.add_argument("--confirm-rights", nargs="+", metavar="CLIP_ID")
    parser.add_argument("--interactive", action="store_true")
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
    if args.confirm_rights:
        changed += confirm_rights(clips, args.confirm_rights)
    if args.approve:
        changed += set_clip_status(clips, args.approve, "approved")
    if args.reject:
        changed += set_clip_status(clips, args.reject, "rejected")
    if args.interactive:
        changed += interactive_review(clips)

    for clip in clips:
        if clip.get("approval_status", "pending_approval") not in VALID_STATUSES:
            print(f"Ungültiger Status in Clip {clip.get('clip_id', 'unbekannt')}", file=sys.stderr)
            return 2
        if clip.get("approval_status") == "approved" and clip.get("rights_confirmed") is not True:
            print(f"Clip {clip.get('clip_id', 'unbekannt')} approved, aber Rechte nicht bestätigt", file=sys.stderr)
            clip["approval_status"] = "pending_approval"
            changed += 1

    if changed:
        save_queue(args.queue, data)
    print_status(clips)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
