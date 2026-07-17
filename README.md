# sve_rag_judge

Shadowverse Evolve 종합 룰북 PDF를 RAG(검색 증강 생성) 파이프라인에 넣기 좋은 형태로 변환하는 스크립트 모음입니다.

## 구성

- `data/ShadowverseEVOLVE_cr_1.26.1_260609.pdf` — 원본 종합 룰 PDF
- `scripts/batch_pdf_to_json.py` — 디렉터리 내 PDF들을 [`opendataloader_pdf`](https://pypi.org/project/opendataloader-pdf/)로 파싱해 원본 구조의 JSON으로 변환
- `scripts/postprocess_pdf_json.py` — 위 JSON을 페이지별 텍스트와 전체 텍스트로 후처리하여 `.processed.json`, `.txt`로 저장

## 설치

```bash
pip install opendataloader_pdf
```

## 사용법

1. PDF → JSON 변환

```bash
python scripts/batch_pdf_to_json.py <input_dir> <output_dir> [--recursive] [--quiet]
```

2. JSON → 페이지별 텍스트/전체 텍스트 후처리

```bash
python scripts/postprocess_pdf_json.py <input_dir> <output_dir> [--recursive]
```

1단계의 `output_dir`을 2단계의 `input_dir`로 넘기면 됩니다.

### 예시

```bash
python scripts/batch_pdf_to_json.py data raw_json
python scripts/postprocess_pdf_json.py raw_json processed
```

`processed/` 안에 `<파일명>.processed.json`(메타데이터 + 페이지별 텍스트 + 전체 텍스트)과 `<파일명>.txt`(전체 텍스트)가 생성됩니다.

## 룰 Q&A CLI (RAG)

사전 준비: [Ollama](https://ollama.com) 설치 후 `ollama pull bge-m3 && ollama pull qwen3:8b`

```bash
pip install -r requirements.txt

# 1회 인덱싱
python scripts/batch_pdf_to_json.py data build/raw_json
python scripts/postprocess_pdf_json.py build/raw_json build/processed
python -m src.chunk_rules build/processed/ShadowverseEVOLVE_cr_1.26.1_260609.txt build/chunks.jsonl
python -m src.build_index build/chunks.jsonl

# 질의
python -m src.judge_cli
```

모든 답변은 `[룰 X.X.X]` 형식으로 종합 룰북 조항을 인용하며, 근거를 찾지 못하면 그렇게 말합니다.

## 참고

`scripts/postprocess_pdf_json.py`의 `collect_text_by_page` 함수는 `opendataloader_pdf`가 출력하는 JSON 트리 구조(`kids`, `list items`, `content`, `page number`)에 의존합니다. 업스트림 라이브러리의 출력 스키마가 바뀌면 이 함수를 먼저 확인하세요.
