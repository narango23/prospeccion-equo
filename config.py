"""Carga de configuración desde variables de entorno."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# override=True asegura que el .env tome precedencia sobre variables del sistema
# (algunas instalaciones de Windows tienen ANTHROPIC_API_KEY="" preseteado)
load_dotenv(override=True)

ROOT = Path(__file__).resolve().parent


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Falta variable de entorno requerida: {name}. Revisa tu archivo .env.")
    return value


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    claude_model: str
    rapidapi_key: str
    rapidapi_host: str
    firecrawl_api_key: str
    sheet_id: str
    sheet_tab: str          # pestaña fuente (Contactos)
    output_sheet_tab: str   # pestaña de resultados (investigacion_claude)
    service_account_path: Path
    batch_size: int


def load_settings() -> Settings:
    sa_path = ROOT / os.getenv("SERVICE_ACCOUNT_JSON", "service_account.json")
    if not sa_path.exists():
        raise RuntimeError(
            f"No se encontró el service account en {sa_path}. "
            "Descarga el JSON desde Google Cloud y guárdalo como service_account.json en la raíz del proyecto."
        )

    return Settings(
        anthropic_api_key=_required("ANTHROPIC_API_KEY"),
        claude_model=os.getenv("CLAUDE_MODEL", "claude-opus-4-7"),
        rapidapi_key=_required("RAPIDAPI_KEY"),
        rapidapi_host=os.getenv("RAPIDAPI_HOST", "professional-network-data.p.rapidapi.com"),
        firecrawl_api_key=_required("FIRECRAWL_API_KEY"),
        sheet_id=_required("GOOGLE_SHEET_ID"),
        sheet_tab=_required("GOOGLE_SHEET_TAB"),
        output_sheet_tab=os.getenv("OUTPUT_SHEET_TAB", "investigacion_claude"),
        service_account_path=sa_path,
        batch_size=int(os.getenv("BATCH_SIZE", "20")),
    )
