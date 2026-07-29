from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from models.database import get_db, DocumentChunk
from models.database import ProjectFile, ProjectReference
from services.vector_store import VectorStore
from routers.agent import RAG_FALLBACK_THRESHOLD
from routers.forms import openai_client, VISION_MODEL
from typing import Optional
import json

router = APIRouter()

class AskQuery(BaseModel):
    question: str
    top_k: int = 5
    source_type: Optional[str] = None

@router.get("/")
def search(
    q: str = Query(..., description="The query string to search for"),
    top_k: int = Query(5, description="Number of results to return"),
    source_type: Optional[str] = Query(None, description="Filter by source_type (project_file or document)"),
    db: Session = Depends(get_db)
):
    try:
        vs = VectorStore()
    except Exception as e:
        raise HTTPException(status_code=503, detail="Vector search model is not loaded yet. Please try again in a few moments.")
        
    results = vs.search(db, query=q, top_k=top_k, source_type=source_type)
    
    # Add download/view links based on source_type
    for r in results:
        if r["source_type"] == "project_file":
            r["view_url"] = f"/api/project-files/{r['source_id']}/view"
            r["download_url"] = f"/api/project-files/{r['source_id']}/download"
        elif r["source_type"] == "document":
            r["view_url"] = f"/api/documents/download/{r['source_id']}"
            r["download_url"] = f"/api/documents/download/{r['source_id']}"
        elif r["source_type"] == "reference":
            r["view_url"] = ""
            r["download_url"] = ""
            
    return {"results": results}

@router.post("/ask")
def ask_question(query: AskQuery, db: Session = Depends(get_db)):
    if len(query.question) > 500:
        raise HTTPException(status_code=400, detail="Question is too long. Max length is 500 characters.")
        
    try:
        vs = VectorStore()
    except Exception as e:
        raise HTTPException(status_code=503, detail="Vector search model is not loaded yet. Please try again in a few moments.")

    # Multi-query expansion
    try:
        expansion_prompt = (
            "You are an AI assistant. The user provides a search query. Your task is to generate 3 alternative versions of this query "
            "to improve document retrieval in a vector database. Fix typos and use synonyms (e.g., turnover -> revenue, profit). "
            "Return ONLY a JSON array of 3 string queries."
        )
        expansion_resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": expansion_prompt},
                {"role": "user", "content": f"Query: {query.question}\n\nReturn JSON like: {{\"queries\": [\"query1\", \"query2\", \"query3\"]}}"}
            ]
        )
        expanded_json = json.loads(expansion_resp.choices[0].message.content)
        search_queries = [query.question] + expanded_json.get("queries", [])
    except Exception as e:
        print("Query expansion failed:", e)
        search_queries = [query.question]

    all_results = []
    seen_ids = set()
    
    # Search for all generated queries and pool the results
    for q in search_queries:
        res = vs.search(db, query=q, top_k=query.top_k, source_type=query.source_type)
        for r in res:
            if r["chunk_id"] not in seen_ids:
                seen_ids.add(r["chunk_id"])
                all_results.append(r)
                
    # Sort by score and take the top N (e.g., top 15 overall)
    all_results.sort(key=lambda x: x["score"], reverse=True)
    all_results = all_results[:15]
    
    # Filter for minimum relevance (lowered for smaller chunks)
    relevant_chunks = [r for r in all_results if r["score"] > 0.20]
    
    if not relevant_chunks:
        return {
            "answer": None,
            "message": "No relevant information found in your documents.",
            "sources": []
        }
        
    # Build context string
    context_parts = []
    for i, chunk in enumerate(relevant_chunks):
        context_text = chunk.get("parent_text") or chunk["text"]
        context_parts.append(f"--- Source [{i+1}] ---\n{context_text}")
    context_str = "\n\n".join(context_parts)
    
    system_prompt = (
        "You are a helpful AI assistant. Answer the user's question ONLY using the provided document excerpts as context. "
        "If the answer isn't in the provided context, say so. Do not use outside knowledge. "
        "Cite which source document each part of your answer comes from using the [X] tags provided."
    )
    
    try:
        completion = openai_client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context excerpts:\n{context_str}\n\nQuestion: {query.question}"}
            ]
        )
        answer = completion.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating answer: {str(e)}")

    sources_out = []
    for r in relevant_chunks:
        name = "Unknown File"
        link = ""
        if r["source_type"] == "project_file":
            pf = db.query(ProjectFile).filter(ProjectFile.id == r["source_id"]).first()
            if pf:
                name = pf.filename or pf.name
                link = f"/api/project-files/{r['source_id']}/download"
        elif r["source_type"] == "document":
            doc = db.query(ProjectFile).filter(ProjectFile.id == r["source_id"], ProjectFile.source_module == "document").first()
            if doc:
                name = doc.filename or doc.name
                link = f"/api/documents/download/{r['source_id']}"
        elif r["source_type"] == "reference":
            ref = db.query(ProjectReference).filter(ProjectReference.id == r["source_id"]).first()
            if ref:
                name = f"Reference: {ref.project_name}"
                link = ""
                
        sources_out.append({
            "source_type": r["source_type"],
            "source_id": r["source_id"],
            "name": name,
            "sheet_or_page": r["sheet_or_page"],
            "score": r["score"],
            "link": link,
            "excerpt": r["text"][:200] + "..." if len(r["text"]) > 200 else r["text"]
        })
        
    return {
        "answer": answer,
        "sources": sources_out
    }
