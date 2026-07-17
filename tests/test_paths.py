from pathlib import Path

from src import build_index, judge_cli

ROOT = Path(__file__).resolve().parent.parent


def test_default_db_anchored_to_repo_root():
    # cwd가 어디든(예: src/ 안에서 실행) 같은 인덱스를 가리켜야 한다
    assert judge_cli.DEFAULT_DB == str(ROOT / "index")
    assert build_index.DEFAULT_DB == str(ROOT / "index")
