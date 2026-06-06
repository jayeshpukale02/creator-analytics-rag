import os
import uuid
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from google import genai
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue
from app.vector_pipeline import get_embedding, COLLECTION_NAME

# Initialize clients
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
qdrant_client = QdrantClient(url="http://localhost:6333")


# ─── 1. State ──────────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    video_context: str
    target_video_id: str


# ─── 2. RAG Retriever Node ─────────────────────────────────────────────────────
def retrieve_semantic_context(state: AgentState):
    """Queries Qdrant for the top-5 semantically closest transcript chunks."""
    user_query = state["messages"][-1].content
    query_vector = get_embedding(user_query)

    try:
        search_results = qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=5
        )
        context_parts = []
        for hit in search_results.points:
            p = hit.payload
            tag = f"[Source: Video {p.get('video_id', '?')} | Chunk {p.get('chunk_id', '?')}]"
            context_parts.append(f"{tag}\n{p.get('page_content', '')}")
        retrieved_text = "\n\n".join(context_parts) if context_parts else "No relevant chunks found."
    except Exception as e:
        retrieved_text = f"Vector search failed: {e}"

    return {"video_context": retrieved_text}


# ─── 3. Analytics Node ─────────────────────────────────────────────────────────
def fetch_video_analytics(state: AgentState):
    """
    Pulls live engagement metrics for Video A and B directly from Qdrant payloads.
    Uses the typed Filter / FieldCondition API — NOT raw dicts (those crash).
    """
    lines = ["--- REAL VIDEO ANALYTICS (from Qdrant) ---"]

    for label in ["A", "B"]:
        try:
            # Correct Qdrant Python client filter syntax
            scroll_results, _ = qdrant_client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=Filter(
                    must=[FieldCondition(key="video_id", match=MatchValue(value=label))]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False
            )
        except Exception as e:
            lines.append(f"\nVideo {label}: Qdrant scroll error — {e}")
            continue

        if scroll_results:
            p = scroll_results[0].payload
            views    = p.get("views", 0)
            likes    = p.get("likes", 0)
            comments = p.get("comments", 0)
            eng      = p.get("engagement_rate", 0.0)
            followers = p.get("follower_count", 0)
            hashtags  = p.get("hashtags", [])

            lines.append(
                f"\nVideo {label} ({p.get('platform','?').upper()} | @{p.get('creator','?')}):\n"
                f"  Views: {views:,} | Likes: {likes:,} | Comments: {comments:,}\n"
                f"  Engagement Rate: {eng}%\n"
                f"  Followers: {followers:,} | Duration: {p.get('duration',0)}s\n"
                f"  Upload Date: {p.get('upload_date','N/A')}\n"
                f"  Hashtags: {', '.join(hashtags[:5]) if hashtags else 'None'}"
            )
        else:
            lines.append(f"\nVideo {label}: No data found — ingest videos first.")

    return {"video_context": "\n".join(lines)}


# ─── 4. LLM Generator Node ─────────────────────────────────────────────────────
async def generate_response(state: AgentState):
    """Synthesizes the final answer from retrieved context + conversation history."""
    context = state.get("video_context", "No context retrieved.")

    system_instruction = (
        "You are an expert Social Media Analytics AI. "
        "Answer ONLY using the video data context below. "
        "Cite sources using the [Source: Video X | Chunk Y] tags in the context.\n\n"
        f"--- VIDEO DATA CONTEXT ---\n{context}\n--------------------------\n"
        "Be concise, structured, and analytically sharp."
    )

    # Build content list — only include user messages and prior assistant replies.
    # The last message must be role='user' for Gemini; the system prompt carries context.
    formatted_contents = []
    for msg in state["messages"]:
        role = "user" if msg.type == "human" else "model"
        text = msg.content.strip()
        if not text:
            continue
        formatted_contents.append({"role": role, "parts": [{"text": text}]})

    # Gemini requires the conversation to end with a user turn
    if not formatted_contents or formatted_contents[-1]["role"] != "user":
        formatted_contents.append({
            "role": "user",
            "parts": [{"text": "Please answer based on the context above."}]
        })

    try:
        response_stream = await gemini_client.aio.models.generate_content_stream(
            model="gemini-2.5-flash",
            contents=formatted_contents,
            config={"system_instruction": system_instruction}
        )
        full_text = ""
        async for chunk in response_stream:
            if chunk.text:
                full_text += chunk.text
    except Exception as e:
        full_text = f"LLM error: {e}"

    return {"messages": [{"role": "assistant", "content": full_text}]}


# ─── 5. Router ─────────────────────────────────────────────────────────────────
def route_user_intent(state: AgentState) -> str:
    """Routes to analytics node or RAG retriever based on query keywords."""
    query = state["messages"][-1].content.lower()
    analytics_keywords = [
        "views", "likes", "comments", "engagement", "rate", "stats",
        "metrics", "analytics", "follower", "subscribers", "average",
        "performance", "who is", "creator", "upload date", "duration"
    ]
    if any(kw in query for kw in analytics_keywords):
        print("ROUTER: → [Analytics Engine]")
        return "analytics"
    print("ROUTER: → [RAG Retriever]")
    return "retriever"


# ─── 6. Build Graph ────────────────────────────────────────────────────────────
workflow = StateGraph(AgentState)
workflow.add_node("retriever", retrieve_semantic_context)
workflow.add_node("analytics", fetch_video_analytics)
workflow.add_node("generator", generate_response)

workflow.add_conditional_edges(START, route_user_intent, {
    "analytics": "analytics",
    "retriever": "retriever",
})
workflow.add_edge("analytics", "generator")
workflow.add_edge("retriever", "generator")
workflow.add_edge("generator", END)

# MemorySaver enables cross-turn conversation memory via thread_id
memory = MemorySaver()
graph_agent = workflow.compile(checkpointer=memory)