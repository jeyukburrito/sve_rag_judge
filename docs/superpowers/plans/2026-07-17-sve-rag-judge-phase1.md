# SVE RAG 룰 저지 1단계 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 일본어 SVE 종합 룰북에 대해 한국어로 질문하면 룰 번호를 인용해 답변하는 로컬 CLI를 만든다.

**Architecture:** 오프라인 인덱싱(기존 PDF 추출 파이프라인 → 조항 단위 청킹 → bge-m3 임베딩 → ChromaDB)과 온라인 질의(질문 임베딩 → top-k 검색 → Ollama LLM 답변 생성)의 2단 구조. RAG 배선은 LangChain(langchain-chroma, langchain-ollama), 청킹은 조항 번호 기반 커스텀 로직.

**Tech Stack:** Python 3.13, LangChain (langchain-chroma + langchain-ollama), ChromaDB (persistent local), Ollama (bge-m3 임베딩 + qwen3 LLM), opendataloader-pdf (기존 추출 스크립트 의존성), pytest

**Spec:** `docs/superpowers/specs/2026-07-17-sve-rag-judge-design.md`

## Global Constraints

- 전부 무료/로컬 실행. 유료 API 호출 금지.
- 모든 답변은 `[룰 X.X.X]` 형식 인용 필수. 근거 부족 시 정확히 "룰북에서 근거를 찾지 못했습니다"로 답하는 프롬프트 유지.
- RAG 배선(임베딩·벡터스토어·LLM 호출)은 LangChain(langchain-chroma, langchain-ollama)을 사용한다. 청킹은 커스텀 로직.
- 생성/수정 파일은 이 계획에 명시된 것만. 기존 `scripts/`, `data/`는 수정 금지.
- 산출물 디렉터리 `build/`(추출 텍스트)와 `index/`(ChromaDB)는 gitignore 대상.
- 커밋 메시지 끝에 다음 트레일러를 붙인다:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: 프로젝트 셋업과 룰북 텍스트 추출

**Files:**
- Create: `requirements.txt`
- Modify: `.gitignore`
- Create (산출물, 커밋 안 함): `build/raw_json/`, `build/processed/ShadowverseEVOLVE_cr_1.26.1_260609.txt`

**Interfaces:**
- Produces: `build/processed/ShadowverseEVOLVE_cr_1.26.1_260609.txt` — 룰북 전체 평문 텍스트. Task 2가 입력으로 사용.

- [ ] **Step 1: requirements.txt 작성**

```
opendataloader-pdf
langchain-chroma
langchain-ollama
pytest
```

(chromadb와 ollama 파이썬 클라이언트는 위 langchain 패키지들의 의존성으로 함께 설치된다.)

- [ ] **Step 2: .gitignore에 산출물 디렉터리 추가**

기존 `.gitignore` 끝에 추가:

```
build/
index/
```

- [ ] **Step 3: 의존성 설치**

Run: `pip install -r requirements.txt`
Expected: 오류 없이 설치 완료. (opendataloader-pdf는 Java 런타임이 필요할 수 있음 — `java -version` 실패 시 여기서 멈추고 보고할 것. 대안 결정은 메인 에이전트가 한다.)

- [ ] **Step 4: 기존 파이프라인으로 텍스트 추출**

Run:
```bash
python scripts/batch_pdf_to_json.py data build/raw_json
python scripts/postprocess_pdf_json.py build/raw_json build/processed
```
Expected: `build/processed/ShadowverseEVOLVE_cr_1.26.1_260609.txt` 생성. `1.` 형식의 조항 번호가 보이는 일본어 텍스트여야 함. 다음으로 확인:

Run: `python -c "t=open('build/processed/ShadowverseEVOLVE_cr_1.26.1_260609.txt',encoding='utf-8').read(); print(len(t)); print(t[:500])"`
Expected: 글자 수 수만 자 이상, 앞부분에 일본어 룰 텍스트 출력.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .gitignore
git commit -m "chore: add phase-1 dependencies and build artifact ignores"
```

---

### Task 2: 조항 단위 청킹 (chunk_rules.py, TDD)

**Files:**
- Create: `src/chunk_rules.py`
- Create: `src/__init__.py` (빈 파일)
- Test: `tests/test_chunking.py`

**Interfaces:**
- Consumes: Task 1의 추출 텍스트 파일 (평문, 조항 번호 줄 시작)
- Produces:
  - `parse_chunks(text: str) -> list[dict]` — 각 dict는 `{"rule_id": "1.1", "parent": "1", "text": "원문"}`
  - CLI: `python -m src.chunk_rules <입력.txt> <출력.jsonl>` → 한 줄에 청크 하나인 JSONL. Task 3이 이 JSONL을 읽는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_chunking.py`:

