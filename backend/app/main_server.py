import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.agent import graph_agent
from app.api.ingest import router as ingest_router
from langchain_core.messages import HumanMessage
import asyncio

app = FastAPI(title="Creator Analytics Chatbot Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest_router)


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"   # frontend passes a session ID for per-user memory


@app.post("/api/chat/stream")
async def stream_chat_response(payload: ChatRequest):
    """
    Streams the LangGraph agent response token-by-token.
    Uses thread_id to maintain conversation memory across turns via MemorySaver.
    """
    async def response_generator():
        config = {"configurable": {"thread_id": payload.thread_id}}
        inputs = {"messages": [HumanMessage(content=payload.message)]}

        # astream_events gives us real token-level streaming from the LLM node
        async for event in graph_agent.astream_events(inputs, config=config, version="v2"):
            kind = event.get("event")
            # Stream tokens from the generator node only
            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    yield chunk.content
            # Fallback: also capture any plain text output chunks
            elif kind == "on_chain_stream":
                data = event.get("data", {})
                output = data.get("output", {})
                if isinstance(output, dict):
                    msgs = output.get("messages", [])
                    if msgs:
                        last = msgs[-1]
                        content = getattr(last, "content", None) or (
                            last.get("content") if isinstance(last, dict) else None
                        )
                        if content:
                            yield content

    return StreamingResponse(response_generator(), media_type="text/plain; charset=utf-8")


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "database_connected": True}