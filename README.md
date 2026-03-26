# aurora-endpoint

Question-answering service for Aurora's take-home assignment. It preloads the upstream `Messages API` into memory, retrieves the most relevant messages for a user question, and asks an LLM to produce a grounded structured answer.

## Request - test it on openrouter or wherever (enter any query in body)
```bash
curl -X POST https://aurora-endpoint.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"What travel preferences has Vikram Desai mentioned?"}'
```


## Architecture

- `FastAPI` serves `POST /ask` and `GET /health`.
- `httpx.AsyncClient` fetches paginated messages from the upstream API.
- `cachetools.TTLCache` keeps the message corpus in memory for low-latency reads.
- A startup preload warms the cache before traffic, and a background refresh keeps it fresh.
- A lightweight lexical retriever narrows the candidate set before the LLM call.
- `OpenRouter` provides model routing flexibility without coupling the app to a single provider.

## Request Flow

1. The app starts and fetches all pages from `/messages/`.
2. The results are stored in an in-memory TTL cache.
3. `POST /ask` reads from cache, never from the upstream API on the hot path.
4. The retriever filters by `user_name` when the question clearly names one, then ranks the top relevant messages.
5. The LLM returns JSON that matches the assignment schema.

## Project Structure

```text
app/
  api/routes.py
  clients/messages_api.py
  clients/llm.py
  services/cache_service.py
  services/retrieval_service.py
  services/qa_service.py
  config.py
  schemas.py
  main.py
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set `OPENROUTER_API_KEY` in `.env`. Everything else uses code defaults, so the env file only needs the API key.

Then run:

```bash
uvicorn app.main:app --reload
```

## Testing Examples

These are a few example questions I ran locally against the service.

- `What hotel preferences has Sophia Al-Farsi mentioned?`
```json
{
  "answer": "Sophia Al-Farsi prefers hypoallergenic pillows and bedding, a fresh fruit basket upon check-in, and a park view room at the Ritz-Carlton.",
  "confidence": 0.95,
  "sources": [
    "0485acf9-1920-4985-8e35-3cb04ae19b94",
    "4d2cd313-ee86-4655-be5c-f05714fc6c9b",
    "e8ebe88e-9453-4118-9e35-3d56f37ea80c"
  ],
  "metadata": {
    "reasoning": "Sophia explicitly requested hypoallergenic bedding, fresh fruit baskets, and a park view room; these are the clearest hotel preferences mentioned."
  }
}
```

- `What did Armand Dupont request for future hotel stays?`
```json
{
  "answer": "Armand Dupont requested to change his hotel to the Four Seasons for his upcoming Europe trip and to upgrade his hotel room to a suite with a balcony.",
  "confidence": 0.95,
  "sources": [
    "7807bf91-ee32-49c9-9d17-de258c2006b6",
    "e83cd9e3-2d86-4982-b04a-26929c8ea971"
  ],
  "metadata": {
    "reasoning": "Armand explicitly requested the Four Seasons hotel change and a suite upgrade with balcony; these are the clearest future hotel stay requests."
  }
}
```

- `What is Hans Muller's favorite sushi restaurant in Tokyo?`
```json
{
  "answer": "There is no information about Hans Muller's favorite sushi restaurant in Tokyo.",
  "confidence": 1.0,
  "sources": [
    "0125e3a7-4f26-4c72-b0d9-a5c6d90fdcbe",
    "61594211-b93d-43f6-a39e-f0cbbe3ea83c",
    "2179bda1-ab65-4b59-94d2-1bd51dd19ecd"
  ],
  "metadata": {
    "reasoning": "Hans Muller asked about sushi spots in Tokyo and planned a trip there, but no message states his favorite sushi restaurant."
  }
}
```

## Production Readiness

If we needed to scale this to 100,000 members with a decade of history, the current in-memory TTL polling architecture + the simple heuristic scorer would immediately bottleneck. (eg vs having embeddings) The first architectural evolution would be:

- Replace the periodic full-cache refreshes with a webhook-based or streaming ingestion pipeline, so new upstream messages are pushed into the system asynchronously.
- Instead of storing raw text in memory, asynchronously vectorize incoming messages with an embedding model like Gemini Embedding 2 and store them in a vector database like Pinecone or Postgres with `pgvector`.
- During `/ask`, perform hybrid search by combining semantic vector similarity with keyword matching, strictly filtered to that specific member's namespace.

