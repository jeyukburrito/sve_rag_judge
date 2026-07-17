import argparse
import sys
from pathlib import Path

import ollama
from langchain_chroma import Chroma
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama, OllamaEmbeddings

EMBED_MODEL = "bge-m3"
DEFAULT_LLM = "qwen3:8b"
# cwd가 아니라 리포 루트 기준으로 고정 — src/ 안에서 실행해도 같은 인덱스를 쓴다
DEFAULT_DB = str(Path(__file__).resolve().parent.parent / "index")
TOP_K = 8
MAX_DISTANCE = 0.75  # cosine distance. 전부 이보다 멀면 LLM 호출 없이 근거 없음 처리

SYSTEM_PROMPT = (
    "당신은 Shadowverse Evolve 공식 룰 저지입니다. "
    "아래 제공된 룰 조항만을 근거로 한국어로 답변하세요. "
    "답변에는 반드시 [룰 X.X.X] 형식으로 근거 조항을 인용하세요. "
    "제공된 조항으로 답할 수 없으면 정확히 '룰북에서 근거를 찾지 못했습니다'라고 답하세요."
)


def ensure_ollama(models: list[str]) -> None:
    try:
        installed = [m.model for m in ollama.list().models]
    except Exception:
        sys.exit("Ollama에 연결할 수 없습니다. 설치/실행 후 재시도: https://ollama.com")
    for model in models:
        if ":" in model:
            ok = model in installed
        else:
            ok = any(name.split(":")[0] == model for name in installed)
        if not ok:
            sys.exit(f"모델이 없습니다. 먼저 실행하세요: ollama pull {model}")


def retrieve(store: Chroma, question: str) -> list[tuple[str, str, float]]:
    hits = store.similarity_search_with_score(question, k=TOP_K)
    return [(doc.metadata["rule_id"], doc.page_content, dist) for doc, dist in hits]


def answer(llm: ChatOllama, question: str, hits: list[tuple[str, str, float]]) -> str:
    context = "\n\n".join(f"[룰 {rid}] {doc}" for rid, doc, _ in hits)
    res = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"룰 조항:\n{context}\n\n질문: {question}"),
    ])
    return res.content


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="SVE 룰 Q&A CLI")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--llm", default=DEFAULT_LLM)
    args = p.parse_args()

    ensure_ollama([EMBED_MODEL, args.llm])
    store = Chroma(
        collection_name="rules",
        persist_directory=args.db,
        embedding_function=OllamaEmbeddings(model=EMBED_MODEL),
    )
    if store._collection.count() == 0:
        sys.exit(
            f"인덱스가 비어 있습니다: {args.db}\n"
            "먼저 실행하세요: python -m src.build_index build/chunks.jsonl"
        )
    llm = ChatOllama(model=args.llm)

    print("SVE 룰 저지 — 질문을 입력하세요 (종료: 빈 줄)")
    while True:
        try:
            question = input("\n질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            break
        hits = [h for h in retrieve(store, question) if h[2] <= MAX_DISTANCE]
        if not hits:
            print("관련 조항을 찾지 못했습니다.")
            continue
        print("\n" + answer(llm, question, hits))
        print("\n--- 참조 조항 ---")
        for rid, doc, dist in hits:
            print(f"[룰 {rid}] (거리 {dist:.2f}) {doc[:120]}")


if __name__ == "__main__":
    main()
