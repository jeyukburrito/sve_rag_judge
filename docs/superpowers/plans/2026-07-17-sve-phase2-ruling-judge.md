# SVE 2단계 판정 저지 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 카드 DB(7,079장)와 공식 Q&A(2,699건)를 인덱싱하고, 질문마다 룰북+카드+Q&A 세 소스를 종합 검색해 판정하는 저지로 확장한다.

**Architecture:** 기존 ChromaDB(`index/`)에 `cards`, `qna` 컬렉션을 추가하고, `judge_cli.py`의 검색을 소스별 쿼터 멀티 컬렉션 검색으로 확장한다. 카드 코드가 질문에 있으면 정확 조회를 병행한다. GUI는 core 함수 재사용이므로 소폭 수정.

**Tech Stack:** 기존과 동일 — Python 3.13, LangChain(langchain-chroma/langchain-ollama), ChromaDB, Ollama(bge-m3 + qwen3:8b), pytest

**Spec:** `docs/superpowers/specs/2026-07-17-sve-phase2-ruling-judge-design.md`

## Global Constraints

- 전부 무료/로컬 실행. 유료 API 호출 금지.
- 검색 쿼터 상수: rules top-6, cards top-4, qna top-4. 거리 게이트 0.75 (기존 MAX_DISTANCE 재사용).
- 인용 형식: `[룰 X.X.X]` / `[카드 {code} {name}]` / `[Q&A {qa_id}]`. 근거 부족 시 정확히 '제공된 자료에서 근거를 찾지 못했습니다'.
- 우선순위 문구(프롬프트에 그대로): "근거 간 충돌 시 우선순위: 공식 Q&A 재정 > 카드 텍스트 > 종합 룰".
- 생성/수정 파일은 각 태스크에 명시된 것만. `rules` 컬렉션은 재구축하지 않는다.
- 커밋 메시지 끝 트레일러:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: index_documents 헬퍼 추출 (build_index.py 리팩터)

**Files:**
- Modify: `src/build_index.py`

**Interfaces:**
- Produces: `index_documents(client, name: str, docs: list[tuple[str, dict]], batch: int = BATCH) -> int` — (text, metadata) 리스트를 임베딩해 컬렉션 `name`에 저장(기존 컬렉션 삭제 후 재구축), 저장 건수 반환. Task 2가 import한다.
- 기존 CLI 동작(`python -m src.build_index build/chunks.jsonl`)은 변하지 않는다.

- [ ] **Step 1: 리팩터 구현**

`src/build_index.py` 전체를 다음으로 교체:

```python
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
```

- [ ] **Step 2: 기존 테스트와 CLI 동작 확인**

Run: `python -m pytest -q`
Expected: 8 passed

Run: `python -m src.build_index --help`
Expected: 사용법 출력, 오류 없음. (rules 재구축은 하지 않는다 — 로직 동일성은 코드 리뷰로 확인)

- [ ] **Step 3: Commit**

```bash
git add src/build_index.py
git commit -m "refactor: extract index_documents helper for phase-2 reuse"
```

---

### Task 2: 카드/Q&A 인덱서 (build_phase2_index.py, TDD)

**Files:**
- Create: `src/build_phase2_index.py`
- Test: `tests/test_phase2.py` (card_doc/qna_doc 테스트 부분)
- Create (산출물, 커밋 안 함): `index/`의 `cards`, `qna` 컬렉션

**Interfaces:**
- Consumes: Task 1의 `index_documents(client, name, docs, batch)`
- Produces:
  - `card_doc(row: dict) -> tuple[str, dict]` — CSV 행 → (문서 텍스트, 메타데이터 {card_code, name, class, card_type})
  - `qna_doc(rec: dict) -> tuple[str, dict]` — JSONL 레코드 → (문서 텍스트, 메타데이터 {qa_id, category, cards, date})
  - CLI: `python -m src.build_phase2_index [--db]` → `cards`(7,079), `qna`(2,699) 컬렉션. Task 3이 이 컬렉션을 읽는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_phase2.py` 생성:

```python
from src.build_phase2_index import card_doc, qna_doc