```python
from src.chunk_rules import parse_chunks

SAMPLE = """1. ゲームの基本
1.1. このゲームは2人で対戦するカードゲームです。プレイヤーは山札を用意します。
1.1.1. 先攻
先攻プレイヤーは最初のターンにカードを引くことができません。注意してください。
2.1. カードには複数の種類があり、それぞれ異なる役割を持っています。
"""


def test_rule_ids_extracted():
    ids = [c["rule_id"] for c in parse_chunks(SAMPLE)]
    assert ids == ["1.1", "1.1.1", "2.1"]


def test_short_title_merged_into_next_chunk():
    # "1. ゲームの基本"은 제목뿐이라 독립 청크가 아니라 1.1 텍스트 앞에 붙는다
    first = parse_chunks(SAMPLE)[0]
    assert first["rule_id"] == "1.1"
    assert "ゲームの基本" in first["text"]


def test_parent_id():
    chunks = parse_chunks(SAMPLE)
    assert chunks[1]["parent"] == "1.1"
    assert chunks[0]["parent"] == "1"


def test_continuation_lines_joined():
    c = parse_chunks(SAMPLE)[1]
    assert "先攻プレイヤー" in c["text"]
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_chunking.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.chunk_rules'`

- [ ] **Step 3: 최소 구현 작성**

`src/__init__.py`: 빈 파일 생성.

`src/chunk_rules.py`:

```python
import argparse
import json
import re
from pathlib import Path

RULE_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+")
MIN_BODY_LEN = 25  # 이보다 짧으면 제목으로 간주하고 다음 조항 앞에 붙인다


def parse_chunks(text: str) -> list[dict]:
    raw: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = RULE_RE.match(line)
        if m:
            if current:
                raw.append(current)
            rule_id = m.group(1)
            parent = rule_id.rsplit(".", 1)[0] if "." in rule_id else ""
            current = {"rule_id": rule_id, "parent": parent, "text": line}
        elif current:
            current["text"] += "\n" + line
    if current:
        raw.append(current)

    # 제목만 있는 짧은 조항은 다음 조항 텍스트 앞에 붙인다
    chunks: list[dict] = []
    pending_title = ""
    for c in raw:
        body = RULE_RE.sub("", c["text"], count=1)
        if len(body) < MIN_BODY_LEN:
            pending_title += c["text"] + "\n"
            continue
        if pending_title:
            c["text"] = pending_title + c["text"]
            pending_title = ""
        chunks.append(c)
    if pending_title and chunks:
        chunks[-1]["text"] += "\n" + pending_title.strip()
    return chunks


def main() -> None:
    p = argparse.ArgumentParser(description="룰북 평문을 조항 단위 JSONL로 청킹")
    p.add_argument("input_txt")
    p.add_argument("output_jsonl")
    args = p.parse_args()

    text = Path(args.input_txt).read_text(encoding="utf-8")
    chunks = parse_chunks(text)
    out = Path(args.output_jsonl)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"{len(chunks)}개 청크 → {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_chunking.py -v`
Expected: 4 passed

- [ ] **Step 5: 실제 룰북에 실행해 육안 확인**

Run: `python -m src.chunk_rules build/processed/ShadowverseEVOLVE_cr_1.26.1_260609.txt build/chunks.jsonl`
Expected: "N개 청크" 출력 (N은 수백 개 예상). 이어서:

Run: `python -c "import json; lines=open('build/chunks.jsonl',encoding='utf-8').readlines(); print(len(lines)); [print(json.loads(l)['rule_id'], json.loads(l)['text'][:60]) for l in lines[:5]]"`
Expected: 조항 번호와 일본어 원문이 짝지어 출력. 깨진 청크(번호 없는 본문 덩어리, 페이지 머리글 섞임 등)가 보이면 정규식/병합 로직을 조정하고 테스트에 케이스를 추가할 것.

- [ ] **Step 6: Commit**

```bash
git add src/__init__.py src/chunk_rules.py tests/test_chunking.py
git commit -m "feat: clause-level chunking for SVE rulebook"
```

---

### Task 3: 임베딩 인덱스 구축 (build_index.py)

**Files:**
- Create: `src/build_index.py`
- Create (산출물, 커밋 안 함): `index/` (ChromaDB persistent 저장소)

**Interfaces:**
- Consumes: Task 2의 `build/chunks.jsonl` (`{"rule_id", "parent", "text"}` per line)
- Produces: ChromaDB 컬렉션 `rules` (경로 `index/`, cosine space). 문서=조항 원문, 메타데이터=`{"rule_id": str, "parent": str}`, id=순번 문자열. Task 4가 이 컬렉션을 읽는다.

- [ ] **Step 1: Ollama와 bge-m3 준비 확인**

