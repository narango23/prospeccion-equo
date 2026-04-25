"""Smoke test: valida que todas las piezas conecten antes de correr main.py.

Verifica:
  1. .env cargado y variables presentes
  2. service_account.json válido
  3. Conexión a Google Sheets + lectura de headers + tab existe
  4. Anthropic API responde con una llamada mínima

Si todo sale OK puedes correr `python main.py` con confianza.
"""
from __future__ import annotations

import sys

# Forzamos UTF-8 en stdout para que la consola de Windows (cp1252)
# no truene al imprimir caracteres especiales como ✓ ✗ ✅
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, Exception):
    pass


def step(num: int, label: str) -> None:
    print(f"\n[{num}] {label}")


def ok(msg: str) -> None:
    print(f"   [OK] {msg}")


def fail(msg: str) -> None:
    print(f"   [FAIL] {msg}")


def main() -> int:
    print("=== Test de conexión · Prospección Équo ===")

    # ---------- 1. Config ----------
    step(1, "Cargando .env")
    try:
        from config import load_settings
        settings = load_settings()
        ok(f"sheet_id = {settings.sheet_id[:20]}...")
        ok(f"tab = {settings.sheet_tab}")
        ok(f"modelo = {settings.claude_model}")
        ok(f"batch_size = {settings.batch_size}")
        ok(f"service_account = {settings.service_account_path.name}")
    except Exception as exc:
        fail(f"Error cargando config: {exc}")
        return 1

    # ---------- 2. Google Sheets ----------
    step(2, "Conectando a Google Sheets")
    try:
        from sheets_client import SheetsClient
        sheets = SheetsClient(
            service_account_path=settings.service_account_path,
            sheet_id=settings.sheet_id,
            sheet_tab=settings.sheet_tab,
            output_tab=settings.output_sheet_tab,
        )
        ok("Autenticación OK")
        ok(f"Tab fuente '{settings.sheet_tab}' encontrado")
        ok(f"Tab salida '{settings.output_sheet_tab}' listo (creado si no existia)")
        headers_found = sheets._headers
        ok(f"Headers fuente ({len(headers_found)} columnas): {', '.join(headers_found[:6])}...")

        # Verificar columnas mínimas en Contactos (fuente RAW)
        required = ["First Name", "Company Name", "LinkedIn URL", "Company Website"]
        missing = [c for c in required if c not in headers_found]
        if missing:
            fail(f"Faltan columnas en '{settings.sheet_tab}': {missing}")
            return 2
        ok(f"Columnas requeridas presentes en '{settings.sheet_tab}'")

        # Contar filas pendientes (no procesadas aún en investigacion_claude)
        pending = sheets.fetch_pending_leads(limit=5)
        ok(f"Encontre {len(pending)} leads pendientes (sin fila en '{settings.output_sheet_tab}') — muestro hasta 5")
        for lead in pending:
            print(f"      . fila {lead['_row_number']}: {lead.get('First Name','?')} @ {lead.get('Company Name','?')}")
    except Exception as exc:
        fail(f"Error con Google Sheets: {exc}")
        print("      Tips:")
        print("      - Compartiste la hoja con el service account como Editor?")
        print(f"      - El tab fuente se llama exactamente '{settings.sheet_tab}'?")
        print("      - Es Google Sheets nativo (no .xlsx)?")
        return 2

    # ---------- 3. Anthropic ----------
    step(3, "Probando Anthropic API (1 llamada mínima)")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=settings.claude_model,
            max_tokens=20,
            messages=[{"role": "user", "content": "Responde solo: PONG"}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        ok(f"Respuesta del modelo: {text.strip()!r}")
        ok(f"Tokens — input: {resp.usage.input_tokens}, output: {resp.usage.output_tokens}")
    except anthropic.AuthenticationError:
        fail("API key inválida — revisa ANTHROPIC_API_KEY en .env")
        return 3
    except anthropic.NotFoundError as exc:
        fail(f"Modelo no encontrado: {exc}")
        print(f"      ¿Existe '{settings.claude_model}' en tu cuenta? Prueba con 'claude-sonnet-4-6'.")
        return 3
    except Exception as exc:
        fail(f"Error con Anthropic: {exc}")
        return 3

    print("\n=== ✓ Todo conectado. Listo para correr main.py ===\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
