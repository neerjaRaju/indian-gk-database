import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def all_questions():
    result = []
    for path in (ROOT / "data/source").glob("*.json"):
        result.extend(json.loads(path.read_text(encoding="utf-8")))
    return result

def test_question_ids_are_unique():
    qs = all_questions()
    ids = [q["id"] for q in qs]
    assert len(ids) == len(set(ids))

def test_bilingual_content_exists_in_seed_data():
    qs = all_questions()
    assert any(q.get("language") == "en" for q in qs)
    assert any(q.get("language") == "hi" for q in qs)

def test_answers_are_in_range():
    for q in all_questions():
        assert isinstance(q["answer_index"], int)
        assert 0 <= q["answer_index"] < len(q["options"])

def test_every_question_has_source_metadata():
    for q in all_questions():
        src = q["source"]
        assert src["title"] and src["url"] and src["publisher"]
        assert src["accessed_on"] and src["license"]
