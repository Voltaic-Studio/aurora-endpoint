from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.schemas import AskResponse
from app.utils.settings_defaults import LLM_MAX_COMPLETION_TOKENS, LLM_TEMPERATURE


class OpenRouterClient:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http_client = http_client
        self._settings = settings

    async def answer_question(
        self,
        question: str,
        context: str,
        candidate_ids: list[str],
    ) -> AskResponse:
        if not self._settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        system_prompt = """
You are a retrieval-grounded QA system for concierge member history.

Answer using ONLY the provided candidate messages.
Do not use outside knowledge.
Do not guess.
Do not include unsupported details.

Return valid JSON with exactly this shape:
{
  "answer": "string",
  "confidence": 0.0,
  "sources": ["message_id"],
  "metadata": {
    "reasoning": "string"
  }
}

Rules:
1. Every claim must be supported by the candidate messages.
2. "sources" must contain only message IDs from the provided context.
3. Prefer the smallest set of facts needed to answer the question well.
4. For broad questions, summarize only the most important supported points instead of listing everything.
5. If evidence is weak, conflicting, or incomplete, say that clearly.
6. If the answer cannot be determined, say so explicitly.
7. Never fabricate preferences, bookings, relationships, dates, or personal details.

Style requirements:
- Keep "answer" to 1 short sentence when possible, never more than 2 sentences.
- Keep "answer" under 60 words.
- Keep "metadata.reasoning" under 25 words.
- Be concise and factual, not exhaustive.
- Do not use vague phrases like "these messages", "the retrieved evidence", or "the context".
- In "metadata.reasoning", name the user and cite the concrete facts that support the answer.
- Make "metadata.reasoning" read like a brief evidence trace, not a generic justification.
- Do not make "metadata.reasoning" a paraphrase of the answer.
- In "metadata.reasoning", explain why the cited messages were chosen or why they were sufficient.

Confidence guidance:
- 0.90 to 1.00: directly supported by multiple consistent messages
- 0.70 to 0.89: directly supported by one strong message or several mostly consistent messages
- 0.40 to 0.69: partial or somewhat ambiguous support
- 0.10 to 0.39: weak evidence, conflicting evidence, or indirect inference
- 0.00 to 0.09: no meaningful evidence

Return JSON only.
""".strip()

        user_prompt = f"""
Question:
{question}

Allowed source IDs:
{", ".join(candidate_ids)}

Candidate messages:
{context}

Instructions:
- Identify the smallest set of messages needed to answer the question.
- If no message supports the answer, return a no-data response.
- If messages support multiple possible answers, return an ambiguous response.
- Prefer a compact summary over an exhaustive list.
- Mention only the strongest supported preferences or facts.
- Keep the answer concise.
- Keep reasoning brief but specific.
- For reasoning, directly mention the user and the strongest supporting facts.
- For reasoning, add a short selection trace such as why those facts were enough or why no stronger conflict appeared.
- Example reasoning style: "Vikram explicitly requested an espresso machine in suites and a stocked wine cellar in holiday homes; those were the clearest retrieved preferences."
- Return JSON only.
""".strip()

        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if self._settings.openrouter_site_url:
            headers["HTTP-Referer"] = self._settings.openrouter_site_url
        if self._settings.openrouter_app_name:
            headers["X-Title"] = self._settings.openrouter_app_name

        response = await self._http_client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json={
                "model": self._settings.openrouter_model,
                "temperature": LLM_TEMPERATURE,
                "max_tokens": LLM_MAX_COMPLETION_TOKENS,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
        )

        if response.is_error:
            message = self._extract_error_message(response)
            raise RuntimeError(
                f"OpenRouter request failed with status {response.status_code}: {message}"
            )

        payload = response.json()
        content = payload["choices"][0]["message"]["content"]

        if not isinstance(content, str):
            raise ValueError("Model response was not a JSON string")

        try:
            return AskResponse.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError("Model response did not match AskResponse schema") from exc

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text or "Unknown OpenRouter error"

        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message

        return response.text or "Unknown OpenRouter error"
