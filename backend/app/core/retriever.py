import chromadb
import json
import re
from functools import lru_cache
from pathlib import Path
from rank_bm25 import BM25Okapi

CHROMA_DIR = "data/processed/chroma_db/"
chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)

def clean_metadata(metadata):
    return {
        key: value
        for key, value in metadata.items()
        if value is not None
    }

class Retriever:
    def __init__(self, child_token_path: str):
        global chroma_client
        self.chroma_collec = chroma_client.get_or_create_collection(name="compliance_nexus_chunks")
        self.child_token_path = Path(child_token_path)

        self.json_data = self._load_child_chunks()
        self.bm25 = self._build_bm25(self.json_data)
        self.child_to_parent = {
            child["child_id"]: child["parent_id"]
            for child in self.json_data
        }

        with Path("data/processed/parent_chunks.json").open(
            "r", encoding="utf-8"
        ) as file:
            parent_chunks = json.load(file)

        self.parent_by_id = {
            parent["parent_id"]: parent
            for parent in parent_chunks
        }

    def _load_child_chunks(self):
        with self.child_token_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    @staticmethod
    def _tokenize(text: str):
        return re.findall(r"\b\w+\b", text.lower())

    def _build_bm25(self, child_chunks):
        tokenized_contents = [
            self._tokenize(chunk["text_content"])
            for chunk in child_chunks
        ]
        return BM25Okapi(tokenized_contents)
    
    def chroma_collection(self):
        """Upsert child chunks during ingestion, not during query handling."""
        ind = []
        metadata = []
        docs = []

        for tok in self.json_data:
            ind.append(tok["child_id"])

            chunk_metadata = clean_metadata(tok["metadata"])
            chunk_metadata["parent_id"] = tok["parent_id"]
            metadata.append(chunk_metadata)

            docs.append(tok["text_content"])

        self.chroma_collec.upsert(
            ids=ind,
            metadatas=metadata,
            documents=docs
        )
    
    def best_matching25(self):
        """Rebuild BM25 explicitly after the source chunks change."""
        self.json_data = self._load_child_chunks()
        self.bm25 = self._build_bm25(self.json_data)

    def semantic_search(self, query_text: str, n_results: int = 10):
        return self.chroma_collec.query(
            query_texts=[query_text],
            n_results=n_results
        )

    def bm25_search(self, query_text: str, n_results: int = 10):
        return self.bm25.get_top_n(
            self._tokenize(query_text),
            self.json_data,
            n=n_results
        )

    def vector_semantic_results(self, query_text: str, n_results: int = 10):
        """Run hybrid retrieval using indexes prepared at initialization."""
        return (
            self.semantic_search(query_text, n_results),
            self.bm25_search(query_text, n_results),
        )
    
    def rrf(self, chroma_results, bm25_results, k=60):
        fused_scores = {}

        chroma_ids = chroma_results.get("ids", [[]])
        if chroma_ids and isinstance(chroma_ids[0], list):
            chroma_ids = chroma_ids[0]

        text_to_child_ids = {}
        for item in self.json_data:
            if isinstance(item, dict):
                child_id = item.get("child_id")
                text_content = item.get("text_content")
                if child_id and text_content:
                    text_to_child_ids.setdefault(text_content, []).append(child_id)

        used_text_offsets = {}

        def resolve_bm25_id(doc):
            if isinstance(doc, dict):
                for key in ("child_id", "id"):
                    if doc.get(key):
                        return doc[key]

                text_content = doc.get("text_content") or doc.get("document")
                if text_content in text_to_child_ids:
                    offset = used_text_offsets.get(text_content, 0)
                    ids = text_to_child_ids[text_content]
                    used_text_offsets[text_content] = offset + 1
                    return ids[min(offset, len(ids) - 1)]

                if doc.get("parent_id"):
                    return doc["parent_id"]

                return str(doc)

            if isinstance(doc, str) and doc in text_to_child_ids:
                offset = used_text_offsets.get(doc, 0)
                ids = text_to_child_ids[doc]
                used_text_offsets[doc] = offset + 1
                return ids[min(offset, len(ids) - 1)]

            return doc

        bm25_ids = []
        for doc in bm25_results:
            bm25_ids.append(resolve_bm25_id(doc))

        # Process ChromaDB Results (Dense Retrieval)
        for rank, doc_id in enumerate(chroma_ids):
            rank_pos = rank + 1 
            fused_scores[doc_id] = fused_scores.get(doc_id, 0.0) + 1.0 / (k + rank_pos)
            
        # Process BM25 Results (Sparse Retrieval)
        for rank, doc_id in enumerate(bm25_ids):
            rank_pos = rank + 1
            fused_scores[doc_id] = fused_scores.get(doc_id, 0.0) + 1.0 / (k + rank_pos)
            
        # Sort documents based on their combined RRF score in descending order
        reranked_docs = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
        
        return [doc_id for doc_id, score in reranked_docs]


@lru_cache(maxsize=1)
def get_retriever(
    child_token_path: str = "data/processed/child_chunks.json",
) -> Retriever:
    """Return the process-wide retriever used by request handlers."""
    return Retriever(child_token_path)
    
if __name__ == "__main__":
    ret = get_retriever()
    ret.chroma_collection()

    query_text =  "foreign capital allocations"
    
    chroma_results, bm25_results = ret.vector_semantic_results(query_text)
    
    rrf_result = ret.rrf(chroma_results,bm25_results)
    print(rrf_result)


    
