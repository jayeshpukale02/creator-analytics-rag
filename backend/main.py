from app.agent import graph_agent
from langchain_core.messages import HumanMessage

if __name__ == "__main__":
    print("--- 🧠 DAY 3 STATEFUL AGENT RUNNING 🧠 ---")
    
    # Define a test question about Rick Astley's transcript we indexed yesterday
    test_query = "What is the core message or focus of the video?"
    
    print(f"User Query: {test_query}\n")
    
    # Feed the message into the state graph dictionary
    initial_inputs = {"messages": [HumanMessage(content=test_query)]}
    
    # Run the execution graph top to bottom
    output_state = graph_agent.invoke(initial_inputs)
    
    # Extract the last message response from the graph payload
    final_reply = output_state["messages"][-1].content
    print("--- 🛰️ AGENT RESPONSE ---")
    print(final_reply)