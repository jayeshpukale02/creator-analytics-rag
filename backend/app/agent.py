import os
from typing import Annotated, TypedDict, List
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from google import genai
from qdrant_client import QdrantClient
from app.vector_pipeline import get_embedding, COLLECTION_NAME

# Initialize connection clients
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
qdrant_client = QdrantClient(url="http://localhost:6333")

# 1. Define the unified state memory layout
class AgentState(TypedDict):
    # add_messages tells LangGraph to append new chat entries to history automatically
    messages: Annotated[list, add_messages]
    video_context: str
    target_video_id: SyntaxError