CARD_ROW = {
    "card_code": "BP01-001", "name": "ローズクイーン", "class": "エルフ",
    "card_type": "フォロワー", "sub_type": "植物族",
    "cost": "8", "attack": "7", "hp": "7",
    "effect": "【ファンファーレ】カードを1枚引く。",
}

QNA_REC = {
    "qa_id": "Q42", "date": "2022-04-26", "scope": "card", "category": "バトル",
    "question": "Qこのカードの能力は誘発しますか？",
    "answer": "Aはい、誘発します。",
    "source_url": "https://example.com",
    "cards": [{"card_code": "SD04-001"}, {"card_code": "BP01-001"}],
}


def test_card_doc_text_contains_key_fields():
    text, meta = card_doc(CARD_ROW)
    assert "BP01-001" in text
    assert "ローズクイーン" in text
    assert "コスト8" in text
    assert "【ファンファーレ】" in text


def test_card_doc_metadata():
    _, meta = card_doc(CARD_ROW)
    assert meta == {
        "card_code": "BP01-001", "name": "ローズクイーン",
        "class": "エルフ", "card_type": "フォロワー",
    }


def test_qna_doc_text_is_question_and_answer():
    text, _ = qna_doc(QNA_REC)
    assert text.startswith("Q: ")
    assert "\nA: " in text
    assert "誘発しますか" in text


def test_qna_doc_metadata_joins_card_codes():
    _, meta = qna_doc(QNA_REC)
    assert meta == {
        "qa_id": "Q42", "category": "バトル",
        "cards": "SD04-001,BP01-001", "date": "2022-04-26",
    }
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_phase2.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.build_phase2_index'`

- [ ] **Step 3: 구현 작성**

`src/build_phase2_index.py`:

```python
import argparse
import csv
import glob
import json
import sys
from pathlib import Path

import chromadb

from src.build_index import DEFAULT_DB, index_documents

ROOT = Path(__file__).resolve().parent.parent
CARDDB_GLOB = str(ROOT / "data" / "carddb" / "*.csv")
QNA_FILE = ROOT / "data" / "qna" / "unique_qna.jsonl"


def card_doc(row: dict) -> tuple[str, dict]:
    text = (
        f"{row['card_code']} {row['name']} / クラス:{row['class']} / "
        f"{row['card_type']}({row['sub_type']}) / "
        f"コスト{row['cost']} 攻{row['attack']} 体{row['hp']} / "
        f"効果: {row['effect']}"
    )
    meta = {k: row[k] for k in ("card_code", "name", "class", "card_type")}
    return text, meta


def qna_doc(rec: dict) -> tuple[str, dict]:
    text = f"Q: {rec['question']}\nA: {rec['answer']}"
    meta = {
        "qa_id": rec["qa_id"],
        "category": rec["category"],
        "cards": ",".join(c["card_code"] for c in rec["cards"]),
        "date": rec["date"],
    }
    return text, meta


def load_cards() -> list[tuple[str, dict]]:
    docs = []
    for path in sorted(glob.glob(CARDDB_GLOB)):
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                docs.append(card_doc(row))
    return docs


def load_qna() -> list[tuple[str, dict]]:
    docs = []
    with open(QNA_FILE, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                docs.append(qna_doc(json.loads(line)))
    return docs


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="카드 DB와 공식 Q&A를 ChromaDB에 인덱싱")
    p.add_argument("--db", default=DEFAULT_DB)
    args = p.parse_args()

    client = chromadb.PersistentClient(path=args.db)
    cards = load_cards()
    print(f"카드 {len(cards)}건 로드")
    index_documents(client, "cards", cards)
    qna = load_qna()
    print(f"Q&A {len(qna)}건 로드")
    index_documents(client, "qna", qna)
    print(f"완료: cards={len(cards)}, qna={len(qna)} → {args.db}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_phase2.py -v`
Expected: 4 passed

- [ ] **Step 5: GPU 사용 확인 후 인덱스 구축**

Run: `ollama ps` (임베딩 1회 호출 후: `python -c "import ollama; ollama.embed(model='bge-m3', input=['test'])" && ollama ps`)
Expected: bge-m3 행의 PROCESSOR에 GPU 표기(예: "100% GPU"). CPU만 나오면 멈추지 말고 보고에 기록만 하고 진행(시간이 25~35분으로 늘어남).

