import argparse
import json
import sys
from pathlib import Path

import chromadb
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

EMBED_MODEL = "bge-m3"
# cwd가 아니라 리포 루트 기준으로 고정 — src/ 안에서 실행해도 같은 인덱스를 쓴다
DEFAULT_DB = str(Path(__file__).resolve().parent.parent / "index")
BATCH = 64


def index_documents(client, name: str, docs: list[tuple[str, dict]], batch: int = BATCH) -> int:
    """(text, metadata) 리스트를 컬렉션 name에 재구축 저장하고 건수를 반환한다."""
    try:
        client.delete_collection(name)
    except Exception:
        pass  # 최초 실행이면 컬렉션이 없다
    store = Chroma(
        client=client,
        collection_name=name,
        embedding_function=OllamaEmbeddings(model=EMBED_MODEL),
        collection_metadata={"hnsw:space": "cosine"},
    )
    for i in range(0, len(docs), batch):
        chunk = docs[i:i + batch]
        store.add_texts(
            texts=[t for t, _ in chunk],
            metadatas=[m for _, m in chunk],
            ids=[str(i + j) for j in range(len(chunk))],
        )
        print(f"{name}: {min(i + batch, len(docs))}/{len(docs)}")
    return len(docs)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="청크 JSONL을 ChromaDB에 인덱싱")
    p.add_argument("chunks_file")
    p.add_argument("--db", default=DEFAULT_DB)
    args = p.parse_args()

    lines = Path(args.chunks_file).read_text(encoding="utf-8").splitlines()
    chunks = [json.loads(l) for l in lines if l.strip()]
    docs = [(c["text"], {"rule_id": c["rule_id"], "parent": c["parent"]}) for c in chunks]

    client = chromadb.PersistentClient(path=args.db)
    n = index_documents(client, "rules", docs)
    print(f"완료: {n}개 청크 → {args.db}/rules")


if __name__ == "__main__":
    main()
