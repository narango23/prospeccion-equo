"""Orquestador principal del flujo de prospección Équo.

Para cada lead pendiente en el Google Sheet:
  1. Lee el lead (LinkedIn URL, empresa, web, etc.)
  2. Extrae perfil + posts de LinkedIn (RapidAPI)
  3. Resume la web de la empresa (Firecrawl)
  4. Busca noticias recientes de la empresa (Claude + web_search)
  5. Genera correo personalizado (Claude con prompt de Lina/Équo)
  6. Escribe Email Subject, Email Body, Fecha Procesado y Status en la hoja

Ejecución:
    python main.py
"""
from __future__ import annotations

import sys
import time
import traceback

from claude_client import ClaudeClient, EmailDraft
from config import load_settings
from firecrawl_scraper import fetch_company_summary
from linkedin_scraper import LinkedInData, fetch_linkedin
from sheets_client import SheetsClient


def format_linkedin_perfil(li_data: LinkedInData) -> str:
    """Formatea el perfil de LinkedIn en texto legible para la hoja."""
    p = li_data.profile
    if not p:
        return ""

    lines: list[str] = []
    if p.get("headline"):
        lines.append(f"Headline: {p['headline']}")
    if p.get("summary"):
        lines.append(f"Bio: {p['summary'][:800]}")
    positions = p.get("position") or []
    for pos in positions[:3]:
        title = pos.get("title", "")
        company = pos.get("companyName", "")
        start = (pos.get("start") or {})
        year = start.get("year", "")
        lines.append(f"Posicion: {title} @ {company}{f' ({year})' if year else ''}")
    educations = p.get("educations") or []
    for edu in educations[:2]:
        school = edu.get("schoolName", "")
        degree = edu.get("degreeName", "")
        lines.append(f"Educacion: {degree} — {school}".strip(" —"))

    return "\n".join(lines)


def format_linkedin_posts(li_data: LinkedInData) -> str:
    """Formatea los posts recientes de LinkedIn en texto legible para la hoja."""
    if not li_data.posts:
        return ""

    lines: list[str] = [f"Posts recientes — {len(li_data.posts)} en los últimos 6 meses"]
    for i, post in enumerate(li_data.posts[:10], start=1):
        text = (post.get("text") or post.get("commentary") or "").strip()
        date = (post.get("postedDate") or "")[:10]
        reactions = post.get("totalReactionCount", 0)
        comments = post.get("commentsCount", 0)
        if text:
            lines.append(f"\n[{i}] {date} · {reactions} reacciones · {comments} comentarios")
            lines.append(text[:1500])

    return "\n".join(lines)


def process_lead(
    lead: dict,
    sheets: SheetsClient,
    claude: ClaudeClient,
    settings,
) -> tuple[str, str]:
    """Procesa un lead. Devuelve (status, mensaje_corto) para log."""
    name = lead.get("First Name") or "(sin nombre)"
    company = lead.get("Company Name") or "(sin empresa)"
    row = lead["_row_number"]

    notes: list[str] = []  # registro de qué pasos completaron / fallaron

    # 1. LinkedIn
    li_url = lead.get("LinkedIn URL") or ""
    li_data = fetch_linkedin(li_url, settings.rapidapi_key, settings.rapidapi_host)
    if li_data.error:
        notes.append(f"linkedin:fail({li_data.error[:80]})")
    elif not li_data.has_data:
        notes.append("linkedin:vacio")
    else:
        notes.append(f"linkedin:ok(posts={len(li_data.posts)})")

    # 2. Firecrawl
    website = lead.get("Company Website") or ""
    company_data = fetch_company_summary(website, settings.firecrawl_api_key)
    if company_data.error:
        notes.append(f"firecrawl:fail({company_data.error[:60]})")
    elif not company_data.has_data:
        notes.append("firecrawl:vacio")
    else:
        notes.append("firecrawl:ok")

    # Si la hoja ya tiene Company Description, lo usamos como fallback
    summary = company_data.summary or (lead.get("Company Description") or "")

    # 3. Noticias
    news = claude.search_company_news(
        company=company,
        country=lead.get("Company Country") or "",
        industry=lead.get("Company Main Industry") or "",
        summary=summary,
    )
    notes.append("news:ok" if news and news.lower() != "no info" else "news:vacio")

    # 4. Generación de correo
    draft = claude.generate_email(
        lead=lead,
        linkedin_profile=li_data.profile,
        linkedin_posts=li_data.posts,
        company_summary=summary,
        news=news,
    )

    if draft.status == "no_info":
        status = "no_info"
        msg = "Claude reportó info insuficiente"
    elif not draft.subject or not draft.body:
        status = "incompleto"
        msg = "Falta subject o body"
    else:
        status = "ok"
        msg = "Correo generado"

    # Adjuntamos las notas de pasos al status para diagnóstico
    full_status = f"{status} | {' / '.join(notes)}"

    # 5. Escribir en hoja
    try:
        sheets.write_result(
            row_number=row,
            subject=draft.subject,
            body=draft.body,
            status=full_status,
            approach_note=draft.approach_note,
            lead=lead,
            linkedin_perfil=format_linkedin_perfil(li_data),
            linkedin_posts=format_linkedin_posts(li_data),
            company_summary=summary,
            news_info=news or "",
        )
    except Exception as exc:
        return "write_fail", f"Error escribiendo en sheet: {exc}"

    return status, f"{name} ({company}): {msg}"


def main() -> int:
    settings = load_settings()
    print(f"\n=== Prospección Équo · batch={settings.batch_size} · modelo={settings.claude_model} ===\n")

    sheets = SheetsClient(
        service_account_path=settings.service_account_path,
        sheet_id=settings.sheet_id,
        sheet_tab=settings.sheet_tab,
        output_tab=settings.output_sheet_tab,
    )
    claude = ClaudeClient(api_key=settings.anthropic_api_key, model=settings.claude_model)

    leads = sheets.fetch_pending_leads(limit=settings.batch_size)
    if not leads:
        print("No hay leads pendientes (Email Body vacío). Nada que hacer.")
        return 0

    print(f"Encontrados {len(leads)} leads pendientes. Procesando...\n")

    counts: dict[str, int] = {}
    for i, lead in enumerate(leads, start=1):
        print(f"[{i}/{len(leads)}] fila={lead['_row_number']} ", end="", flush=True)
        try:
            status, msg = process_lead(lead, sheets, claude, settings)
        except Exception as exc:
            traceback.print_exc()
            status = "exception"
            msg = f"Excepción no manejada: {exc}"
            try:
                sheets.write_result(
                    row_number=lead["_row_number"],
                    subject="",
                    body="",
                    status=f"exception | {exc}",
                    lead=lead,
                )
            except Exception:
                pass

        counts[status] = counts.get(status, 0) + 1
        print(f"-> {status} :: {msg}")

        # Pequeña pausa para no saturar APIs
        if i < len(leads):
            time.sleep(1.5)

    print("\n=== Resumen ===")
    for status, n in sorted(counts.items()):
        print(f"  {status}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
