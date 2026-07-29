import json
import logging
import numpy as np
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from models.database import DocumentChunk

logger = logging.getLogger(__name__)

class VectorStore:
    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VectorStore, cls).__new__(cls)
            cls._instance._load_model()
        return cls._instance

    def _load_model(self):
        if self._model is None:
            logger.info("Loading sentence-transformers model 'all-MiniLM-L6-v2'...")
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Model loaded successfully.")

    def embed_and_store(self, db: Session, chunk_id: int, text: str):
        try:
            chunk = db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
            if chunk:
                embedding = self._model.encode(text).tolist()
                chunk.embedding = embedding
                db.commit()
        except Exception as e:
            logger.error(f"Error embedding chunk {chunk_id}: {e}")

    def embed_missing(self, db: Session):
        try:
            # Fetch all chunks and filter in memory, because SQLite JSON IS NULL can be tricky
            all_chunks = db.query(DocumentChunk).all()
            chunks = [c for c in all_chunks if c.embedding is None or c.embedding == 'null']
            
            if not chunks:
                return

            logger.info(f"Embedding {len(chunks)} missing chunks...")
            
            # Batch process in size of 32
            batch_size = 32
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]
                texts = [c.text for c in batch]
                
                embeddings = self._model.encode(texts)
                for c, emb in zip(batch, embeddings):
                    c.embedding = emb.tolist()
                
                db.commit()
                logger.info(f"Embedded batch {i//batch_size + 1}")
        except Exception as e:
            logger.error(f"Error in embed_missing: {e}")

    def search(self, db: Session, query: str, top_k: int = 5, source_type: Optional[str] = None) -> List[Dict]:
        try:
            query_embedding = self._model.encode(query)
            
            q = db.query(DocumentChunk).filter(DocumentChunk.embedding != None)
            if source_type:
                q = q.filter(DocumentChunk.source_type == source_type)
                
            candidates = q.all()
            if not candidates:
                return []
                
            results = []
            for c in candidates:
                if c.embedding:
                    emb_val = c.embedding
                    if isinstance(emb_val, str):
                        import json
                        emb_val = json.loads(emb_val)
                    emb = np.array(emb_val, dtype=float)
                    # Cosine similarity
                    score = np.dot(query_embedding, emb) / (np.linalg.norm(query_embedding) * np.linalg.norm(emb))
                    results.append({
                        "chunk_id": c.id,
                        "source_type": c.source_type,
                        "source_id": c.source_id,
                        "sheet_or_page": c.sheet_or_page,
                        "text": c.text,
                        "parent_text": c.parent_text,
                        "score": float(score)
                    })
                    
            # Sort by score descending
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:top_k]
        except Exception as e:
            logger.error(f"Error searching vector store: {e}")
            return []
