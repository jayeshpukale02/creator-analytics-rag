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

    # 2. Node: The Vector Search Context Retriever
def retrieve_semantic_context(state: AgentState):
    """Queries Qdrant to find relevant text transcript frames using Gemini vectors."""
    # Grab the last message the user sent
    user_query = state["messages"][-1].content
    
    # Vectorize the user prompt using our Day 2 engine layout
    query_vector = get_embedding(user_query)
    
    # Query our local Docker container for the top 3 matches
    search_results = qdrant_client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=3
    )
    
    # Concatenate the matching payload hits into a single context paragraph
    retrieved_text = "\n".join([hit.payload["page_content"] for hit in search_results])
    
    # Pass the context string directly forward through the graph state
    return {"video_context": retrieved_text}


# 3. Node: The LLM Responder Engine
def generate_response(state: AgentState):
    """Synthesizes the final answer using the compiled background memory context."""
    conversation_history = state["messages"]
    context = state.get("video_context", "No direct vector text matches found.")
    
    system_instruction = (
        f"You are an expert DevOps and Social Media analytics engine. "
        f"Answer the user's inquiry accurately using only the extracted video context below.\n\n"
        f"--- VIDEO TEXT DATA CONTEXT ---\n{context}\n--------------------------------\n"
        f"Be direct, structured, and prioritize analytical clarity."
    )
    
    # Package messages for the modern Google GenAI SDK syntax format
    formatted_contents = []
    for msg in conversation_history:
        # Map roles cleanly ('user' or 'model')
        role = "user" if msg.type == "human" else "model"
        formatted_contents.append({"role": role, "parts": [{"text": msg.content}]})
        
    # Execute call using Gemini 2.5 Flash for hyper-fast execution speeds
    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=formatted_contents,
        config={"system_instruction": system_instruction}
    )
    
    # Return the text as a clean assistant reply message node string
    return {"messages": [{"role": "assistant", "content": response.text}]}

    # 4. Construct and compile the network layout graph
workflow = StateGraph(AgentState)

# Add our custom processing steps
workflow.add_node("retriever", retrieve_semantic_context)
workflow.add_node("generator", generate_response)

# Connect the paths
workflow.add_edge(START, "retriever")
workflow.add_edge("retriever", "generator")
workflow.add_edge("generator", END)

# Compile graph into a standard executable agent instance
graph_agent = workflow.compile()