from langchain_text_splitters import RecursiveCharacterTextSplitter

def chunk_transcript(transcript_text: str, video_id: str, platform: str) -> list[dict]:
    """
    Splits a raw transcript string into tightly optimized semantic chunks 
    and attaches mandatory video metadata to every single chunk.
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=50,
        length_function=len,
        separators=["\n\n", "\n", " ", ""]
    )
    
    # Split the document text
    raw_chunks = text_splitter.split_text(transcript_text)
    
    processed_chunks = []
    for index, text in enumerate(raw_chunks):
        # Build the exact chunk document structure needed for the Vector DB
        processed_chunks.append({
            "text": text,
            "metadata": {
                "chunk_id": f"{video_id}_chunk_{index}",
                "video_id": video_id,
                "platform": platform,
                "source_position": index
            }
        })
        
    return processed_chunks