Run: `ollama --version && ollama pull bge-m3`
Expected: 버전 출력 후 모델 다운로드 완료. `ollama` 명령이 없으면 멈추고 보고할 것 (설치는 사용자 결정: https://ollama.com).

- [ ] **Step 2: 구현 작성**

`src/build_index.py`:

```python
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
```

- [ ] **Step 3: 인덱스 구축 실행**

Run: `python -m src.build_index build/chunks.jsonl`
Expected: 진행 카운터 출력 후 "완료: N개 청크 → index/rules". `index/` 디렉터리 생성됨.

- [ ] **Step 4: 검색 스모크 테스트 (교차 언어 확인)**

Run:
```bash
python -c "
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
store = Chroma(collection_name='rules', persist_directory='index', embedding_function=OllamaEmbeddings(model='bge-m3'))
for doc, dist in store.similarity_search_with_score('진화는 언제 할 수 있나요?', k=3):
    print(doc.metadata['rule_id'], f'{dist:.3f}', doc.page_content[:80])
"
```
Expected: 진화(進化) 관련 일본어 조항이 상위에 나오고 distance가 대략 0.6 이하. 무관한 조항만 나오면 멈추고 보고할 것.

- [ ] **Step 5: Commit**

```bash
git add src/build_index.py
git commit -m "feat: build ChromaDB index with bge-m3 embeddings"
```

---

### Task 4: 질의 CLI (judge_cli.py)

**Files:**
- Create: `src/judge_cli.py`

**Interfaces:**
- Consumes: Task 3의 ChromaDB 컬렉션 `rules` (경로 `index/`, 메타데이터 `rule_id`), Ollama 모델 `bge-m3` + LLM
- Produces: `python -m src.judge_cli [--db index] [--llm qwen3:8b]` 대화형 CLI

- [ ] **Step 1: 구현 작성**

`src/judge_cli.py`:

```python
import argparse
import sys

import ollama
from langchain_chroma import Chroma
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama, OllamaEmbeddings

EMBED_MODEL = "bge-m3"
DEFAULT_LLM = "qwen3:8b"
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
        installed = {m.model.split(":")[0] for m in ollama.list().models}
    except Exception:
        sys.exit("Ollama에 연결할 수 없습니다. 설치/실행 후 재시도: https://ollama.com")
    for model in models:
        if model.split(":")[0] not in installed:
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
    p = argparse.ArgumentParser(description="SVE 룰 Q&A CLI")
    p.add_argument("--db", default="index")
    p.add_argument("--llm", default=DEFAULT_LLM)
    args = p.parse_args()

    ensure_ollama([EMBED_MODEL, args.llm])
    store = Chroma(
        collection_name="rules",
        persist_directory=args.db,
        embedding_function=OllamaEmbeddings(model=EMBED_MODEL),
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
```

- [ ] **Step 2: LLM 모델 준비**

Run: `ollama pull qwen3:8b`
Expected: 다운로드 완료. (머신 사양이 안 되면 `qwen3:4b`로 대체하고 이후 명령의 `--llm` 값을 맞출 것.)

- [ ] **Step 3: 수동 검증 — 룰 질문 3개 + 무관 질문 1개**

Run: `python -m src.judge_cli`
입력할 질문과 기대 결과:
1. "진화는 언제 할 수 있나요?" → `[룰 X.X.X]` 인용이 포함된 한국어 답변 + 참조 조항 목록
2. "덱은 몇 장으로 구성하나요?" → 덱 구성 조항 인용 답변
3. "공격 순서는 어떻게 되나요?" → 전투 관련 조항 인용 답변
4. "유희왕의 체인 규칙을 설명해줘" → "룰북에서 근거를 찾지 못했습니다" 또는 "관련 조항을 찾지 못했습니다"

각 답변에서 인용된 조항 번호가 참조 조항 목록에 실제로 존재하는지 확인. 인용 없는 답변이 나오면 SYSTEM_PROMPT를 강화하고 재시도.

- [ ] **Step 4: Commit**

```bash
git add src/judge_cli.py
git commit -m "feat: interactive rule Q&A CLI with mandatory citations"
```

---

### Task 5: README 갱신과 마무리

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 1~4의 전체 파이프라인

- [ ] **Step 1: README에 사용법 추가**

`README.md`의 `## 사용법` 섹션 아래에 다음 섹션 추가 (기존 내용 유지):

```markdown
## 룰 Q&A CLI (RAG)

사전 준비: [Ollama](https://ollama.com) 설치 후 `ollama pull bge-m3 && ollama pull qwen3:8b`

\`\`\`bash
pip install -r requirements.txt

# 1회 인덱싱
python scripts/batch_pdf_to_json.py data build/raw_json
python scripts/postprocess_pdf_json.py build/raw_json build/processed
python -m src.chunk_rules build/processed/ShadowverseEVOLVE_cr_1.26.1_260609.txt build/chunks.jsonl
python -m src.build_index build/chunks.jsonl

# 질의
python -m src.judge_cli
\`\`\`

모든 답변은 `[룰 X.X.X]` 형식으로 종합 룰북 조항을 인용하며, 근거를 찾지 못하면 그렇게 말합니다.
```

(위 코드 블록의 `\`\`\``는 실제 파일에서는 일반 백틱 3개로 쓸 것.)

- [ ] **Step 2: 전체 테스트 실행**

Run: `python -m pytest -v`
Expected: 전부 PASS

- [ ] **Step 3: Commit & Push**

```bash
git add README.md
git commit -m "docs: add RAG rule Q&A usage to README"
git push
```
