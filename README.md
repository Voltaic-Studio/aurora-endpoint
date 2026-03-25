# aurora-endpoint

Question-answering service for Aurora's take-home assignment. It preloads the upstream `Messages API` into memory, retrieves the most relevant messages for a user question, and asks an LLM to produce a grounded structured answer.

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
cp .env.example .env
```

Set `OPENROUTER_API_KEY` in `.env`. The cache/retrieval tuning now lives in code defaults, so the env file only needs secrets and optional model selection.

Then run:

```bash
uvicorn app.main:app --reload
```

## Example Request

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What is Amira'\''s favorite restaurant in Paris?"}'
```

## Production Readiness

If this had to scale to 100,000 members with 10 years of history each, the first architectural change would be replacing periodic full-cache refreshes with an event-driven ingestion pipeline that incrementally updates a proper search layer, such as OpenSearch, Postgres full-text search, or a vector database. That would avoid repeatedly pulling the full dataset and would make retrieval much more selective and scalable.
