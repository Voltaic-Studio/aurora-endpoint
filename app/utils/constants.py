import re

TOKEN_RE = re.compile(r"[a-z0-9']+")

RETRIEVAL_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "me",
    "my",
    "of",
    "on",
    "or",
    "please",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "who",
    "with",
}

BROAD_QUERY_TERMS = {
    "favorite",
    "favorites",
    "habit",
    "habits",
    "history",
    "interests",
    "pattern",
    "patterns",
    "preferences",
    "preference",
    "typically",
    "usual",
    "usually",
}
