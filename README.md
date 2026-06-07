# Creator Analytics RAG — Video Intelligence Platform

A full-stack RAG (Retrieval-Augmented Generation) chatbot that ingests YouTube and Instagram Reels, embeds their transcripts and metadata into a local vector database, and answers natural language questions about them using a LangGraph-orchestrated AI agent backed by Google Gemini.

Built as a technical screening project. The spec said "full-stack RAG chatbot with LangChain/LangGraph + embeddings + vector DB." What I actually ended up building was substantially more involved than that description implies.

---

## What It Does

Paste a YouTube URL and an Instagram Reel URL. Click Analyze. The app:

1. **Scrapes** both videos — transcripts, view counts, like counts, comments, follower counts, hashtags, upload dates, and duration
2. **Chunks** the transcripts using recursive character splitting (400 chars, 50 overlap)
3. **Embeds** every chunk using Gemini's `gemini-embedding-2` model (3072 dimensions)
4. **Stores** each chunk in a local Qdrant vector collection, with the full video metadata merged directly into every chunk's payload
5. **Routes** your chat queries through a LangGraph state machine that decides whether to hit the analytics engine (for metrics questions) or the semantic retriever (for content questions)
6. **Streams** the Gemini 2.5 Flash response back word-by-word to the chat panel

The whole thing runs locally. No cloud vector DB subscription required. No OpenAI bill.

---

## Architecture

```
Frontend (Next.js)
│
│  POST /api/ingest ──► Scraper (YouTube + Instagram)
│                            │
│                            ▼
│                       vector_pipeline.py
│                       └── Gemini embeddings
│                       └── Qdrant upsert (local Docker)
│
│  POST /api/chat/stream ──► LangGraph Agent
│                                │
│                    ┌───────────┴───────────┐
│                    ▼                       ▼
│             [Analytics Node]        [RAG Retriever]
│             Qdrant scroll()         Qdrant query_points()
│             filter video_id=A/B     top-5 semantic search
│                    │                       │
│                    └───────────┬───────────┘
│                                ▼
│                         [Generator Node]
│                         Gemini 2.5 Flash
│                                │
│                         StreamingResponse
│                         (word-by-word, 15ms)
```

---

## Tech Stack

### Backend
| Library | Version | Why I chose it |
|---------|---------|---------------|
| **FastAPI** | 0.136.3 | Async-native, automatic OpenAPI docs, StreamingResponse built-in. Would have taken twice as long in Flask. |
| **LangGraph** | 1.2.4 | Lets you model the agent as an actual state machine with typed edges instead of a monolithic chain. When I needed to add the analytics node later, I just wired a new edge — no refactor. |
| **LangChain** | 1.3.4 | Text splitters and message types. Minimal surface area usage — just `RecursiveCharacterTextSplitter` and `HumanMessage`. |
| **Google GenAI SDK** | 2.7.0 | Gemini `gemini-embedding-2` gives 3072-dim embeddings. Gemini 2.5 Flash for generation — free tier, fast, genuinely good at structured analytical answers. |
| **Qdrant** | 1.18.0 | Local Docker, no cloud costs, cosine similarity, typed filter API. Chose it over Chroma because Qdrant's `scroll()` with `Filter(must=[FieldCondition(...)])` lets the analytics node read metric payloads without a second database. |
| **yt-dlp** | 2026.3.17 | Handles YouTube metadata extraction + extractor args to bypass rigid runtime checks. |
| **youtube-transcript-api** | 1.2.4 | Direct CC/auto-caption access, falls back gracefully when subtitles are disabled. |
| **instaloader** | 4.15.1 | The only library that reliably returns `video_view_count` and `owner_profile.followers` for public Instagram reels without requiring an API key. |
| **uvicorn** | 0.49.0 | ASGI server with `--reload` for development. |

### Frontend
| Library | Why |
|---------|-----|
| **Next.js 16 (App Router)** | File-based routing, RSC-ready, `'use client'` for streaming. The `ReadableStream` reader approach for SSE just works. |
| **Vanilla CSS** | Full control. No Tailwind class soup. Design tokens via CSS custom properties. |
| **React hooks only** | `useState`, `useRef`, `useCallback`, `useEffect`. No Redux, no Zustand. The state surface is small enough that context + refs is totally sufficient. |