Run: `python -m src.build_phase2_index`
Expected: "카드 7079건 로드" → 진행 카운터 → "Q&A 2699건 로드" → 진행 카운터 → "완료: cards=7079, qna=2699 → ...index"

- [ ] **Step 6: 교차 언어 스모크 테스트**

Run:
```bash
python -c "
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
emb = OllamaEmbeddings(model='bge-m3')
cards = Chroma(collection_name='cards', persist_directory='index', embedding_function=emb)
qna = Chroma(collection_name='qna', persist_directory='index', embedding_function=emb)
print('cards count:', cards._collection.count())
print('qna count:', qna._collection.count())
for doc, dist in cards.similarity_search_with_score('로즈퀸 카드 효과', k=3):
    print('CARD', doc.metadata['card_code'], f'{dist:.3f}', doc.page_content[:50])
for doc, dist in qna.similarity_search_with_score('팡파르 능력은 언제 발동하나요?', k=3):
    print('QNA', doc.metadata['qa_id'], f'{dist:.3f}', doc.page_content[:50])
"
```
Expected: counts 7079/2699. 한국어 '로즈퀸' 쿼리에 ローズクイーン 카드가 상위권(정확한 순위는 무관, 3위 내), Q&A는 팡파르(ファンファーレ) 관련 항목이 상위. 전혀 무관하면 멈추고 실제 top-3와 함께 보고.

- [ ] **Step 7: Commit**

```bash
git add src/build_phase2_index.py tests/test_phase2.py
git commit -m "feat: index card DB and official QnA into ChromaDB"
```

---

### Task 3: 멀티 소스 검색·판정 (judge_cli.py 확장, TDD)

**Files:**
- Modify: `src/judge_cli.py`
- Test: `tests/test_phase2.py` (extract_card_codes 테스트 추가)

**Interfaces:**
- Consumes: Task 2의 `cards`/`qna` 컬렉션 (메타데이터 키: cards→card_code/name, qna→qa_id)
- Produces (Task 4의 GUI가 import):
  - `extract_card_codes(text: str) -> list[str]` — 질문에서 카드 코드 추출 (등장 순서, 중복 제거)
  - `open_stores(db: str) -> dict[str, Chroma]` — {"rules","cards","qna"} 스토어. 비었으면 sys.exit(안내 메시지)
  - `retrieve_all(stores: dict, question: str) -> list[tuple[str, str, float]]` — (라벨, 문서, 거리) 리스트. 라벨 형식: `"룰 {rule_id}"` / `"카드 {card_code} {name}"` / `"Q&A {qa_id}"`. 거리 게이트 적용 완료 상태로 반환
  - `answer(llm, question, hits)` — 시그니처 기존과 동일 (hits의 첫 원소가 rule_id 대신 라벨)

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_phase2.py`에 추가:

```python
from src.judge_cli import extract_card_codes


def test_extract_card_codes_basic():
    assert extract_card_codes("BP01-001과 SD04-001의 상호작용은?") == ["BP01-001", "SD04-001"]


def test_extract_card_codes_lowercase_set_suffix():
    assert extract_card_codes("CSD02a-015 효과 알려줘") == ["CSD02a-015"]


def test_extract_card_codes_none():
    assert extract_card_codes("진화는 언제 할 수 있나요?") == []


