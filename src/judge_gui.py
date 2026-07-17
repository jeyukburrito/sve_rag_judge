import argparse

import gradio as gr
from langchain_ollama import ChatOllama

from src.judge_cli import (
    DEFAULT_DB,
    DEFAULT_LLM,
    EMBED_MODEL,
    answer,
    ensure_ollama,
    open_stores,
    retrieve_all,
)


def build_app(db: str, llm_name: str) -> gr.ChatInterface:
    stores = open_stores(db)
    llm = ChatOllama(model=llm_name)

    def respond(question: str, history: list) -> str:
        question = question.strip()
        if not question:
            return "질문을 입력해주세요."
        try:
            hits = retrieve_all(stores, question)
            if not hits:
                return "관련 근거를 찾지 못했습니다."
            refs = "\n".join(
                f"- **[{label}]** (거리 {dist:.2f}) {doc[:120]}"
                for label, doc, dist in hits
            )
            return f"{answer(llm, question, hits)}\n\n---\n**참조 근거**\n{refs}"
        except Exception as e:  # 서버는 유지하고 채팅창에만 표시
            return f"오류가 발생했습니다: {e}"

    return gr.ChatInterface(
        fn=respond,
        title="SVE 판정 저지",
        description=(
            "Shadowverse Evolve 판정 저지 — 종합 룰북 + 카드 DB + 공식 Q&A 종합 검색. "
            "모든 답변은 근거([룰]/[카드]/[Q&A])를 인용합니다."
        ),
    )


def main() -> None:
    p = argparse.ArgumentParser(description="SVE 판정 저지 GUI")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--llm", default=DEFAULT_LLM)
    p.add_argument("--port", type=int, default=7860)
    args = p.parse_args()

    ensure_ollama([EMBED_MODEL, args.llm])
    app = build_app(args.db, args.llm)
    app.launch(server_name="127.0.0.1", server_port=args.port, inbrowser=True)


if __name__ == "__main__":
    main()