### Infrastructure
- **Qdrant** running in a local Docker container (`qdrant/qdrant`) — stores both vectors AND metadata in a single payload per chunk
- **MemorySaver** (LangGraph built-in) — in-memory checkpointer keyed by `thread_id` for cross-turn conversation memory

---

## Hurdles I Ran Into (And How I Solved Them)

### 1. The `video_id` payload overwrite that killed the entire analytics pipeline

This one took an embarrassingly long time to find. The scraper returns a dict with a `video_id` key — for YouTube it's the 11-char video ID, for Instagram the shortcode. When I built `ingest.py`, I stripped only `transcript` from the metadata dict before storing:

```python
video_meta_a = {k: v for k, v in yt_data.items() if k != "transcript"}
```

Then inside `store_video_chunks_in_db`, I did:

```python
payload.update(video_metadata)
```

The chunk already had `video_id = "A"` set by `chunk_transcript()`. But `payload.update()` runs **after** the chunk metadata is set — so the scraper's `video_id: "KHOSiaT4yC4"` silently overwrote the `"A"` label. Every chunk in Qdrant had the raw YouTube ID, not the label the analytics node was filtering on.

The analytics node did `Filter(must=[FieldCondition(key="video_id", match=MatchValue(value="A"))])` and found zero results. It returned "no data found" for every query.

Fix: exclude `"video_id"` from the metadata dict entirely and store it as `"raw_video_id"`.

```python
video_meta_a = {k: v for k, v in yt_data.items() if k not in ("transcript", "video_id")}
video_meta_a["raw_video_id"] = yt_data.get("video_id", "")
```

### 2. Qdrant's Python client doesn't accept raw dicts for filters

The initial `scroll()` call used a raw dictionary for `scroll_filter`:

```python
scroll_filter={"must": [{"key": "video_id", "match": {"value": label}}]}
```

This looks like valid JSON and the REST API accepts it. The Python client does not. It expects typed model objects:

```python
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

scroll_filter=Filter(
    must=[FieldCondition(key="video_id", match=MatchValue(value=label))]
)
```

Runtime validation error that only surfaces when the analytics node actually executes. Took catching the exception in the node's output to trace it back.

### 3. LangGraph `astream_events` doesn't capture raw GenAI SDK calls

My `generate_response` node called `gemini_client.aio.models.generate_content_stream` directly — raw Google GenAI SDK, not a LangChain chat model wrapper. The streaming endpoint used `astream_events(..., version="v2")` and listened for `on_chat_model_stream`. That event only fires for LangChain-native model wrappers. Zero events emitted. The chat just showed `...` forever and never updated.

Switched to `graph_agent.astream()` which yields node-level state updates regardless of what LLM you call inside. When the `generator` node finishes, I grab its output and word-stream it to the client at 15ms/word. Real token streaming would require wrapping Gemini in `langchain-google-genai` — that's a future improvement.

### 4. Python's `hash()` is non-deterministic and can return negative values

First version of `store_video_chunks_in_db` used:

```python
id = hash(chunk_id) % (10**10)
```

Python's `hash()` is randomized per process (since Python 3.3 by default) and can return negative integers. Qdrant rejects negative point IDs. Replaced with:

```python
id = uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id).int >> 64
```

`uuid5` is deterministic (same input always gives same UUID), always positive, and 64-bit — exactly what Qdrant wants.

### 5. Instagram doesn't expose view counts or follower counts to yt-dlp

Thought I had the Instagram scraper working when I saw likes and comments coming through. But `view_count` and `channel_follower_count` were always `None` — Instagram's API response simply omits these fields from the yt-dlp metadata endpoint for most reels.

Tried RapidAPI (requires a paid account once the trial ends). Tried Instagram's oEmbed endpoint (only returns title and thumbnail). Eventually found `instaloader` — a library that fetches the Instagram GraphQL payload directly for public posts and exposes `post.video_view_count`, `post.owner_profile.followers`, `post.likes`, etc. as first-class Python properties. No API key, no login required for public reels.

