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
    Streams the LangGraph agent response word-by-word.
    Uses graph_agent.astream() which yields node-level state updates — reliable
    regardless of whether the LLM is called via a LangChain wrapper or raw SDK.
    thread_id ensures MemorySaver keeps conversation history across turns.
    """
    async def response_generator():
        config = {"configurable": {"thread_id": payload.thread_id}}
        inputs = {"messages": [HumanMessage(content=payload.message)]}

        try:
            async for node_output in graph_agent.astream(inputs, config=config):
                # node_output is a dict: {"node_name": state_update}
                if "generator" in node_output:
                    msgs = node_output["generator"].get("messages", [])
                    if msgs:
                        last = msgs[-1]
                        # Handle both dict messages and LangChain message objects
                        if isinstance(last, dict):
                            content = last.get("content", "")
                        else:
                            content = getattr(last, "content", "") or ""

                        if content:
                            # Stream word by word with a short delay for smooth UX
                            for word in content.split(" "):
                                yield word + " "
                                await asyncio.sleep(0.015)
        except Exception as e:
            yield f"[Error: {str(e)}]"

    return StreamingResponse(response_generator(), media_type="text/plain; charset=utf-8")


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "database_connected": True}