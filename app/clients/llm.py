from __future__ import annotations

import asyncio
import json

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.schemas import AskResponse
from app.utils.settings_defaults import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MAX_CONCURRENCY,
    EMBEDDING_RETRIES,
    EMBEDDING_RETRY_DELAY_SECONDS,
    LLM_TEMPERATURE,
)


class OpenRouterClient:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http_client = http_client
        self._settings = settings

    async def embed_text(self, value: str) -> list[float]:
        embeddings = await self.embed_texts([value])
        if not embeddings:
            raise RuntimeError("Embedding request returned no vectors")
        return embeddings[0]

    async def embed_texts(self, values: list[str]) -> list[list[float]]:
        if not values:
            return []

        semaphore = asyncio.Semaphore(EMBEDDING_MAX_CONCURRENCY)
        tasks = [
            self._embed_batch(
                batch_index=batch_index,
                batch_values=values[start : start + EMBEDDING_BATCH_SIZE],
                semaphore=semaphore,
            )
            for batch_index, start in enumerate(range(0, len(values), EMBEDDING_BATCH_SIZE))
        ]
        ordered_batches = await asyncio.gather(*tasks)

        embeddings: list[list[float]] = []
        for _, batch_embeddings in sorted(ordered_batches, key=lambda item: item[0]):
            embeddings.extend(batch_embeddings)

        return embeddings

    async def answer_question(
        self,
        question: str,
        context: str,
        candidate_ids: list[str],
    ) -> AskResponse:
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
- Keep reasoning brief but specific.
- For reasoning, directly mention the user and the strongest supporting facts.
- For reasoning, add a short selection trace such as why those facts were enough or why no stronger conflict appeared.
- Return JSON only.
""".strip()

        response = await self._http_client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=self._build_headers(),
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

    async def _embed_batch(
        self,
        batch_index: int,
        batch_values: list[str],
        semaphore: asyncio.Semaphore,
    ) -> tuple[int, list[list[float]]]:
        attempts = EMBEDDING_RETRIES + 1
        for attempt in range(1, attempts + 1):
            try:
                async with semaphore:
                    response = await self._http_client.post(
                        "https://openrouter.ai/api/v1/embeddings",
                        headers=self._build_headers(),
                        json={
                            "model": self._settings.openrouter_embedding_model,
                            "input": batch_values,
                            "encoding_format": "float",
                        },
                    )

                if response.is_error:
                    message = self._extract_error_message(response)
                    raise RuntimeError(
                        f"OpenRouter embeddings request failed with status {response.status_code}: {message}"
                    )

                payload = response.json()
                rows = payload.get("data")
                if not isinstance(rows, list):
                    raise ValueError("Embedding response did not contain a data list")

                embeddings: list[list[float]] = []
                for row in rows:
                    if not isinstance(row, dict):
                        raise ValueError("Embedding response row was not an object")

                    embedding = row.get("embedding")
                    if not isinstance(embedding, list) or not embedding:
                        raise ValueError("Embedding response row did not contain a valid embedding")

                    if not all(isinstance(value, (int, float)) for value in embedding):
                        raise ValueError("Embedding response contained non-numeric values")

                    embeddings.append([float(value) for value in embedding])

                if len(embeddings) != len(batch_values):
                    raise ValueError("Embedding response length did not match request length")

                return batch_index, embeddings
            except (httpx.HTTPError, RuntimeError):
                if attempt == attempts:
                    raise
                await asyncio.sleep(EMBEDDING_RETRY_DELAY_SECONDS * attempt)

        raise RuntimeError("Embedding batch retries exhausted")

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

    def _build_headers(self) -> dict[str, str]:
        if not self._settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        return {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
