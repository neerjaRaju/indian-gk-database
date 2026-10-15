import json
import sqlite3
from pathlib import Path

from scripts.build_database import build_sqlite

ROOT = Path(__file__).resolve().parents[1]


def test_sqlite_database_stores_questions_by_category(tmp_path):
    categories = json.loads((ROOT / "config" / "categories.json").read_text(encoding="utf-8"))
    source = {
        "title": "Test source",
        "url": "https://example.gov.in/test",
        "publisher": "Example publisher",
        "accessed_on": "2026-10-15",
        "license": "Unverified; editorial review required",
    }
    common = {
        "id": "history-test-en",
        "category": "history",
        "difficulty": "easy",
        "type": "mcq",
        "question": "Who was the first Mughal emperor?",
        "options": ["Babur", "Akbar", "Humayun", "Jahangir"],
        "answer_index": 0,
        "explanation": "Babur founded the Mughal Empire in India.",
        "tags": ["mughal", "history"],
        "source": source,
        "updated_at": "2026-10-15",
    }
    records = [
        {**common, "language": "en"},
        {
            **common,
            "id": "history-test-hi",
            "language": "hi",
            "question": "पहला मुगल सम्राट कौन था?",
            "options": ["बाबर", "अकबर", "हुमायूँ", "जहाँगीर"],
        },
    ]
    database_path = tmp_path / "questions.sqlite3"

    build_sqlite(database_path, records, categories)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute("""
            SELECT c.name_en, c.name_hi, q.language, q.question,
                   q.options_json, q.answer_index, q.tags_json, q.source_json
            FROM questions q
            JOIN categories c ON c.id = q.category_id
            WHERE q.category_id = ?
            ORDER BY q.language
        """, ("history",)).fetchall()

    assert len(rows) == 2
    assert rows[0][0:3] == ("Indian History", "भारतीय इतिहास", "en")
    assert rows[1][2] == "hi"
    assert json.loads(rows[0][4]) == records[0]["options"]
    assert rows[0][5] == 0
    assert json.loads(rows[0][6]) == records[0]["tags"]
    assert json.loads(rows[0][7]) == source