def test_extract_card_codes_dedup():
    assert extract_card_codes("BP01-001 그리고 또 BP01-001") == ["BP01-001"]
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_phase2.py -v`
Expected: 기존 4개 PASS + 신규 4개 FAIL (`ImportError: cannot import name 'extract_card_codes'`)

- [ ] **Step 3: judge_cli.py 확장 구현**

`src/judge_cli.py` 전체를 다음으로 교체:

```python
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
CARD_CODE_RE = re.compile(r"\b[A-Za-z]{2,4}\d{2}[A-Za-z]?-\d{1,3}\b")

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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest -v`
Expected: 전부 PASS (기존 8 + phase2 8 = 16). `tests/test_paths.py`도 여전히 통과해야 한다.

- [ ] **Step 5: 룰 질문 회귀 + 카드 코드 정확 조회 수동 확인**

Run:
```bash
python -c "
import sys; sys.stdout.reconfigure(encoding='utf-8')
from src.judge_cli import open_stores, retrieve_all, DEFAULT_DB
stores = open_stores(DEFAULT_DB)
for q in ['진화는 언제 할 수 있나요?', 'BP01-001 카드 효과 알려줘']:
    print('---', q)
    for label, doc, dist in retrieve_all(stores, q)[:6]:
        print(f'  [{label}] {dist:.2f} {doc[:50]}')
"
```
Expected: 첫 질문에 `[룰 12.2.x]`류가 상위 포함. 둘째 질문에 `[카드 BP01-001 ローズクイーン] 0.00`이 첫 항목(정확 조회).

- [ ] **Step 6: Commit**

```bash
git add src/judge_cli.py tests/test_phase2.py
git commit -m "feat: multi-source ruling retrieval with card-code exact lookup"
```

---

### Task 4: GUI 반영 + README + 수동 검증 (마무리)

**Files:**
- Modify: `src/judge_gui.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 3의 `open_stores`, `retrieve_all`, `answer`, `ensure_ollama`, `DEFAULT_DB`, `DEFAULT_LLM`, `EMBED_MODEL`

- [ ] **Step 1: judge_gui.py 수정**

`src/judge_gui.py` 전체를 다음으로 교체:

```python
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
```

- [ ] **Step 2: README 갱신**

`README.md`의 `## 룰 Q&A 사용법` 섹션 제목을 `## 판정 저지 사용법`으로 바꾸고, 인덱싱 블록 마지막(`python -m src.build_index build/chunks.jsonl` 다음 줄)에 추가:

```
python -m src.build_phase2_index
```

그리고 섹션 끝 설명 문단을 다음으로 교체:

```markdown
모든 답변은 `[룰 X.X.X]` / `[카드 코드 이름]` / `[Q&A ID]` 형식으로 근거를 인용하며, 근거를 찾지 못하면 그렇게 말합니다. 근거 충돌 시 공식 Q&A 재정 > 카드 텍스트 > 종합 룰 순으로 우선합니다. 인덱스 경로는 실행 위치와 무관하게 리포 루트의 `index/`로 고정됩니다.
```

`## 로드맵` 섹션의 2단계 줄을 다음으로 교체:

```markdown
- 2단계 (완료): 카드 DB(7,079장) + 공식 Q&A(2,699건) 종합 판정 저지
- 3단계 (예정): 한↔일 카드명 매핑, 대화 히스토리, 웹/메신저 배포
```

- [ ] **Step 3: 수동 검증 5문항 (GUI 또는 CLI)**

Run: `printf '...' | python -m src.judge_cli` 방식으로 다음 5문항 (또는 GUI API):
1. 일본어 카드명: "ファフニールの【ファンファーレ】은 어떻게 처리되나요?" → `[카드 SD04-...]` 또는 `[Q&A ...]` 인용 답변
2. 한국어 카드명: "로즈퀸 효과 알려줘" → ローズクイーン 카드 근거 포함 답변
3. 카드 코드: "BP01-001 효과와 관련 재정 알려줘" → `[카드 BP01-001 ...]` (거리 0.00) 포함
4. 룰 회귀: "덱은 몇 장으로 구성하나요?" → `[룰 6.1.1.x]` 인용 (1단계와 동일 수준)
5. 무관 질문: "유희왕의 체인 규칙을 설명해줘" → '제공된 자료에서 근거를 찾지 못했습니다' 또는 '관련 근거를 찾지 못했습니다'

각 답변의 인용이 참조 근거 목록에 실제 존재하는지 확인. 결과 전문을 보고서에 기록.

- [ ] **Step 4: 전체 테스트 + Commit + Push**

Run: `python -m pytest -q`
Expected: 16 passed

```bash
git add src/judge_gui.py README.md
git commit -m "feat: phase-2 ruling judge in GUI, update README"
git push
```
