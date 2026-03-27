from __future__ import annotations

from collections import Counter
import unicodedata

from app.schemas import MessageRecord
from app.utils.constants import RETRIEVAL_STOPWORDS, TOKEN_RE


class RetrievalService:
    def retrieve(self, question: str, messages: list[MessageRecord]) -> list[MessageRecord]:
        normalized_question = self._normalize_text(question)
        matched_name = self._matched_user_name(normalized_question, messages)
        candidate_messages = self._filter_messages_by_user_name(normalized_question, messages)
        if matched_name and self._is_profile_query(normalized_question):
            return candidate_messages

        scored_messages = self.retrieve_scored(question, messages)
        return [message for _, message in self._select_relevant_candidates(scored_messages)]

    def retrieve_scored(self, question: str, messages: list[MessageRecord]) -> list[tuple[float, MessageRecord]]:
        normalized_question = self._normalize_text(question)
        all_question_tokens = self._tokenize_all(normalized_question)
        content_question_tokens = self._tokenize_content(normalized_question)
        if not all_question_tokens:
            return []

        matched_name = self._matched_user_name(normalized_question, messages)
        candidate_messages = self._filter_messages_by_user_name(normalized_question, messages)
        scored_messages: list[tuple[float, MessageRecord]] = []
        question_counts = Counter(content_question_tokens or all_question_tokens)
        all_question_counts = Counter(all_question_tokens)
        question_fragments = self._question_fragments(all_question_tokens)
        question_text = normalized_question

        for message in candidate_messages:
            # Once the query resolves to a single user, scoring against the name adds
            # the same overlap to every message and washes out real content relevance.
            haystack_source = message.message if matched_name else f"{message.user_name} {message.message}"
            haystack = self._normalize_text(haystack_source)
            all_message_tokens = self._tokenize_all(haystack)
            content_message_tokens = self._tokenize_content(haystack)
            if not all_message_tokens:
                continue

            message_counts = Counter(content_message_tokens or all_message_tokens)
            all_message_counts = Counter(all_message_tokens)
            overlap = sum(min(question_counts[token], message_counts[token]) for token in question_counts)
            all_token_overlap = sum(
                min(all_question_counts[token], all_message_counts[token]) for token in all_question_counts
            )
            soft_overlap = self._soft_overlap(
                question_counts,
                message_counts,
            )
            soft_all_overlap = self._soft_overlap(
                all_question_counts,
                all_message_counts,
            )
            unique_overlap = self._soft_unique_overlap(
                content_question_tokens or all_question_tokens,
                content_message_tokens or all_message_tokens,
            )
            phrase_bonus = (
                1.5
                if not matched_name and self._normalize_text(message.user_name) in question_text
                else 0.0
            )
            fragment_hits = sum(1 for fragment in question_fragments if fragment in haystack)

            score = (
                (overlap * 2.0)
                + unique_overlap
                + (soft_overlap * 1.25)
                + phrase_bonus
                + (all_token_overlap * 0.35)
                + (soft_all_overlap * 0.2)
                + (fragment_hits * 1.5)
            )
            if score > 0:
                scored_messages.append((score, message))

        scored_messages.sort(key=lambda item: (-item[0], item[1].timestamp), reverse=False)
        return scored_messages

    @staticmethod
    def _select_relevant_candidates(
        scored_messages: list[tuple[float, MessageRecord]],
    ) -> list[tuple[float, MessageRecord]]:
        return RetrievalService._select_top_score_band(scored_messages)

    @staticmethod
    def _select_top_score_band(
        scored_messages: list[tuple[float, MessageRecord]],
    ) -> list[tuple[float, MessageRecord]]:
        if len(scored_messages) <= 1:
            return scored_messages

        cutoff_index = len(scored_messages)
        widest_gap = float("-inf")

        for index, ((current_score, _), (next_score, _)) in enumerate(
            zip(scored_messages, scored_messages[1:])
        ):
            gap = current_score - next_score
            if gap > widest_gap:
                widest_gap = gap
                cutoff_index = index + 1

        return scored_messages[:cutoff_index]

    @staticmethod
    def _matched_user_name(question: str, messages: list[MessageRecord]) -> str | None:
        question_text = RetrievalService._normalize_text(question)
        matched_names = {
            message.user_name
            for message in messages
            if message.user_name and RetrievalService._normalize_text(message.user_name) in question_text
        }
        if len(matched_names) != 1:
            return None
        return next(iter(matched_names))

    @staticmethod
    def _filter_messages_by_user_name(
        question: str, messages: list[MessageRecord]
    ) -> list[MessageRecord]:
        matched_name = RetrievalService._matched_user_name(question, messages)
        if not matched_name:
            return messages

        return [message for message in messages if message.user_name == matched_name]

    @staticmethod
    def build_context(messages: list[MessageRecord]) -> str:
        lines = []
        for message in messages:
            lines.append(
                f"[{message.id}] {message.user_name} | {message.timestamp} | {message.message}"
            )
        return "\n".join(lines)

    @staticmethod
    def _question_fragments(tokens: list[str]) -> list[str]:
        fragments: list[str] = []
        max_size = min(4, len(tokens))
        for size in range(max_size, 1, -1):
            for index in range(len(tokens) - size + 1):
                fragment = " ".join(tokens[index : index + size])
                if len(fragment) >= 8:
                    fragments.append(fragment)
        return fragments

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        return ascii_text.lower()

    @staticmethod
    def _normalize_token(token: str) -> str:
        normalized = token
        if normalized.endswith("'s"):
            normalized = normalized[:-2]
        if len(normalized) > 4 and normalized.endswith("ies"):
            return normalized[:-3] + "y"
        if len(normalized) > 4 and normalized.endswith("es") and not normalized.endswith("ses"):
            return normalized[:-2]
        if len(normalized) > 4 and normalized.endswith("s") and not normalized.endswith("ss"):
            return normalized[:-1]
        return normalized

    @staticmethod
    def _common_prefix_length(left: str, right: str) -> int:
        length = 0
        for left_char, right_char in zip(left, right):
            if left_char != right_char:
                break
            length += 1
        return length

    @staticmethod
    def _is_profile_query(question: str) -> bool:
        return any(
            token.startswith("prefer") or token in {"favorite", "favourite"}
            for token in RetrievalService._tokenize_all(question)
        )

    @staticmethod
    def _tokens_related(left: str, right: str) -> bool:
        if left == right:
            return True
        shorter, longer = sorted((left, right), key=len)
        if len(shorter) < 5:
            return False
        prefix_length = RetrievalService._common_prefix_length(shorter, longer)
        return prefix_length >= max(4, int(len(shorter) * 0.75))

    @staticmethod
    def _soft_overlap(
        question_counts: Counter[str],
        message_counts: Counter[str],
    ) -> float:
        total = 0.0
        for question_token, question_count in question_counts.items():
            if question_token in message_counts:
                continue
            best_match = 0
            for message_token, message_count in message_counts.items():
                if RetrievalService._tokens_related(question_token, message_token):
                    best_match = max(best_match, min(question_count, message_count))
            total += best_match
        return total

    @staticmethod
    def _soft_unique_overlap(question_tokens: list[str], message_tokens: list[str]) -> int:
        message_token_set = set(message_tokens)
        count = 0
        for question_token in set(question_tokens):
            if question_token in message_token_set:
                count += 1
                continue
            if any(
                RetrievalService._tokens_related(question_token, message_token)
                for message_token in message_token_set
            ):
                count += 1
        return count

    @staticmethod
    def _tokenize_all(value: str) -> list[str]:
        return [
            RetrievalService._normalize_token(token)
            for token in TOKEN_RE.findall(RetrievalService._normalize_text(value))
        ]

    @staticmethod
    def _tokenize_content(value: str) -> list[str]:
        return [
            token for token in RetrievalService._tokenize_all(value) if token not in RETRIEVAL_STOPWORDS
        ]
