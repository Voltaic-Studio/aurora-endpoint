# aurora-endpoint

Question-answering service for Aurora's take-home assignment. It preloads the upstream `Messages API` into memory, retrieves the most relevant messages for a user question, and asks an LLM to produce a grounded structured answer.

## Request - test it on openrouter or wherever (enter any query in body)
```bash
curl -X POST https://aurora-endpoint.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"What travel preferences has Vikram Desai mentioned?"}'
```

Or go on this simple interface i made https://aurora-endpoint.vercel.app/


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
  "answer": "Sophia Al-Farsi requires hypoallergenic pillows and bedding, a fresh fruit basket upon check-in, and a park view for her room at the Ritz-Carlton. She has also requested pet accommodations for her cat during a stay in Rome.",
  "confidence": 1.0,
  "sources": [
    "0485acf9-1920-4985-8e35-3cb04ae19b94",
    "4d2cd313-ee86-4655-be5c-f05714fc6c9b",
    "2d9ecdd3-7b09-45b2-8408-3f5a16ca48fd",
    "e8ebe88e-9453-4118-9e35-3d56f37ea80c",
    "528788e9-4f8b-4994-a7b8-22d5063af7e0"
  ],
  "metadata": {
    "reasoning": "Sophia Al-Farsi explicitly requested hypoallergenic bedding, fruit baskets, park views, and cat accommodations across several messages."
  }
}
```

- `What contact details has Vikram Desai asked Aurora to update?`
```json
{
  "answer": "Vikram Desai has requested updates for his contact number (+44-7901-234567), his primary contact number (5553219874), and his emergency contact (initially 555-111-2222, then updated to his assistant at 3322110099). He also asked to add executive membership details to his profile.",
  "confidence": 1.0,
  "sources": [
    "a431a55a-7e85-4efe-8d90-96ddc906e418",
    "c0306413-3dc5-4378-a687-e079391a0c93",
    "b993cff1-ea78-4ae6-b88e-0295982c31dc",
    "19ad9ff0-6357-4140-bc0d-8dd76bb76cff",
    "299bc291-3114-47c1-a481-1d10a5360847"
  ],
  "metadata": {
    "reasoning": "Vikram provided specific phone numbers for primary and emergency contacts across multiple dates, plus a request for membership details."
  }
}
```

- `Which hotel brands or properties has Layla Kawaguchi mentioned preferring?`
```json
{
  "answer": "Layla Kawaguchi requested to adjust her preferred hotel chain to Peninsula for her annual visits. She also specifically requested a suite facing Central Park at The Plaza Hotel in New York.",
  "confidence": 1.0,
  "sources": [
    "6a559143-433d-4566-bb05-874d23448f27",
    "e02050f0-0598-4400-9ff9-080c3f24dc54"
  ],
  "metadata": {
    "reasoning": "Layla Kawaguchi explicitly named Peninsula as her preferred chain and requested a specific suite at The Plaza Hotel."
  }
}
```

## Production Readiness

If we needed to scale this to 100,000 members with a decade of history, the current in-memory TTL polling architecture + the simple heuristic scorer would immediately bottleneck. (eg vs having embeddings) The first architectural evolution would be:

- Replace the periodic full-cache refreshes with a webhook-based or streaming ingestion pipeline, so new upstream messages are pushed into the system asynchronously.
- Instead of storing raw text in memory, asynchronously vectorize incoming messages with an embedding model like Gemini Embedding 2 and store them in a vector database like Pinecone or Postgres with `pgvector`.
- During `/ask`, perform hybrid search by combining semantic vector similarity with keyword matching, strictly filtered to that specific member's namespace.

