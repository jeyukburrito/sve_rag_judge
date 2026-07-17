# SVE 2단계 — 카드 DB + 공식 Q&A 판정 저지 설계 문서

날짜: 2026-07-17
상태: 승인됨

## 목적

1단계 룰 Q&A에 카드 DB(13,903장)와 공식 Q&A(2,699건)를 추가해, 특정 카드가 얽힌 판정(룰링) 질문에 종합 근거로 답하는 저지로 확장한다. 사용 방식은 기존과 동일한 단일 채팅(CLI/GUI) — 질문이 들어오면 세 소스를 모두 검색해 종합 판정한다.

## 데이터

- `data/carddb/*.csv` (52파일, 13,903행): card_code, name, class, card_type, sub_type, cost, attack, hp, effect (일본어)
- `data/qna/unique_qna.jsonl` (2,699행): qa_id, date, scope, category, question, answer, source_url, cards(연결 카드 배열)

## 인덱싱

기존 `index/` ChromaDB에 컬렉션 추가 (모두 cosine):

| 컬렉션 | 건수 | 문서 형식 | 메타데이터 |
|---|---|---|---|
| `rules` | 659 | (기존 그대로, 재구축 없음) | rule_id, parent |
| `cards` | 13,903 | `"{code} {name} / クラス:{class} / {card_type}({sub_type}) / コスト{cost} 攻{attack} 体{hp} / 効果: {effect}"` | card_code, name, class, card_type |
| `qna` | 2,699 | `"Q: {question}\nA: {answer}"` | qa_id, category, cards(콤마 문자열), date |

- `src/build_index.py`의 임베딩+저장 루프를 `index_documents()` 헬퍼로 추출(기존 CLI 동작 불변), 신규 `src/build_phase2_index.py`가 재사용
- 재실행 시 해당 컬렉션 삭제 후 전체 재구축 (기존 패턴)
- 소요: CPU 기준 1회 40~60분, GPU 인식 시 수 분 (Ollama가 GPU 자동 사용; 구현 시 `ollama ps`로 확인)

## 검색·판정

1. 질문에서 카드 코드 정규식(`[A-Z]+\d+[a-zA-Z]*-\d+`) 추출 → `cards` 컬렉션 메타데이터 정확 조회, 항상 컨텍스트 포함
2. 질문 임베딩 1회 → 소스별 쿼터 검색: rules top-6, cards top-4, qna top-4
3. 거리 게이트 0.75 소스별 동일 적용. 세 소스 모두 통과 항목 없으면 LLM 호출 없이 "관련 근거를 찾지 못했습니다"
4. SYSTEM_PROMPT v2: 소스 라벨 구분 전달, 우선순위 명시(개별 카드 Q&A 재정 > 카드 텍스트 > 종합 룰), 인용 필수, 근거 부족 시 "제공된 자료에서 근거를 찾지 못했습니다"
5. 인용 형식: `[룰 X.X.X]` / `[카드 {code} {name}]` / `[Q&A {qa_id}]`
6. 답변 뒤 참조 근거 목록(소스 태그 포함) 표시 — 기존 UX 유지

기존 `judge_cli.py`의 retrieve/answer를 확장하고, GUI는 import 재사용이므로 자동 반영.

## 에러 처리

- 시작 시 세 컬렉션 체크: `cards`/`qna` 없거나 비면 "2단계 인덱스가 없습니다. 먼저 실행하세요: python -m src.build_phase2_index" 후 종료
- 카드 코드가 질문에 있으나 DB에 없으면: 해당 코드는 무시하고 임베딩 검색 결과로만 진행 (컨텍스트에 "코드 미발견" 표시)

## 테스트

- 자동(pytest, LLM/DB 불필요): 카드 행→문서 포맷, Q&A 행→문서 포맷, 카드 코드 정규식 추출 3종
- 수동 5문항: ① 일본어 카드명 판정 ② 한국어 카드명 판정 ③ 카드 코드 지정 판정 ④ 룰 질문 회귀 ⑤ 무관 질문 거부

## 제약

- 전부 무료/로컬 (Ollama bge-m3 + qwen3, ChromaDB)
- 한국어 카드명 매칭은 다국어 임베딩에 의존 — 정확도 부족 시 한↔일 카드명 매핑 테이블은 3단계에서

## 의도적으로 뺀 것

한↔일 카드명 매핑 테이블, 대화 히스토리, 에이전틱 라우팅, 리랭커, 카드 이미지.
