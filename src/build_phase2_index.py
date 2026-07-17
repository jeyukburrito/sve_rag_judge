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
