import argparse
import json
from pathlib import Path

import chromadb
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

EMBED_MODEL = "bge-m3"
BATCH = 64


def main() -> None:
    p = argparse.ArgumentParser(description="청크 JSONL을 ChromaDB에 인덱싱")
    p.add_argument("chunks_file")
    p.add_argument("--db", default="index")
    args = p.parse_args()

    lines = Path(args.chunks_file).read_text(encoding="utf-8").splitlines()
    chunks = [json.loads(l) for l in lines if l.strip()]

    client = chromadb.PersistentClient(path=args.db)
    try:
        client.delete_collection("rules")
    except Exception:
        pass  # 최초 실행이면 컬렉션이 없다

    store = Chroma(
        client=client,
        collection_name="rules",
        embedding_function=OllamaEmbeddings(model=EMBED_MODEL),
        collection_metadata={"hnsw:space": "cosine"},
    )

    for i in range(0, len(chunks), BATCH):
        batch = chunks[i:i + BATCH]
        store.add_texts(
            texts=[c["text"] for c in batch],
            metadatas=[{"rule_id": c["rule_id"], "parent": c["parent"]} for c in batch],
            ids=[str(i + j) for j in range(len(batch))],
        )
        print(f"{min(i + BATCH, len(chunks))}/{len(chunks)}")

    print(f"완료: {len(chunks)}개 청크 → {args.db}/rules")


if __name__ == "__main__":
    main()
