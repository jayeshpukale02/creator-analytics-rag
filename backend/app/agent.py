import os
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from google import genai
from qdrant_client import QdrantClient
from app.vector_pipeline import get_embedding, COLLECTION_NAME

# Initialize connection clients
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
qdrant_client = QdrantClient(url="http://localhost:6333")


class AgentState(TypedDict):
    # add_messages tells LangGraph to append new chat entries to history automatically
    messages: Annotated[list, add_messages]
    video_context: str
    target_video_id: str   # FIX: was erroneously set to `SyntaxError` (a Python exception class)


def retrieve_semantic_context(state: AgentState):
    """Queries Qdrant to find relevant transcript chunks using Gemini embeddings."""
    user_query = state["messages"][-1].content

    # Vectorize the user prompt
    query_vector = get_embedding(user_query)

    # Query local Qdrant container for top 5 semantic matches
    search_results = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=5
    )

    # Build context string with source citations (video_id + chunk_id) per chunk
    context_parts = []
    for hit in search_results.points:
        payload = hit.payload
        source_tag = f"[Source: Video {payload.get('video_id', '?')} | Chunk {payload.get('chunk_id', '?')}]"
        context_parts.append(f"{source_tag}\n{payload['page_content']}")

    retrieved_text = "\n\n".join(context_parts) if context_parts else "No relevant chunks found in the vector store."

    return {"video_context": retrieved_text}


# ─── 3. Node: Analytics Engine ─────────────────────────────────────────────────
def fetch_video_analytics(state: AgentState):
    """
    Pulls real engagement metrics for both videos directly from Qdrant payload metadata.
    Searches for chunks tagged with video_id 'A' and 'B' and reads their stored metadata.
    """
    results = {}

    for label in ["A", "B"]:
        # Scroll through Qdrant to find metadata payloads tagged with this video_id label
        scroll_results, _ = qdrant_client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter={
                "must": [{"key": "video_id", "match": {"value": label}}]
            },
            limit=1,
            with_payload=True,
            with_vectors=False
        )

        if scroll_results:
            payload = scroll_results[0].payload
            results[label] = {
                "creator":         payload.get("creator", "Unknown"),
                "platform":        payload.get("platform", "Unknown"),
                "views":           payload.get("views", 0),
                "likes":           payload.get("likes", 0),
                "comments":        payload.get("comments", 0),
                "engagement_rate": payload.get("engagement_rate", 0.0),
                "follower_count":  payload.get("follower_count", 0),
                "duration":        payload.get("duration", 0),
                "upload_date":     payload.get("upload_date", "N/A"),
                "hashtags":        payload.get("hashtags", []),
            }
        else:
            results[label] = None

    lines = ["--- REAL VIDEO ANALYTICS (from Qdrant) ---"]
    for label, data in results.items():
        if data:
            lines.append(
                f"\nVideo {label} ({data['platform'].upper()} | @{data['creator']}):\n"
                f"  Views: {data['views']:,} | Likes: {data['likes']:,} | Comments: {data['comments']:,}\n"
                f"  Engagement Rate: {data['engagement_rate']}%\n"
                f"  Followers: {data['follower_count']:,} | Duration: {data['duration']}s\n"
                f"  Upload Date: {data['upload_date']}\n"
                f"  Hashtags: {', '.join(data['hashtags'][:5]) if data['hashtags'] else 'None'}"
            )
        else:
            lines.append(f"\nVideo {label}: No metadata found — video may not have been ingested yet.")

    formatted_metrics = "\n".join(lines)
    return {"video_context": formatted_metrics}


# ─── 4. Node: LLM Response Generator ──────────────────────────────────────────
async def generate_response(state: AgentState):
    """Synthesizes the final answer using retrieved context and conversation history."""
    conversation_history = state["messages"]
    context = state.get("video_context", "No context retrieved.")

    system_instruction = (
        "You are an expert Social Media Analytics AI. "
        "Answer the user's question using ONLY the video data context provided below. "
        "Always cite your sources using the [Source: Video X | Chunk Y] tags present in the context.\n\n"
        f"--- VIDEO DATA CONTEXT ---\n{context}\n--------------------------\n"
        "Be concise, structured, and analytically clear."
    )

    # Package conversation history for Gemini SDK format
    formatted_contents = []
    for msg in conversation_history:
        role = "user" if msg.type == "human" else "model"
        formatted_contents.append({"role": role, "parts": [{"text": msg.content}]})

    # Call Gemini async streaming
    response_stream = await gemini_client.aio.models.generate_content_stream(
        model="gemini-2.5-flash",
        contents=formatted_contents,
        config={"system_instruction": system_instruction}
    )

    full_text = ""
    async for chunk in response_stream:
        if chunk.text:
            full_text += chunk.text

    return {"messages": [{"role": "assistant", "content": full_text}]}


# ─── 5. Conditional Router ─────────────────────────────────────────────────────
def route_user_intent(state: AgentState) -> str:
    """Routes the query to the analytics node or RAG retriever based on intent keywords."""
    user_query = state["messages"][-1].content.lower()

    analytics_keywords = [
        "views", "likes", "comments", "engagement", "rate", "stats",
        "metrics", "analytics", "follower", "subscribers", "average",
        "performance", "who is", "creator", "upload date", "duration"
    ]

    if any(keyword in user_query for keyword in analytics_keywords):
        print("ROUTER: → [Analytics Engine]")
        return "analytics"

    print("ROUTER: → [RAG Vector Retriever]")
    return "retriever"


# ─── 6. Build & Compile the LangGraph ─────────────────────────────────────────
workflow = StateGraph(AgentState)

# Register all functional nodes
workflow.add_node("retriever", retrieve_semantic_context)
workflow.add_node("analytics", fetch_video_analytics)
workflow.add_node("generator", generate_response)

# Entry point: route based on user intent
workflow.add_conditional_edges(
    START,
    route_user_intent,
    {
        "analytics": "analytics",
        "retriever": "retriever",
    }
)

# Both branches feed into the LLM generator
workflow.add_edge("analytics", "generator")
workflow.add_edge("retriever", "generator")
workflow.add_edge("generator", END)

# Single compiled agent instance used by the FastAPI server
graph_agent = workflow.compile()