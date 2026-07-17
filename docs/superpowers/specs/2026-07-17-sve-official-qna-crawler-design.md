# SVE 공식 Q&A 크롤러 설계

날짜: 2026-07-17  
상태: 사용자 검토 대기

## 목적

Shadowverse EVOLVE 공식 Q&A 사이트의 일반 FAQ와 카드별 Q&A를 반복 실행 가능한 스크립트로 수집해 RAG 원천 데이터로 저장한다. Playwright는 사이트 구조 조사에만 사용하고, 전체 수집은 가벼운 HTTP 크롤러가 담당한다.

## 작업 경계

- 새 파일: `scripts/crawl_official_qna.py`
- 외부 데이터에서 복사: `C:\Users\Yoo\Desktop\sve-meta\data\carddb\`의 유효 CSV 50개 → `data/carddb/`
- 생성 산출물: `build/qna/questions.jsonl`, `build/qna/question_cards.jsonl`, `build/qna/checkpoint.json`
- 수정 금지: `src/**`, 기존 `tests/**`, `README.md`, `requirements.txt`, 기존 PDF 변환 스크립트

이 경계는 Claude가 진행 중인 PDF 청킹·인덱싱·CLI 작업과 겹치지 않는다.

## 확인된 사이트 구조

- 랜딩 페이지 `/question/`에 상품 링크 52개가 연도별로 모두 노출된다.
- 일반 FAQ `/question/faq/`에는 123개 항목이 있으며 페이지네이션이 없다.
- 상품 페이지 `/question/card?ex=<상품코드>`에서 카드 링크를 얻는다.
- 카드 상세 `/cardlist/?cardno=<카드번호>&faq`에 해당 카드 Q&A가 있다.
- Q&A 항목은 `.qa-List_Item`, 식별자·날짜는 `.qa-List_Ttl`, 질문은 `.qa-List_Txt-Q`, 답변은 `.qa-List_Txt-A`로 추출한다.
- 동일 Q번호가 여러 카드 인쇄본에 연결될 수 있으므로 Q&A 본문과 카드 연결을 분리한다.

## 수집 흐름

1. 일반 FAQ를 수집하고 카테고리를 기록한다.
2. 랜딩 페이지에서 52개 상품 URL을 수집한다.
3. 각 상품 페이지에서 카드 번호와 카드 상세 URL을 수집한다.
4. 카드 번호 기준으로 상세 URL을 먼저 중복 제거한다.
5. 카드 상세에서 Q&A를 추출한다.
6. Q번호 기준으로 Q&A 본문을 중복 제거하고, Q번호와 카드 번호의 다대다 연결은 별도 파일에 저장한다.
7. `data/carddb/*.csv`를 합쳐 카드 번호를 `card_code`와 연결하고 카드 메타데이터를 보강한다.
8. 완료한 카드 번호를 체크포인트에 기록해 중단 후 재실행할 수 있게 한다.

## 출력 스키마

`questions.jsonl`의 각 행:

```json
{"qa_id":"Q2625","date":"2026-05-18","scope":"card","category":null,"question":"...","answer":"...","source_url":"..."}
```

일반 FAQ는 안정적인 공식 Q번호가 없을 경우 본문 기반 결정적 ID를 생성하고 `scope`를 `general`로 기록한다.

`question_cards.jsonl`의 각 행:

```json
{"qa_id":"Q2625","card_code":"BP20-001","name":"...","class":"...","card_type":"...","sub_type":"...","cost":"...","attack":"...","hp":"...","effect":"...","source_url":"..."}
```

50개 CSV는 UTF-8-SIG, 총 6,777행이며 `card_code`가 결측·중복 없는 조인 키다. 빈 `CSC01.csv`는 제외한다. 통합본 `carddb_all.csv`는 최신 PR 카드 30개가 누락되고 현재 `PR.csv`와 겹치는 330행도 달라 사용하지 않는다. `carddb_json/`, 이미지, 분석 산출물도 복사하지 않는다.

조인은 원문 `cardno`와 `card_code`의 정확 일치를 우선한다. 실패할 때만 Unicode 정규화와 대소문자 무시 비교를 사용한다. `-SL01`, `-T01`, `-LDⓈ01` 같은 접미사와 `DSD01a`/`DSD01b`, `CSD03a` 같은 표기는 삭제하거나 대문자로 덮어쓰지 않는다.

## 네트워크·오류 처리

- 동시성 없이 순차 요청한다.
- 요청 사이에 기본 지연을 두고 CLI 옵션으로 조절할 수 있게 한다.
- 일시적 HTTP/연결 오류는 제한 횟수만 재시도한다.
- 페이지 구조가 예상과 다르면 조용히 빈 결과로 넘기지 않고 실패 URL을 표시한다.
- 출력은 임시 파일에 쓴 뒤 교체해 중단 시 기존 결과를 보존한다.
- `robots.txt`는 Playwright 환경에서 확인하지 못했으므로 실행 전 스크립트가 직접 조회하고, 명시적으로 금지된 경로는 수집하지 않는다.

## 구현 선택

HTTP 요청은 `requests`, HTML 파싱은 `BeautifulSoup`을 사용한다. 두 패키지가 환경에 없으면 설치 명령을 안내하고 종료한다. Claude 작업과의 충돌을 피하기 위해 이번 작업에서는 `requirements.txt`를 수정하지 않는다.

## 검증

- 네트워크 없이 실행 가능한 HTML fixture 기반 자체 테스트로 FAQ/Q&A 추출, Q번호 파싱, 중복 제거, 카드 CSV 조인을 확인한다.
- 샘플 모드로 일반 FAQ와 상품 1개만 수집해 JSONL 파싱, 필수 필드, 중복 키 부재를 확인한다.
- 기존 프로젝트 테스트 `python -m pytest -v`도 마지막에 실행해 회귀가 없는지 확인한다.

## 제외 범위

- 전체 크롤링을 이 작업 중 강제로 완료하는 것
- 일본어 Q&A의 한국어 번역
- Q&A를 ChromaDB에 직접 적재하는 작업
- 카드 이미지 복사
- 기존 RAG 코드나 문서 수정
