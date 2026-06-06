from app.agent import graph_agent
from langchain_core.messages import HumanMessage

def test_agent_query(query_text: str):
    print(f"\nUser Query: '{query_text}'")
    initial_inputs = {"messages": [HumanMessage(content=query_text)]}
    output_state = graph_agent.invoke(initial_inputs)
    print("--- 🛰️ AGENT RESPONSE ---")
    print(output_state["messages"][-1].content)
    print("="*50)

if __name__ == "__main__":
    print("--- DYNAMIC AGENT APP ONLINE  ---")
    
    # Test Run Path A: Should trigger the RAG Vector Retrieval Node
    test_agent_query("What focus or main message does Rick Astley convey in the video transcript?")
    
    # Test Run Path B: Should trigger the Analytics Data Node
    test_agent_query("Can you give me a breakdown of my profile view metrics and statistics?")