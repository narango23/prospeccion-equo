"""Cliente de Claude para búsqueda de noticias y generación de correos."""
from __future__ import annotations

from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from prompts import LINA_SYSTEM_PROMPT, NEWS_SEARCH_PROMPT, build_user_prompt


class EmailDraft(BaseModel):
    """Estructura del correo generado por Claude."""
    status: Literal["ok", "no_info"] = Field(description="ok si hay correo, no_info si faltó info")
    subject: str = Field(default="", description="Subject line personalizado")
    body: str = Field(default="", description="Cuerpo completo del email con saludo, hook, relevancia, valor, CTA y cierre")
    approach_note: str = Field(default="", description="1 línea explicando el ángulo elegido")


class ClaudeClient:
    def __init__(self, api_key: str, model: str = "claude-opus-4-7"):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    # -------------------------------------------------------- news search

    def search_company_news(self, company: str, country: str, industry: str, summary: str) -> str:
        """Usa la herramienta web_search de Claude para buscar noticias recientes."""
        if not company.strip():
            return ""

        query = NEWS_SEARCH_PROMPT.format(
            company=company,
            country=country or "",
            industry=industry or "",
            summary=(summary or "")[:1500],  # truncar para no inflar tokens
        )

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=2000,
                tools=[{
                    "type": "web_search_20260209",
                    "name": "web_search",
                    "max_uses": 3,
                }],
                messages=[{"role": "user", "content": query}],
            )
        except anthropic.APIError as exc:
            return f"(error en búsqueda de noticias: {exc})"

        # Si pause_turn por límite del web_search, reanudamos una vez
        if response.stop_reason == "pause_turn":
            try:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=2000,
                    tools=[{
                        "type": "web_search_20260209",
                        "name": "web_search",
                        "max_uses": 3,
                    }],
                    messages=[
                        {"role": "user", "content": query},
                        {"role": "assistant", "content": response.content},
                    ],
                )
            except anthropic.APIError as exc:
                return f"(error en búsqueda de noticias: {exc})"

        # Extraer el último bloque de texto
        text_parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        full_text = "\n".join(part.strip() for part in text_parts if part).strip()
        return full_text or "no info"

    # ------------------------------------------------------- email generation

    def generate_email(
        self,
        lead: dict,
        linkedin_profile: dict,
        linkedin_posts: list,
        company_summary: str,
        news: str,
    ) -> EmailDraft:
        """Genera el correo personalizado con el prompt de Lina/Équo."""
        user_prompt = build_user_prompt(
            lead=lead,
            linkedin_profile=linkedin_profile,
            linkedin_posts=linkedin_posts,
            company_summary=company_summary,
            news=news,
        )

        # System prompt cacheado — el bloque grande de Lina se reutiliza en cada
        # llamada de un mismo run. Ahorra ~90% en tokens repetidos.
        system_blocks = [{
            "type": "text",
            "text": LINA_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }]

        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=2000,
                system=system_blocks,
                messages=[{"role": "user", "content": user_prompt}],
                output_format=EmailDraft,
            )
        except anthropic.APIError as exc:
            # Devolvemos un draft de error
            return EmailDraft(
                status="no_info",
                approach_note=f"Error de API: {exc}",
            )

        if response.parsed_output is None:
            return EmailDraft(
                status="no_info",
                approach_note="Claude no devolvió JSON válido",
            )

        return response.parsed_output
