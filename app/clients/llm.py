from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.schemas import AskResponse
from app.utils.settings_defaults import LLM_TEMPERATURE


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
You are a retrieval-grounded QA system for concierge member history only.

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
3. Prefer the most relevant supported facts for the question.
4. Be concise, but not at the expense of useful supported detail.
5. If evidence is weak, conflicting, or incomplete, say that clearly.
6. If the answer cannot be determined, say so explicitly.
7. Never fabricate preferences, bookings, relationships, dates, or personal details.
8. If the question is about one user, keep the answer strictly about that user.
9. Do not mention other users unless the question explicitly asks for a comparison.
10. Match the scope of the question exactly; do not add nearby facts that share only a location, city, category, or trip.
11. For preference questions, prioritize explicit standing or recurring preferences over one-off requests or bookings.
12. Do not turn isolated bookings, reservations, or logistics requests into general preferences unless the message explicitly frames them that way.
13. If the evidence shows mixed or conflicting preferences, say that explicitly and lower confidence accordingly.
14. For questions asking for a single favorite, exact property, exact brand, or exact restaurant, provide it only if it is explicitly named.

Style requirements:
- Keep "answer" under 80 words.
- Keep "metadata.reasoning" under 25 words.
- Be concise and factual, but include additional relevant facts when they improve fidelity.
- If the answer names the user, prefer the first name rather than repeating the full name unless the full name adds clarity.
- If a fact would sound vague or awkward on its own, include enough nearby detail to make it clear and natural.
- Do not use vague phrases like "these messages", "the retrieved evidence", or "the context".
- In "metadata.reasoning", name the user and cite the concrete facts that support the answer.
- Make "metadata.reasoning" read like a brief evidence trace, not a generic justification.
- Do not make "metadata.reasoning" a paraphrase of the answer.
- In "metadata.reasoning", explain why the cited messages were chosen or why they were sufficient.
- When the question is narrow, keep the answer narrow.
- For preference summaries, favor durable profile facts over incidental trip details.
- If evidence is mixed, state the conflict rather than smoothing it over.
- If an exact named item is not stated, say that it was not stated.

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
- Keep the answer concise, but not at the expense of useful supported detail.
- Include additional relevant facts when they improve fidelity to the user's question.
- If a retrieved detail would be unclear by itself, add enough local context to make it understandable.
- If the question is about one user, do not mention facts about any other user.
- For no-data answers, explain only that the needed fact was not stated; do not pad with unrelated nearby evidence.
- For questions asking about a specific preference, favorite, chain, or property, do not rely on indirect hints like a "usual hotel" reference unless it directly answers the question.
- For narrow questions, do not add adjacent facts just because they share the same city, hotel, restaurant, or trip.
- For preference questions, separate durable preferences from one-off bookings; prefer durable preferences in the answer.
- If a message sounds like a one-time request rather than an enduring preference, treat it as weaker evidence.
- If the evidence is mixed or contradictory, say so directly instead of forcing one clean summary.
- If the question asks for an exact named favorite, property, brand, or restaurant, return it only if the exact name is explicitly stated.
- Keep reasoning brief but specific.
- For reasoning, directly mention the user and the strongest supporting facts.
- For reasoning, add a short selection trace such as why those facts were enough or why no stronger conflict appeared.
- Return JSON only.
""".strip()

        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }

        response = await self._http_client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json={
                "model": self._settings.openrouter_model,
                "temperature": LLM_TEMPERATURE,
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