Scraper now tries instaloader first, falls back to yt-dlp, then RapidAPI if a key is configured, then a mock struct that at least keeps the app running.

### 6. Gemini rejects conversations that don't end with a `user` turn

The `generate_response` node builds a message list from the full LangGraph state. If the last message in state was an assistant reply (from a previous turn), the content list ended with `role="model"`. Gemini's API requires the last item to be `role="user"`.

Added a guard:

```python
if not formatted_contents or formatted_contents[-1]["role"] != "user":
    formatted_contents.append({
        "role": "user",
        "parts": [{"text": "Please answer based on the context above."}]
    })
```

### 7. Flex children ignore `overflow: auto` without `min-height: 0`

Added individual scrollbars to both the left panel and the chat messages area. The CSS looked correct — `flex: 1; overflow-y: auto` on `.chat-messages`. But the panel kept expanding to fit its content instead of scrolling.

The issue: flex children default to `min-height: auto`, which means "grow to fit content." This overrides any `overflow` constraint. Setting `min-height: 0` tells the item it is bounded by the parent — only then does `overflow: auto` activate and the scrollbar appear.

---

## Cost & Scalability at 1,000 Creators/Day

### What actually costs money

| Resource | Cost driver | Per-creator cost |
|----------|------------|-----------------|
| **Gemini embeddings** (`gemini-embedding-2`) | ~15–30 chunks per video × 2 videos = ~60 API calls | $0.000025/1K chars → ~$0.001 per creator |
| **Gemini 2.5 Flash** (generation) | Per query, not per ingest | ~$0.0001/query |
| **Qdrant** | Local Docker = $0. Qdrant Cloud starts at ~$25/month for 1M vectors | ~$0 (local), ~$0.003/creator (cloud) |
| **Scrapers** | yt-dlp + instaloader = $0 | $0 |
| **Compute** | A single uvicorn worker handles the async embedding pipeline | ~$0.002/creator on a $50/month VM |

**Rough total: ~$1–3/day at 1,000 creators, almost entirely from embedding API calls.**

### Why this is the right architecture for scale

- **Qdrant as dual store**: Every chunk carries full metadata in its payload. The analytics node reads metric data directly from Qdrant without a second database (no Redis, no Postgres for metrics). At 1,000 creators/day that's one less database to pay for and one less failure point.
- **LangGraph conditional routing**: The router decides at query time whether to hit the vector index (semantic) or scroll by filter (analytics). Analytics queries skip the embedding step entirely — zero Gemini API calls, just a Qdrant scroll.
- **Gemini Flash, not Pro**: 2.5 Flash is 10–15× cheaper than Pro and fast enough for this use case. Analytical summaries don't need deep reasoning — they need structured, accurate recall.
- **Local Qdrant first**: For a single-machine deployment handling ~1,000 creators/day, local Qdrant with persistent storage is free. Migration to Qdrant Cloud is a one-line URL change.

### The real bottleneck at scale

Embedding is synchronous per chunk. At 30 chunks × 2 videos = 60 Gemini API calls sequentially per ingest, each taking ~200ms, that's ~12 seconds per creator. At 1,000 creators/day you'd want to parallelize with `asyncio.gather()` across chunk batches. The architecture supports it — it's a code change, not a redesign.

---

## Future Improvements

**Short-term (low effort, high impact):**

- **Batch embedding**: Replace the sequential `for chunk in chunks` loop with `asyncio.gather()` to embed all chunks in parallel. Should cut ingest time from ~12s to ~2s per creator.
- **Real token streaming**: Wrap Gemini in `langchain-google-genai`'s `ChatGoogleGenerativeAI` so `astream_events` fires `on_chat_model_stream`. Currently tokens stream word-by-word after the full LLM call completes.
- **Transcript audio fallback**: When YouTube CC is disabled, use Whisper (via `faster-whisper`) to transcribe the audio directly. Right now it just logs an error string into the transcript field.
- **Instagram caption ≠ transcript**: Instagram reels don't have CC. The caption is a decent proxy but not the same thing. A proper fix is downloading the audio via yt-dlp and running it through Whisper.

