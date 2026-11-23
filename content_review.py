"""Claude preflight review. This is a content-safety check, not a rights determination."""
import json
import os
import urllib.request
from typing import Any, Dict


def review_with_claude(title: str, description: str, transcript: str, source_url: str) -> Dict[str, Any]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY fehlt; Upload wird aus Sicherheitsgründen abgebrochen")
    payload = {
        "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
        "max_tokens": 500,
        "system": (
            "Prüfe Clip-Metadaten und Transkript vor Veröffentlichung auf erkennbare Risiken: "
            "Belästigung, Hass, private/personenbezogene Daten, gefährliche Handlungen, irreführende "
            "Behauptungen und mögliche sensible Inhalte. Du kannst keine Urheberrechte oder Erlaubnisse "
            "feststellen. Antworte nur als JSON-Objekt: {\"approved\": boolean, \"reasons\": [string], "
            "\"notes\": [string]}. Bei Unsicherheit approved=false."
        ),
        "messages": [{"role": "user", "content": json.dumps({
            "title": title, "description": description, "transcript": transcript[:12000], "source_url": source_url,
        }, ensure_ascii=False)}],
    }
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=json.dumps(payload).encode("utf-8"),
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        result = json.loads(response.read().decode("utf-8"))
    text = "\n".join(block.get("text", "") for block in result.get("content", []) if block.get("type") == "text").strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    review = json.loads(text)
    if not isinstance(review, dict) or not isinstance(review.get("approved"), bool):
        raise RuntimeError("Claude lieferte kein gültiges Review; Upload wird abgebrochen")
    return review
