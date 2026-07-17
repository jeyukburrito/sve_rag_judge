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


TOC_SAMPLE = """目次 ページ
1. ゲームの概要.........................................................................................1
2. カードの情報...........................................................................................2
総合ルール本文
1. ゲームの概要
1.1. このゲームは2人で対戦するカードゲームです。プレイヤーは山札を用意します。
"""


def test_toc_dot_leader_lines_produce_no_chunks():
    # 목차의 "N. 제목.....페이지" 줄은 조항 본문이 아니라 페이지 머리글이므로
    # rule_id "1", "2" 같은 가짜 청크를 만들면 안 된다
    chunks = parse_chunks(TOC_SAMPLE)
    ids = [c["rule_id"] for c in chunks]
    assert ids == ["1.1"]


APPENDIX_SAMPLE = """1. ゲームの基本
1.1. このゲームは2人で対戦するカードゲームです。プレイヤーは山札を用意します。
付録 A：トークン一覧
● 種類：フォロワー・トークン カード名 クラス タイプ コスト 攻撃力 体力 テキスト
"""


def test_appendix_marker_stops_continuation():
    # "付録" 이후의 번호 없는 표 형식 본문이 직전 조항(1.1)에 이어붙으면 안 된다
    chunks = parse_chunks(APPENDIX_SAMPLE)
    assert len(chunks) == 1
    assert "付録" not in chunks[0]["text"]
    assert "トークン一覧" not in chunks[0]["text"]


CHANGELOG_SAMPLE = """1. ゲームの基本
1.1. このゲームは2人で対戦するカードゲームです。プレイヤーは山札を用意します。
付録 C：更新項目
2026 年 6 月 9 日 ver 1.26.1 クレストに関するルールを定義しました。進化に関するルールを追加しました。
"""


def test_year_like_number_not_treated_as_rule_id():
    # 부록 C(변경 이력)의 "2026 年 6 月..." 날짜는 조항 번호가 아니다.
    # 실제 조항 번호는 최상위 자릿수가 2자리를 넘지 않는다(1~15).
    chunks = parse_chunks(CHANGELOG_SAMPLE)
    ids = [c["rule_id"] for c in chunks]
    assert "2026" not in ids
    assert ids == ["1.1"]