**Medium-term:**

- **Persistent session store**: `MemorySaver` is in-process and resets on server restart. Swap it for `AsyncPostgresSaver` (LangGraph built-in) for durable conversation history across sessions.
- **Multi-video support**: Right now the schema is hardcoded to Video A and Video B. Generalize to N videos with UUIDs as labels and a collection-per-session approach.
- **Trend comparison over time**: Store multiple ingests per creator with timestamps. The analytics node could then answer "has engagement gone up over the last 10 videos?" — actual trend analysis rather than single-video snapshots.
- **Export to PDF/CSV**: The analytics node already has all the data formatted. A `/api/export` route that renders it into a PDF report would make this a proper creator audit tool.

**Long-term:**

- **Hook detection**: Fine-tune a small classifier on the first 30 seconds of transcripts to score "hook quality" — what percentage of top-performing videos use a question hook vs. a statement hook vs. a shock stat. Feed that back into the RAG context.
- **Competitor benchmarking**: Ingest a creator's last 10 videos against a competitor's last 10 and let the agent identify structural differences in what performed well.
- **Thumbnail analysis**: Add a vision model pass on the video thumbnail to analyze composition, text density, and contrast — all of which correlate with CTR. Gemini's multimodal capabilities make this a one-node addition to the graph.

---

## Running Locally

### Prerequisites
- Python 3.10+
- Node.js 18+
- Docker (for Qdrant)
- A Gemini API key (free at [ai.google.dev](https://ai.google.dev))

### 1. Start Qdrant
```bash
docker run -p 6333:6333 -v ./qdrant_storage:/qdrant/storage qdrant/qdrant
```

### 2. Backend
```bash
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1      # Windows
# source venv/bin/activate       # Mac/Linux

pip install -r requirements.txt
pip install instaloader          # not in requirements.txt yet
```

Create `backend/.env`:
```
GEMINI_API_KEY=your_key_here
RAPIDAPI_KEY=optional_if_you_have_one
```

```bash
uvicorn app.main_server:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000**.

### 4. Using the app
1. Paste a YouTube URL in field **A**
2. Paste an Instagram Reel URL in field **B** (must be a public reel)
3. Click **Analyze Videos** — ingest takes 15–30 seconds depending on transcript length
4. Ask the chatbot anything about either video

---

## Project Structure

```
video-analysis-RAG-chatbot/
├── backend/
│   ├── app/
│   │   ├── agent.py              # LangGraph state machine (router + retriever + analytics + generator)
│   │   ├── main_server.py        # FastAPI app, /api/ingest, /api/chat/stream, /api/health
│   │   ├── vector_pipeline.py    # Gemini embeddings + Qdrant upsert
│   │   ├── api/
│   │   │   └── ingest.py         # Ingest route: scrape → chunk → embed → store
│   │   └── scrapers/
│   │       ├── youtube.py        # yt-dlp + youtube-transcript-api
│   │       └── instagram.py      # instaloader → yt-dlp → RapidAPI → mock
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   └── src/app/
│       ├── page.js               # Full single-page UI (ingest form + video cards + streaming chat)
│       ├── globals.css           # Design system (tokens, layout, components)
│       └── layout.js
│
└── qdrant_storage/               # Qdrant persists vectors here between runs
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | ✅ Yes | Gemini API key from [ai.google.dev](https://ai.google.dev). Used for both embeddings and generation. |
| `RAPIDAPI_KEY` | ❌ No | RapidAPI key for `instagram-scraper-api2`. Only used if instaloader fails. |

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ingest` | POST | `{ youtube_url, instagram_url }` → scrape, embed, store both videos |
| `/api/chat/stream` | POST | `{ message, thread_id }` → streaming text response from the LangGraph agent |
| `/api/health` | GET | `{ status, database_connected }` |
| `/docs` | GET | Auto-generated FastAPI Swagger UI |
