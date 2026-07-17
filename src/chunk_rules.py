import argparse
import json
import re
from pathlib import Path

RULE_RE = re.compile(r"^(\d{1,2}(?:\.\d+)*)\.?\s+")
MIN_BODY_LEN = 25  # 이보다 짧으면 제목으로 간주하고 다음 조항 앞에 붙인다

# 목차(TOC)의 "N. 제목..........페이지" 줄은 점(dot) 3개 이상의 리더로 페이지
# 번호를 채운다. 실제 조항 본문에는 이런 패턴이 나타나지 않으므로 노이즈로 제거한다.
TOC_DOT_LEADER_RE = re.compile(r"\.{3,}")

# 부록(付録) 표제는 조항 번호 체계 밖의 내용(카드/토큰 표, 서식 등)이 시작됨을
# 뜻한다. 번호 없는 표 형식 본문이 직전 조항에 계속 이어붙는 것을 막기 위해
# 여기서 진행 중이던 청크를 마감한다.
APPENDIX_RE = re.compile(r"^付録")


def parse_chunks(text: str) -> list[dict]:
    raw: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if TOC_DOT_LEADER_RE.search(line):
            continue
        if APPENDIX_RE.match(line):
            if current:
                raw.append(current)
                current = None
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
