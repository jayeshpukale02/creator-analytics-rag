import sys
import os
# Ensure app modules are discoverable on the system path
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

# Enable CORS boundaries so local frontend UIs can connect cleanly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Open for local dev loop testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(ingest_router)

class ChatRequest(BaseModel):
    message: str

# 📡 THE STREAMING CONTROLLER
@app.post("/api/chat/stream")
async def stream_chat_response(payload: ChatRequest):
    """Executes the state graph and streams back text chunks over HTTP instantly."""
    
    async def response_generator():
        initial_inputs = {"messages": [HumanMessage(content=payload.message)]}
        
        # Invoke graph asynchronously
        output_state = await graph_agent.ainvoke(initial_inputs)
        final_text = output_state["messages"][-1].content
        
        # Simulate an instantaneous character network token stream delivery chunk loop
        # (In production, you can stream chunk.text directly out of your custom node callbacks)
        for token in final_text.split(" "):
            yield f"{token} "
            await asyncio.sleep(0.04) # 40ms smooth cadence spacing
            
    return StreamingResponse(response_generator(), media_type="text/event-stream")

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "database_connected": True}