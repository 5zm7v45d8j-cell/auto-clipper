#!/usr/bin/env python3
"""Unverbindliche Rechte-Checkliste und Quellenhinweis-Entwurf.

Dies ist keine Rechtsberatung, stellt keine Nutzungsrechte fest und erteilt
keine Freigabe zur Veröffentlichung. Quellenangabe allein schafft keine Rechte.
"""
from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from urllib.parse import urlparse

DISCLAIMER = (
    "HINWEIS: Diese Checkliste ist unverbindlich und keine Rechtsberatung. "
    "Sie kann weder Rechte noch die Anwendbarkeit gesetzlicher Schranken verbindlich feststellen."
)


def copy_to_clipboard(text: str) -> bool:
    """Kopiert Text, sofern ein unterstütztes Clipboard-Programm verfügbar ist."""
    system = platform.system()
    commands: list[tuple[list[str], str]] = []
    if system == "Windows":
        commands = [(["clip"], "utf-16le")]
    elif system == "Darwin":
        commands = [(["pbcopy"], "utf-8")]
    elif system == "Linux":
        commands = [
            (["xclip", "-selection", "clipboard"], "utf-8"),
            (["xsel", "--clipboard", "--input"], "utf-8"),
        ]

    for command, encoding in commands:
        try:
            subprocess.run(command, input=text.encode(encoding), check=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            continue
    return False


def ask_yes_no(prompt: str) -> bool:
    """Fragt bis zur Ja-/Nein-Antwort; EOF wird sicher als Nein behandelt."""
    while True:
        try:
            answer = input(f"{prompt} (ja/nein): ").strip().casefold()
        except EOFError:
            print("\nKeine Eingabe erhalten; Check wird abgebrochen.")
            return False
        if answer in {"ja", "j", "yes", "y"}:
            return True
        if answer in {"nein", "n", "no", "n"}:
            return False
        print("Bitte antworte mit 'ja' oder 'nein'.")


def ask_non_empty(prompt: str) -> str:
    while True:
        try:
            value = input(f"{prompt}: ").strip()
        except EOFError as exc:
            raise ValueError("Eingabe abgebrochen.") from exc
        if value:
            return value
        print("Dieses Feld darf nicht leer sein.")


def is_valid_http_url(value: str) -> bool:
    """Prüft URL-Grundform; Echtheit oder Rechte werden dadurch nicht bestätigt."""
    try:
        parsed = urlparse(value.strip())
        # Accessing .port also validates malformed port numbers.
        _ = parsed.port
        return (
            parsed.scheme.lower() in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
        )
    except (ValueError, AttributeError):
        return False


def generate_source_notice(creator: str, title: str, url: str, legal_basis: str = "") -> str:
    """Erstellt einen Quellenhinweis-Entwurf, keine verbindliche Pflichtangabe."""
    creator, title, url = creator.strip(), title.strip(), url.strip()
    if not creator or not title:
        raise ValueError("Name/Kanal und Titel müssen angegeben werden.")
    if not is_valid_http_url(url):
        raise ValueError("Bitte eine gültige http(s)-URL ohne Zugangsdaten angeben.")
    lines = [
        "Quelle / Original",
        f"Urheber/Kanal: {creator}",
        f"Titel: {title}",
        f"Link: {url}",
    ]
    if legal_basis.strip():
        lines.append(f"Angegebener Nutzungskontext (nicht rechtlich geprüft): {legal_basis.strip()}")
    lines.append("Hinweis: Quellenangabe allein erteilt keine Nutzungsrechte.")
    return "\n".join(lines)


def print_source_notice() -> None:
    print("\n--- Quellenangabe (Entwurf) ---")
    creator = ask_non_empty("Name des Streamers/Kanals")
    title = ask_non_empty("Titel des Originalvideos/Streams")
    while True:
        url = ask_non_empty("Direkter Link zum Original")
        if is_valid_http_url(url):
            break
        print("Bitte eine gültige http(s)-URL eingeben.")
    notice = generate_source_notice(creator, title, url)
    print("\n" + notice)
    if copy_to_clipboard(notice):
        print("\nQuellenangabe wurde in die Zwischenablage kopiert.")
    else:
        print("\nClipboard nicht verfügbar; Text bitte manuell kopieren.")


def run_check() -> int:
    print("=" * 68)
    print("Unverbindliche Urheberrechts- & Quellen-Checkliste für Stream-Clips")
    print("=" * 68)
    print(DISCLAIMER + "\n")

    if ask_yes_no("Enthält der Clip möglicherweise fremde Musik, Sport, Film-/TV-Material oder andere Drittinhalte?"):
        print("\nSTOPP: Drittrechte können betroffen sein. Vor Veröffentlichung Rechte klären.")
        return 2
    if ask_yes_no("Enthält der Clip sensible/private Informationen oder möglicherweise rechtsverletzende Bloßstellung/Beleidigung?"):
        print("\nSTOPP: Datenschutz-, Persönlichkeits- oder sonstige Rechtsrisiken prüfen lassen.")
        return 2

    print("\nWähle den behaupteten Nutzungsweg (keine Antwort ist eine Rechtsfreigabe):")
    print("  [1] Schriftliche Lizenz/Erlaubnis")
    print("  [2] Plattforminterne Remix-/Duett-/Stitch-Funktion")
    print("  [3] Zitat (§ 51 UrhG kann im Einzelfall relevant sein)")
    print("  [4] Karikatur, Parodie oder Pastiche (§ 51a UrhG kann im Einzelfall relevant sein)")
    print("  [0] Kein geklärter Nutzungsweg")
    try:
        choice = input("Auswahl (0–4): ").strip()
    except EOFError:
        print("\nKeine Eingabe erhalten; keine Freigabe.")
        return 2

    if choice == "1":
        checks = [
            ("Liegt eine nachweisbare Erlaubnis des Rechteinhabers vor?", "Lizenznachweis"),
            ("Deckt sie Bearbeitung/Clipping ausdrücklich ab?", "Bearbeitungsumfang"),
            ("Deckt sie jede Zielplattform (z. B. YouTube und TikTok) ab?", "Plattformen"),
            ("Sind Laufzeit, Gebiet und gegebenenfalls Monetarisierung geklärt?", "Nutzungsumfang"),
            ("Sind Drittmaterialien und weitere erforderliche Rechte geklärt?", "Drittrechte"),
        ]
        failed = [label for question, label in checks if not ask_yes_no(question)]
        if failed:
            print("\nNICHT GEKLÄRT: " + ", ".join(failed) + ". Bis zur Klärung nicht veröffentlichen.")
            return 2
        print("\nCHECKLISTE VORLÄUFIG ERFÜLLT. Keine Rechtsfreigabe; Lizenztext und tatsächliche Rechte prüfen.")
        return 0

    if choice == "2":
        same_platform = ask_yes_no("Bleibt der Inhalt in der Plattform, deren native Remix-Funktion verwendet wird?")
        terms_checked = ask_yes_no("Hast du aktuelle Bedingungen und Einschränkungen dieser Funktion geprüft?")
        if same_platform and terms_checked:
            print("\nPlattformbedingungen selbst prüfen. Das erlaubt nicht automatisch plattformübergreifenden Download/Reupload.")
            return 3
        print("\nNICHT GEKLÄRT: Bedingungen prüfen; kein plattformübergreifender Reupload ohne passende Rechte.")
        return 2

    if choice in {"3", "4"}:
        own_work = ask_yes_no("Enthält der Clip eine eigenständige, erkennbare Auseinandersetzung/eigene schöpferische Leistung?")
        necessary = ask_yes_no("Ist das fremde Material für diesen Zweck erforderlich und auf das nötige Maß begrenzt?")
        if not (own_work and necessary):
            print("\nNICHT GEKLÄRT: Die Antworten reichen nicht für eine automatische Bewertung. Fachlich prüfen lassen.")
            return 2
        print("\nRECHTLICHE EINZELFALLPRÜFUNG ERFORDERLICH. Keine automatische Upload-Freigabe.")
        if ask_yes_no("Zusätzlich einen Quellenhinweis-Entwurf erstellen? (Der Hinweis schafft keine Rechte)"):
            print_source_notice()
        return 3

    if choice == "0":
        print("\nSTOPP: Kein Nutzungsweg angegeben. Ohne geklärte Rechte nicht veröffentlichen.")
    else:
        print("Ungültige Auswahl; keine Freigabe.")
    return 2


def main() -> int:
    argparse.ArgumentParser(description="Unverbindliche Rechte-Checkliste und Quellenhinweis-Entwurf").parse_args()
    try:
        return run_check()
    except (ValueError, OSError) as exc:
        print(f"Abgebrochen: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
