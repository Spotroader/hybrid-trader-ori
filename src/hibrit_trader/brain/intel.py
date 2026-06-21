"""Ücretsiz dış intel — korku/açgözlülük, haber özeti."""

from __future__ import annotations

import httpx

FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"


def fetch_fear_greed() -> dict | None:
    try:
        with httpx.Client() as client:
            r = client.get(FEAR_GREED_URL, timeout=10)
            r.raise_for_status()
            data = r.json().get("data", [])
            if not data:
                return None
            row = data[0]
            return {
                "value": int(row["value"]),
                "label": row.get("value_classification", ""),
                "source": "alternative.me",
            }
    except Exception:
        return None
