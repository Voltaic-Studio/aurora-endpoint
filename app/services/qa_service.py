from __future__ import annotations

from app.clients.llm import OpenRouterClient
from app.schemas import AskMetadata, AskResponse, IndexedMessage
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
        snapshot = await self._cache_service.get_snapshot()
        query_embedding = await self._llm_client.embed_text(question)

        _, scoped_messages = self._retrieval_service.resolve_member_scope(
            question=question,
            messages_by_user_id=snapshot.messages_by_user_id,
            user_names_by_id=snapshot.user_names_by_id,
        )
        candidates = self._retrieval_service.retrieve_semantic(
            query_embedding=query_embedding,
            candidates=scoped_messages,
        )
        if not candidates:
            return self._build_no_data_response(
                reason="No retrieved messages were semantically similar enough to the question."
            )

        context = self._retrieval_service.build_context(candidates)
        candidate_ids = [message.record.id for message in candidates]

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

        return self._validate_grounding(response=response, candidates=candidates)

    @staticmethod
    def _build_no_data_response(reason: str) -> AskResponse:
        return AskResponse(
            answer="I could not find enough evidence in the available messages to answer that reliably.",
            confidence=0.0,
            sources=[],
            metadata=AskMetadata(reasoning=reason),
        )

    @staticmethod
    def _validate_grounding(response: AskResponse, candidates: list[IndexedMessage]) -> AskResponse:
        candidate_id_set = {message.record.id for message in candidates}
        valid_sources = [source for source in response.sources if source in candidate_id_set]

        if len(valid_sources) != len(response.sources):
            return AskResponse(
                answer=response.answer,
                confidence=min(response.confidence, 0.5),
                sources=valid_sources,
                metadata=AskMetadata(
                    reasoning=(
                        f"{response.metadata.reasoning} Invalid source IDs were removed because they were "
                        "not present in the retrieved evidence."
                    ).strip()
                ),
            )

        if response.sources or response.confidence <= 0.3:
            return response

        return AskResponse(
            answer="I could not generate a reliable answer from the available messages.",
            confidence=0.0,
            sources=[],
            metadata=AskMetadata(
                reasoning="The model returned an answer without grounded source IDs from the retrieved evidence."
            ),
        )
