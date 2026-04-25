"""Debug: muestra el JSON crudo que devuelve RapidAPI para un perfil de LinkedIn.

Uso:
    python debug_linkedin.py https://www.linkedin.com/in/usuario/
"""
from __future__ import annotations

import json
import sys

from config import load_settings
from linkedin_scraper import _extract_username, _filter_recent_posts, _clean_profile

import requests


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python debug_linkedin.py <linkedin_url>")
        sys.exit(1)

    url = sys.argv[1]
    settings = load_settings()

    username = _extract_username(url)
    if not username:
        print(f"URL inválida: {url}")
        sys.exit(1)

    print(f"\nConsultando RapidAPI para: {username}\n")

    api_url = f"https://{settings.rapidapi_host}/profile-data-connection-count-posts"
    headers = {
        "x-rapidapi-host": settings.rapidapi_host,
        "x-rapidapi-key": settings.rapidapi_key,
    }
    resp = requests.get(api_url, headers=headers, params={"username": username}, timeout=45)
    resp.raise_for_status()
    payload = resp.json()

    # ── 1. Perfil RAW ──────────────────────────────────────────────────────────
    print("=" * 60)
    print("PERFIL RAW (data)")
    print("=" * 60)
    print(json.dumps(payload.get("data") or {}, indent=2, ensure_ascii=False)[:4000])

    # ── 2. Posts RAW ──────────────────────────────────────────────────────────
    raw_posts = payload.get("posts") or []
    print(f"\n{'=' * 60}")
    print(f"POSTS RAW — total recibidos: {len(raw_posts)}")
    print("=" * 60)
    for i, post in enumerate(raw_posts[:5], start=1):
        print(f"\n--- Post {i} ---")
        print(json.dumps(post, indent=2, ensure_ascii=False)[:2000])

    # ── 3. Posts filtrados (lo que ve Claude) ─────────────────────────────────
    filtered = _filter_recent_posts(raw_posts, months=6, limit=10)
    print(f"\n{'=' * 60}")
    print(f"POSTS FILTRADOS (últimos 6 meses) — {len(filtered)} de {len(raw_posts)}")
    print("=" * 60)
    for i, post in enumerate(filtered, start=1):
        date = (post.get("postedDate") or "")[:10]
        text = (post.get("text") or post.get("commentary") or "(sin texto)").strip()
        print(f"\n[{i}] {date}")
        print(text[:500])

    # ── 4. Perfil limpio (lo que ve Claude) ───────────────────────────────────
    print(f"\n{'=' * 60}")
    print("PERFIL LIMPIO (lo que pasa a Claude)")
    print("=" * 60)
    cleaned = _clean_profile(payload.get("data") or {})
    print(json.dumps(cleaned, indent=2, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main()
