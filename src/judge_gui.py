import argparse

import gradio as gr
from langchain_chroma import Chroma
from langchain_ollama import ChatOllama, OllamaEmbeddings

from src.judge_cli import (
    DEFAULT_DB,
    DEFAULT_LLM,
    EMBED_MODEL,
    MAX_DISTANCE,
    answer,
    ensure_ollama,
    retrieve,
)


def build_app(db: str, llm_name: str) -> gr.ChatInterface:
    store = Chroma(
        collection_name="rules",
        persist_directory=db,
        embedding_function=OllamaEmbeddings(model=EMBED_MODEL),
    )
    if store._collection.count() == 0:
        raise SystemExit(
            f"인덱스가 비어 있습니다: {db}\n"
            "먼저 실행하세요: python -m src.build_index build/chunks.jsonl"
        )
    llm = ChatOllama(model=llm_name)

    def respond(question: str, history: list) -> str:
        question = question.strip()
        if not question:
            return "질문을 입력해주세요."
        try:
            hits = [h for h in retrieve(store, question) if h[2] <= MAX_DISTANCE]
            if not hits:
                return "관련 조항을 찾지 못했습니다."
            refs = "\n".join(
                f"- **[룰 {rid}]** (거리 {dist:.2f}) {doc[:120]}"
                for rid, doc, dist in hits
            )
            return f"{answer(llm, question, hits)}\n\n---\n**참조 조항**\n{refs}"
        except Exception as e:  # 서버는 유지하고 채팅창에만 표시
            return f"오류가 발생했습니다: {e}"

    return gr.ChatInterface(
        fn=respond,
        title="SVE 룰 저지",
        description=(
            "Shadowverse Evolve 종합 룰북 기반 룰 Q&A. "
            "모든 답변은 [룰 X.X.X] 형식으로 조항을 인용합니다. "
            "답변 생성에 1~3분 걸릴 수 있습니다."
        ),
    )


def main() -> None:
    p = argparse.ArgumentParser(description="SVE 룰 Q&A GUI")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--llm", default=DEFAULT_LLM)
    p.add_argument("--port", type=int, default=7860)
    args = p.parse_args()

    ensure_ollama([EMBED_MODEL, args.llm])
    app = build_app(args.db, args.llm)
    app.launch(server_name="127.0.0.1", server_port=args.port, inbrowser=True)


if __name__ == "__main__":
    main()
