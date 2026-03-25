from __future__ import annotations

from app.clients.llm import OpenRouterClient
from app.schemas import AskMetadata, AskResponse
from app.services.cache_service import MessageCacheService
from app.services.retrieval_service import RetrievalService


class QAService:
    def __init__(
        self,
        cache_service: MessageCacheService,
        retrieval_service: RetrievalService,
        llm_client: OpenRouterClient,
    ) -> None:
        self._cache_service = cache_service
        self._retrieval_service = retrieval_service
        self._llm_client = llm_client

    async def answer_question(self, question: str) -> AskResponse:
        messages = await self._cache_service.get_messages()
        scored_candidates = self._retrieval_service.retrieve_scored(question, messages)
        if not scored_candidates:
            return self._build_no_data_response(
                reason="No retrieved messages contained meaningful overlap with the question."
            )

        top_k = self._retrieval_service.top_k_for_question(question)
        candidates = [message for _, message in scored_candidates[:top_k]]
        context = self._retrieval_service.build_context(candidates)
        candidate_ids = [message.id for message in candidates]
        candidate_id_set = set(candidate_ids)

        try:
            response = await self._llm_client.answer_question(
                question=question,
                context=context,
                candidate_ids=candidate_ids,
            )
        except ValueError:
            return self._build_no_data_response(
                reason="The model response could not be validated against the required schema."
            )

        valid_sources = [source for source in response.sources if source in candidate_id_set]
        if len(valid_sources) != len(response.sources):
            reasoning = (
                f"{response.metadata.reasoning} Invalid source IDs were removed because they were not "
                "present in the retrieved evidence."
            ).strip()
            response = AskResponse(
                answer=response.answer,
                confidence=min(response.confidence, 0.5),
                sources=valid_sources,
                metadata=AskMetadata(reasoning=reasoning),
            )

        if not response.sources and response.confidence > 0.3:
            response = AskResponse(
                answer="I could not generate a reliable answer from the available messages.",
                confidence=0.0,
                sources=[],
                metadata=AskMetadata(
                    reasoning="The model returned an answer without grounded source IDs from the retrieved evidence."
                ),
            )

        return response

    @staticmethod
    def _build_no_data_response(reason: str) -> AskResponse:
        return AskResponse(
            answer="I could not find enough evidence in the available messages to answer that reliably.",
            confidence=0.0,
            sources=[],
            metadata=AskMetadata(reasoning=reason),
        )
