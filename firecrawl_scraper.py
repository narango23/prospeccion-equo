"""Scraping de webs corporativas vía Firecrawl."""
from __future__ import annotations

from dataclasses import dataclass

import requests


@dataclass
class CompanySummary:
    summary: str = ""
    error: str | None = None

    @property
    def has_data(self) -> bool:
        return bool(self.summary.strip())


def fetch_company_summary(website: str, api_key: str, timeout: int = 60) -> CompanySummary:
    """Pide a Firecrawl un resumen del sitio de la empresa."""
    if not website or not website.strip():
        return CompanySummary(error="Website vacío")

    url = "https://api.firecrawl.dev/v2/scrape"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "url": website.strip(),
        "onlyMainContent": False,
        "maxAge": 172_800_000,  # 2 días — reusa el cache de Firecrawl
        "parsers": [],
        "formats": ["summary"],
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return CompanySummary(error=f"Firecrawl error: {exc}")

    payload = resp.json() if resp.content else {}
    summary = (payload.get("data") or {}).get("summary") or ""
    return CompanySummary(summary=summary)
