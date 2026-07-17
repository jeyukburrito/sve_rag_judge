import argparse
import re
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
MAX_DISTANCE = 0.75  # cosine distance. 소스별 동일 게이트
QUOTAS = {"rules": 6, "cards": 4, "qna": 4}  # 소스별 top-k
# \b is Unicode-aware in Python 3, so a code touching a Korean/Japanese particle
# (e.g. "BP01-001과") has no word boundary and would not match. Use ASCII-only
# boundary lookarounds so CJK-adjacent codes still match, without over-matching.
CARD_CODE_RE = re.compile(r"(?<![0-9A-Za-z])[A-Za-z]{2,4}\d{2}[A-Za-z]?-\d{1,3}(?![0-9A-Za-z])")

SYSTEM_PROMPT = (
    "당신은 Shadowverse Evolve 공식 룰 저지입니다. "
    "아래 제공된 근거(종합 룰 조항, 카드 정보, 공식 Q&A)만으로 한국어로 판정하세요. "
    "근거 간 충돌 시 우선순위: 공식 Q&A 재정 > 카드 텍스트 > 종합 룰. "
    "답변에는 반드시 [룰 X.X.X], [카드 코드 이름], [Q&A ID] 형식으로 근거를 인용하세요. "
    "제공된 자료로 답할 수 없으면 정확히 '제공된 자료에서 근거를 찾지 못했습니다'라고 답하세요."
)

_EMPTY_HINTS = {
    "rules": "python -m src.build_index build/chunks.jsonl",
    "cards": "python -m src.build_phase2_index",
    "qna": "python -m src.build_phase2_index",
}


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


def extract_card_codes(text: str) -> list[str]:
    seen: list[str] = []
    for code in CARD_CODE_RE.findall(text):
        if code not in seen:
            seen.append(code)
    return seen


def open_stores(db: str) -> dict[str, Chroma]:
    emb = OllamaEmbeddings(model=EMBED_MODEL)
    stores = {}
    for name in ("rules", "cards", "qna"):
        store = Chroma(collection_name=name, persist_directory=db, embedding_function=emb)
        if store._collection.count() == 0:
            sys.exit(
                f"'{name}' 인덱스가 비어 있습니다: {db}\n"
                f"먼저 실행하세요: {_EMPTY_HINTS[name]}"
            )
        stores[name] = store
    return stores


def _label(source: str, meta: dict) -> str:
    if source == "rules":
        return f"룰 {meta['rule_id']}"
    if source == "cards":
        return f"카드 {meta['card_code']} {meta['name']}"
    return f"Q&A {meta['qa_id']}"


def retrieve_all(stores: dict, question: str) -> list[tuple[str, str, float]]:
    hits: list[tuple[str, str, float]] = []
    seen_labels: set[str] = set()

    # 1) 질문 속 카드 코드는 정확 조회 (항상 포함, 거리 0)
    for code in extract_card_codes(question):
        got = stores["cards"].get(where={"card_code": code})
        if not got["documents"]:
            # 스펙: 미발견 코드는 무시하되 컨텍스트에 표시
            hits.append((f"카드 {code}", "카드 DB에서 이 코드를 찾지 못했습니다.", 0.0))
            continue
        for doc, meta in zip(got["documents"], got["metadatas"]):
            label = _label("cards", meta)
            if label not in seen_labels:
                seen_labels.add(label)
                hits.append((label, doc, 0.0))

    # 2) 소스별 쿼터 임베딩 검색 + 거리 게이트
    for source, k in QUOTAS.items():
        for doc, dist in stores[source].similarity_search_with_score(question, k=k):
            if dist > MAX_DISTANCE:
                continue
            label = _label(source, doc.metadata)
            if label not in seen_labels:
                seen_labels.add(label)
                hits.append((label, doc.page_content, dist))
    return hits


def answer(llm: ChatOllama, question: str, hits: list[tuple[str, str, float]]) -> str:
    context = "\n\n".join(f"[{label}] {doc}" for label, doc, _ in hits)
    res = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"근거 자료:\n{context}\n\n질문: {question}"),
    ])
    return res.content


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="SVE 판정 저지 CLI")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--llm", default=DEFAULT_LLM)
    args = p.parse_args()

    ensure_ollama([EMBED_MODEL, args.llm])
    stores = open_stores(args.db)
    llm = ChatOllama(model=args.llm)

    print("SVE 판정 저지 — 질문을 입력하세요 (종료: 빈 줄)")
    while True:
        try:
            question = input("\n질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            break
        hits = retrieve_all(stores, question)
        if not hits:
            print("관련 근거를 찾지 못했습니다.")
            continue
        print("\n" + answer(llm, question, hits))
        print("\n--- 참조 근거 ---")
        for label, doc, dist in hits:
            print(f"[{label}] (거리 {dist:.2f}) {doc[:120]}")


if __name__ == "__main__":
    main()
