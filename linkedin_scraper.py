"""Extracción de perfil + posts de LinkedIn vía RapidAPI.

Notas sobre el payload real (verificadas contra el JSON de referencia n8n):
- `postedDate` viene en formato "2026-03-22 06:58:54.538 +0000 UTC" — con
  milisegundos opcionales, offset y sufijo " UTC". `datetime.fromisoformat`
  no lo parsea; usamos un parser tolerante.
- El perfil incluye URLs de imágenes (profilePicture, profilePictures, logos
  de educations y position) que no aportan al LLM y cuestan tokens.
- Los posts incluyen arrays de video, thumbnails y poster URLs igualmente
  inútiles. Los limpiamos antes de pasar al LLM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

LINKEDIN_URL_RE = re.compile(r"https?://(?:www\.)?linkedin\.com/in/([^/?#]+)/?", re.IGNORECASE)

# Campos basura que strippeamos del profile y los posts para no inflar tokens.
PROFILE_NOISE_KEYS = {
    "profilePicture",
    "profilePictures",
    "backgroundImage",
    "supportedLocales",
    "multiLocaleFirstName",
    "multiLocaleLastName",
    "multiLocaleHeadline",
}
POST_NOISE_KEYS = {
    "video",
    "thumbnails",
    "poster",
    "image",
    "images",
    "document",
    "celebration",
    "poll",
    "entity",
}


@dataclass
class LinkedInData:
    profile: dict[str, Any] = field(default_factory=dict)
    posts: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def has_data(self) -> bool:
        return bool(self.profile) or bool(self.posts)


def _extract_username(url: str) -> str | None:
    if not url:
        return None
    m = LINKEDIN_URL_RE.search(url.strip())
    return m.group(1) if m else None


def _parse_posted_date(raw: str) -> datetime | None:
    """Parser tolerante para los formatos que produce RapidAPI.

    Acepta:
      - "2026-03-22 06:58:54.538 +0000 UTC"
      - "2026-03-22 06:58:54 +0000 UTC"
      - "2026-03-22 06:58:54.538 +0000"
      - "2026-03-22 06:58:54"
    Devuelve datetime UTC-aware (asume UTC si no hay offset).
    """
    if not raw:
        return None
    s = raw.strip().replace(" UTC", "").strip()
    formats = (
        "%Y-%m-%d %H:%M:%S.%f %z",
        "%Y-%m-%d %H:%M:%S %z",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    )
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _filter_recent_posts(posts: list[dict[str, Any]], months: int = 6, limit: int = 10) -> list[dict[str, Any]]:
    """Conserva posts de los últimos N meses, hasta `limit`. Limpia ruido."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30 * months)
    recent: list[dict[str, Any]] = []
    for post in posts or []:
        posted = _parse_posted_date(post.get("postedDate") or "")
        if posted is None:
            continue
        if posted >= cutoff:
            recent.append(_clean_post(post))
        if len(recent) >= limit:
            break
    return recent


def _clean_post(post: dict[str, Any]) -> dict[str, Any]:
    """Quita arrays de URL pesadas de un post y de su resharedPost si existe."""
    cleaned = {k: v for k, v in post.items() if k not in POST_NOISE_KEYS}
    if isinstance(cleaned.get("resharedPost"), dict):
        cleaned["resharedPost"] = {
            k: v for k, v in cleaned["resharedPost"].items() if k not in POST_NOISE_KEYS
        }
    return cleaned


def _clean_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Quita imágenes y locales redundantes; condensa positions y educations."""
    if not profile:
        return {}
    cleaned: dict[str, Any] = {
        k: v for k, v in profile.items() if k not in PROFILE_NOISE_KEYS
    }

    # positions: máximo 5, sin logos
    positions = cleaned.get("position") or []
    cleaned["position"] = [
        {k: v for k, v in p.items() if k not in {"companyLogo", "multiLocaleTitle", "multiLocaleCompanyName"}}
        for p in positions[:5]
    ]

    # educations: máximo 3, sin logos
    educations = cleaned.get("educations") or []
    cleaned["educations"] = [
        {k: v for k, v in e.items() if k not in {"logo", "multiLocaleDegreeName", "multiLocaleSchoolName"}}
        for e in educations[:3]
    ]

    return cleaned


def fetch_linkedin(linkedin_url: str, rapidapi_key: str, rapidapi_host: str, timeout: int = 45) -> LinkedInData:
    """Llama a RapidAPI para perfil + posts. Robusto a fallos parciales."""
    username = _extract_username(linkedin_url)
    if not username:
        return LinkedInData(error=f"URL de LinkedIn inválida: {linkedin_url!r}")

    url = f"https://{rapidapi_host}/profile-data-connection-count-posts"
    headers = {
        "x-rapidapi-host": rapidapi_host,
        "x-rapidapi-key": rapidapi_key,
    }
    params = {"username": username}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return LinkedInData(error=f"RapidAPI error: {exc}")

    payload = resp.json() if resp.content else {}
    profile = _clean_profile(payload.get("data") or {})
    raw_posts = payload.get("posts") or []
    posts = _filter_recent_posts(raw_posts, months=6, limit=10)

    return LinkedInData(profile=profile, posts=posts)
