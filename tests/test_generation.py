import pytest
from jsonschema import Draft202012Validator, FormatChecker

from scripts.collect_sources import validate_source
from scripts.generate_questions import call_gemini, records_for, validate_pair
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def test_collector_requires_explicit_license_approval():
    source = {
        "id": "rbi-economy",
        "category": "economy",
        "title": "Economy data",
        "publisher": "Reserve Bank of India",
        "url": "https://example.gov.in/data",
        "license": "CC-BY-4.0",
        "license_url": "https://example.gov.in/license",
        "reuse_approved": False,
    }

    with pytest.raises(ValueError, match="reuse_approved"):
        validate_source(source, {"economy"})


def test_generated_pair_becomes_two_schema_shaped_records():
    source = {
        "id": "open-economy-data",
        "category": "economy",
        "title": "Economy data",
        "publisher": "Example Publisher",
        "url": "https://example.gov.in/data",
        "accessed_on": "2026-10-15",
        "license": "Government Open Data License - India (GODL)",
        "license_url": "https://example.gov.in/license",
    }
    pair = {
        "slug": "inflation-index",
        "difficulty": "easy",
        "question_en": "Which index measures retail inflation?",
        "options_en": ["CPI", "IIP", "WPI", "GDP"],
        "question_hi": "खुदरा महंगाई को कौन-सा सूचकांक मापता है?",
        "options_hi": ["सीपीआई", "आईआईपी", "डब्ल्यूपीआई", "जीडीपी"],
        "answer_index": 0,
        "explanation_en": "The Consumer Price Index tracks retail prices.",
        "explanation_hi": "उपभोक्ता मूल्य सूचकांक खुदरा कीमतों को मापता है।",
        "tags": ["inflation"],
    }

    records = records_for(source, [pair], "2026-10-15")

    assert [record["language"] for record in records] == ["en", "hi"]
    assert [record["answer_index"] for record in records] == [0, 0]
    assert records[0]["id"] == "open-economy-data-inflation-index-en"
    assert records[1]["source"] == records[0]["source"]
    schema = json.loads((ROOT / "data" / "schema" / "question.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assert all(not list(validator.iter_errors(record)) for record in records)


def test_generator_rejects_non_object_pair():
    with pytest.raises(ValueError, match="must be an object"):
        validate_pair([])


def test_gemini_request_keeps_key_out_of_url(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b'{"candidates":[{"content":{"parts":[{"text":"{\\"questions\\":[]}"}]}}]}'

    def fake_urlopen(request, timeout):
        assert "test-secret" not in request.full_url
        assert request.get_header("X-goog-api-key") == "test-secret"
        assert timeout == 90
        return FakeResponse()

    monkeypatch.setattr("scripts.generate_questions.urlopen", fake_urlopen)

    assert call_gemini("prompt", "test-secret", "gemini-test") == {"questions": []}