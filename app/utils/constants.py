import re

TOKEN_RE = re.compile(r"[a-z0-9']+")

RETRIEVAL_STOPWORDS = {
    "a",
    "an",
    "and",
    "i",
    "me",
    "my",
    "please",
    "the",
    "this",
}
