# sve_rag_judge 아키텍처

```mermaid
flowchart TB
    subgraph OFFLINE["오프라인 인덱싱 (1회)"]
        PDF["data/<br/>종합 룰북 PDF (일본어)"]
        EXTRACT["scripts/<br/>batch_pdf_to_json.py<br/>postprocess_pdf_json.py"]
        CHUNK["src/chunk_rules.py<br/>조항 번호 단위 청킹"]
        JSONL["build/chunks.jsonl<br/>659 청크 {rule_id, parent, text}"]
        BUILD["src/build_index.py<br/>LangChain + OllamaEmbeddings"]
        PDF --> EXTRACT --> CHUNK --> JSONL --> BUILD
    end

    subgraph STORE["저장소"]
        CHROMA[("index/ ChromaDB<br/>컬렉션 'rules' · cosine<br/>메타데이터: rule_id")]
    end

    subgraph ONLINE["온라인 질의"]
        CLI["src/judge_cli.py<br/>대화형 CLI"]
        GUI["src/judge_gui.py<br/>Gradio 웹 UI (신규)"]
        CORE["공유 로직 (judge_cli)<br/>ensure_ollama · retrieve · answer<br/>거리 게이트 MAX_DISTANCE=0.75"]
        CLI --> CORE
        GUI -->|import 재사용| CORE
    end

    subgraph OLLAMA["Ollama (로컬, 무료)"]
        EMB["bge-m3<br/>다국어 임베딩<br/>한국어 질문 ↔ 일본어 원문"]
        LLM["qwen3:8b<br/>한국어 답변 생성<br/>[룰 X.X.X] 인용 강제"]
    end

    BUILD --> CHROMA
    BUILD -.임베딩 요청.-> EMB
    CORE -->|top-k=8 검색| CHROMA
    CORE -.질문 임베딩.-> EMB
    CORE -.근거 조항 + 질문.-> LLM

    subgraph PHASE2["2단계 예정 데이터"]
        CARD["data/carddb/<br/>카드 CSV 52종"]
        QNA["data/qna/<br/>공식 Q&A JSONL"]
    end
    PHASE2 -.별도 컬렉션으로 인덱싱 예정.-> CHROMA

    style GUI fill:#e8f5e9,stroke:#43a047
    style PHASE2 fill:#fff3e0,stroke:#fb8c00,stroke-dasharray: 5 5
```

## 답변 흐름 요약

1. 사용자 질문(한국어) → bge-m3 임베딩 → ChromaDB top-8 검색
2. 거리 ≤ 0.75인 조항이 없으면 LLM 호출 없이 "관련 조항을 찾지 못했습니다" (환각 1차 방어)
3. 통과 조항만 프롬프트에 실어 qwen3:8b 호출 — 인용 필수, 근거 부족 시 "룰북에서 근거를 찾지 못했습니다" (2차 방어)
4. 답변 + 참조 조항 원문 표시 (사용자 직접 검증)
