"""Cliente de Google Sheets — lectura desde Contactos, escritura en investigacion_claude.

Diseño de dos pestañas:
  - source_tab  ("Contactos"):          datos RAW de Lusha, no se toca nunca.
  - output_tab  ("investigacion_claude"): filas generadas por el flujo; se añade
                                          una fila nueva por cada lead procesado.

Un lead se considera PENDIENTE si su clave (LinkedIn URL, o First Name|Company Name
como fallback) NO aparece todavía en la pestaña de salida.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Columnas que tendrá la pestaña investigacion_claude
OUTPUT_COLUMNS = [
    "Contactos_Row",   # nro de fila original en Contactos (para trazabilidad)
    "First Name",
    "Last Name",
    "Company Name",
    "LinkedIn URL",
    "LinkedIn_Perfil",    # perfil extraído por RapidAPI
    "LinkedIn_Posts",     # posts recientes extraídos por RapidAPI
    "Company_Summary",    # resumen web extraído por Firecrawl
    "News_Info",          # noticias recientes encontradas por Claude web_search
    "Email Subject",
    "Email Body",
    "Fecha Procesado",
    "Status",
]


class SheetsClient:
    def __init__(
        self,
        service_account_path: Path,
        sheet_id: str,
        sheet_tab: str,           # fuente: Contactos
        output_tab: str,          # destino: investigacion_claude
    ):
        creds = Credentials.from_service_account_file(str(service_account_path), scopes=SCOPES)
        gc = gspread.authorize(creds)
        self._spreadsheet = gc.open_by_key(sheet_id)

        # Pestaña fuente — solo lectura
        self._source_ws = self._spreadsheet.worksheet(sheet_tab)
        self._headers = self._source_ws.row_values(1)  # expuesto para el test

        # Pestaña de salida — la creamos si no existe, y verificamos headers
        self._output_ws = self._ensure_output_tab(output_tab)

    # ---------------------------------------------------------------- helpers

    def _ensure_output_tab(self, tab_name: str) -> gspread.Worksheet:
        """Crea la pestaña de salida si no existe y garantiza los headers correctos."""
        try:
            ws = self._spreadsheet.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            ws = self._spreadsheet.add_worksheet(
                title=tab_name, rows=1000, cols=len(OUTPUT_COLUMNS)
            )

        # Si la primera fila no coincide exactamente, reescribimos los headers
        current = ws.row_values(1)
        if current != OUTPUT_COLUMNS:
            ws.update(range_name="A1", values=[OUTPUT_COLUMNS])

        return ws

    def _lead_key(self, row: dict) -> str:
        """Clave única para un lead: LinkedIn URL si existe, si no First Name|Company."""
        li = (row.get("LinkedIn URL") or "").strip()
        if li:
            return li
        return f"{row.get('First Name', '')}|{row.get('Company Name', '')}".strip()

    # ----------------------------------------------------------------- public

    def fetch_pending_leads(self, limit: int) -> list[dict[str, Any]]:
        """Lee Contactos y descarta los que ya están en investigacion_claude."""
        # Claves ya procesadas (cualquier fila en la pestaña de salida)
        output_rows = self._output_ws.get_all_records()
        processed: set[str] = set()
        for row in output_rows:
            k = self._lead_key(row)
            if k and k != "|":
                processed.add(k)

        # Filas pendientes de la pestaña fuente
        source_rows = self._source_ws.get_all_records()
        pending: list[dict[str, Any]] = []
        for i, row in enumerate(source_rows, start=2):  # fila 1 = headers
            k = self._lead_key(row)
            if k and k not in processed:
                row["_row_number"] = i
                pending.append(row)
                if len(pending) >= limit:
                    break
        return pending

    def write_result(
        self,
        row_number: int,          # nro de fila en Contactos (solo referencia)
        subject: str | None,
        body: str | None,
        status: str,
        approach_note: str | None = None,
        lead: dict | None = None,
        linkedin_perfil: str | None = None,
        linkedin_posts: str | None = None,
        company_summary: str | None = None,
        news_info: str | None = None,
    ) -> None:
        """Añade una fila nueva en investigacion_claude con los resultados."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        body_with_note = body or ""
        if approach_note and body:
            body_with_note = f"{body}\n\n---\n[Nota approach]: {approach_note}"

        lead = lead or {}
        new_row = [
            row_number,
            lead.get("First Name", ""),
            lead.get("Last Name", ""),
            lead.get("Company Name", ""),
            lead.get("LinkedIn URL", ""),
            linkedin_perfil or "",
            linkedin_posts or "",
            company_summary or "",
            news_info or "",
            subject or "",
            body_with_note,
            timestamp,
            status,
        ]
        self._output_ws.append_row(new_row, value_input_option="USER_ENTERED")
