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


from src.judge_cli import extract_card_codes


def test_extract_card_codes_basic():
    assert extract_card_codes("BP01-001과 SD04-001의 상호작용은?") == ["BP01-001", "SD04-001"]


def test_extract_card_codes_lowercase_set_suffix():
    assert extract_card_codes("CSD02a-015 효과 알려줘") == ["CSD02a-015"]


def test_extract_card_codes_none():
    assert extract_card_codes("진화는 언제 할 수 있나요?") == []


def test_extract_card_codes_dedup():
    assert extract_card_codes("BP01-001 그리고 또 BP01-001") == ["BP01-001"]
