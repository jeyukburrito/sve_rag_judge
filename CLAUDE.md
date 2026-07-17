# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Two standalone Python scripts for turning PDFs into plain text/JSON via the `opendataloader_pdf` package. There is no package manifest, build system, or test suite in this directory — each script is run directly with `python`.

## Layout

- `scripts/` — the two pipeline scripts
- `data/` — source PDF(s) to process

## Commands

Install the one dependency (not currently installed in this environment):

```
pip install opendataloader_pdf
```

Convert all PDFs in a directory to raw `opendataloader_pdf` JSON:

```
python scripts/batch_pdf_to_json.py <input_dir> <output_dir> [--recursive] [--quiet]
```

Post-process that raw JSON into per-page text and a flat `.txt`/`.processed.json`:

```
python scripts/postprocess_pdf_json.py <input_dir> <output_dir> [--recursive]
```

Typical pipeline: run `batch_pdf_to_json.py` on `data/` (or another folder of PDFs), then feed its `output_dir` as the `input_dir` for `postprocess_pdf_json.py`.

## Architecture

- `scripts/batch_pdf_to_json.py` — finds `*.pdf` files in a directory (optionally recursive), calls `opendataloader_pdf.convert(...)` once with the full file list, and writes one JSON file per PDF to `output_dir`.
- `scripts/postprocess_pdf_json.py` — reads each `opendataloader_pdf`-format JSON file and walks its nested `kids`/`list items` tree (`collect_text_by_page`) to pull out text `content` nodes keyed by `page number`. It normalizes whitespace per line, joins lines per page, then joins pages into one document. For each input file it writes two outputs: `<stem>.processed.json` (metadata + per-page text + full text) and `<stem>.txt` (full text only).

The `opendataloader_pdf` JSON tree shape (`kids`, `list items`, `content`, `page number`) is the load-bearing assumption in `scripts/postprocess_pdf_json.py::collect_text_by_page` — if the upstream library's output schema changes, that function is the one to update.

## 프로젝트 지침

이 프로젝트를 수행할때 작업 수행시 서브에이전트 호출을 권장하며, agency agents에 있는 persona를 호출하여 사용한다.
메인 에이전트의 역할은 오케스트레이터이다.
가능한 경우 서브에이전트를 병렬로 호출하는 것이 권장된다.

### 에이전트 분업 규칙 (Fable 모델 사용 시 특히 준수)

- 메인 에이전트는 전체 계획, 작업 분배, 결과 통합, 최종 검증만 담당한다. 복잡한 작업만 메인이 직접 처리하고 대부분의 업무는 서브 에이전트가 처리한다.
- 요청을 먼저 확인하고, 독립적으로 처리 가능한 작업이 2개 이상일 때만 서브 에이전트에 위임한다.
- 서브 에이전트는 최대 3개까지만 동시 실행하고 다음 작업을 나눠 맡긴다:
  - 관련 파일과 영향 범위 조사
  - 자료 조사와 정보 정리
  - 독립된 기능 구현
  - 테스트 작성과 오류 확인
- 서브 에이전트끼리 같은 파일을 동시에 수정하지 않는다.
- 작업 분할이 오히려 비효율적인 경우 서브 에이전트를 쓰지 않고 메인 에이전트가 직접 처리한다.
- 사용자가 지정한 파일만 수정하고 요청하지 않은 기능은 추가하지 않는다.
- 모든 결과는 메인 에이전트가 다시 확인하고 하나로 통합한다.
- 마지막에는 반드시 테스트를 실행하고 성공 여부와 수정한 파일만 짧게 보고한다.
- 서브 에이전트 위임 기능을 사용할 수 없다면 실행한 척하지 말고 사용할 수 없다고 알린다.
- 서브 에이전트는 Sonnet이나 Opus 같은 하위 모델을 사용한다 (메인 에이전트 모델인 Fable을 서브에 쓰지 않는다).
