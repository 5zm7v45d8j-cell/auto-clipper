#!/usr/bin/env python3
"""
Unverbindliche Rechte-Checkliste für Stream-Clips nach deutschen Rechtsgrundlagen.

Diese Datenbasis dient als Orientierung und ersetzt keine Lizenzprüfung oder
Rechtsberatung. Sie erteilt keine Veröffentlichungsgenehmigung.
"""

RECHTS_CHECKLISTE: dict[str, dict[str, object]] = {
    "1": {
        "titel": "1. Ausdrückliche Erlaubnis / Lizenz",
        "kurz": "Nachweisbare schriftliche Freigabe vom Rechteinhaber oder Management.",
        "fragen": [
            "Liegt eine nachweisbare Erlaubnis des Rechteinhabers vor?",
            "Deckt sie Bearbeitung und das Erstellen von Clips ausdrücklich ab?",
            "Deckt sie alle geplanten Plattformen wie YouTube und TikTok ab?",
            "Sind Laufzeit, Gebiet, Monetarisierung und weitere Auflagen geklärt?",
            "Sind Drittinhalte wie Musik, Sport oder fremde Videos ebenfalls abgedeckt?",
        ],
        "quellenhinweis_empfohlen": False,
    },
    "2": {
        "titel": "2. Plattform-eigene Remix- oder Stitch-Funktion",
        "kurz": "Prüfpunkte für eine native Funktion innerhalb derselben Plattform.",
        "fragen": [
            "Hat der Original-Creator die Funktion für genau dieses Video freigegeben?",
            "Bleibt das Ergebnis in derselben App?",
            "Wird kein fremdes Video heruntergeladen und woanders erneut hochgeladen?",
            "Wurden aktuelle Plattformbedingungen und mögliche Einschränkungen geprüft?",
            "Sind Drittinhalte und weitere Rechte geklärt?",
        ],
        "quellenhinweis_empfohlen": False,
    },
    "3": {
        "titel": "3. Zitatrecht – § 51 UrhG",
        "kurz": "Nur eine mögliche Einzelfallprüfung bei eigener inhaltlicher Auseinandersetzung.",
        "fragen": [
            "Dient der Ausschnitt einer eigenen Analyse, Kritik oder Kommentierung?",
            "Steht die eigene Einordnung klar im Vordergrund?",
            "Ist der fremde Ausschnitt auf das erforderliche Maß beschränkt?",
            "Wird das fremde Werk nicht als Ersatz für das Original angeboten?",
            "Wurden Drittinhalte und Persönlichkeitsrechte gesondert geprüft?",
        ],
        "quellenhinweis_empfohlen": True,
    },
    "4": {
        "titel": "4. Karikatur, Parodie oder Pastiche – § 51a UrhG",
        "kurz": "Nur eine mögliche Einzelfallprüfung bei erkennbarer eigener künstlerischer Leistung.",
        "fragen": [
            "Ist eine eigenständige humoristische oder künstlerische Transformation erkennbar?",
            "Geht es über simples Spiegeln, Zuschneiden oder Untertiteln hinaus?",
            "Ist die fremde Nutzung für die eigene Bearbeitung erforderlich und begrenzt?",
            "Sind keine weiteren geschützten Drittinhalte ohne Rechte enthalten?",
            "Wurde der konkrete Einzelfall gegebenenfalls fachlich geprüft?",
        ],
        "quellenhinweis_empfohlen": True,
    },
}


def print_rechts_checkliste() -> None:
    """Zeigt die unverbindliche Checkliste übersichtlich im Terminal."""
    print("=" * 74)
    print("  UNVERBINDLICHE RECHTS-CHECKLISTE FÜR STREAM-CLIPS")
    print("=" * 74)
    print("Kein Punkt oder Ja/Nein-Ergebnis ist eine Rechtsfreigabe oder Rechtsberatung.")
    print("Quellenangaben ersetzen keine Nutzungsrechte und sind kein Lizenznachweis.")
    for eintrag in RECHTS_CHECKLISTE.values():
        print(f"\n{eintrag['titel']}")
        print(f"Hinweis: {eintrag['kurz']}")
        for punkt in eintrag["fragen"]:
            print(f"  [ ] {punkt}")
        if eintrag["quellenhinweis_empfohlen"]:
            print("  [ ] Quellenhinweis als zusätzlichen Kontext prüfen lassen")
    print("\nBei Unsicherheit: Veröffentlichung stoppen und qualifizierte Rechtsberatung einholen.")


if __name__ == "__main__":
    print_rechts_checkliste()
