import io
import pytest
from email.message import Message
from jsonschema import Draft202012Validator, FormatChecker
from urllib.error import HTTPError

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


def test_gemini_only_pair_becomes_unverified_review_draft():
    pair = {
        "slug": "gva-agriculture-share",
        "difficulty": "easy",
        "question_en": "What share did agriculture and allied sectors contribute to GVA in 2020-21?",
        "options_en": ["20.4%", "18.3%", "17.6%", "18.9%"],
        "question_hi": "2020-21 में कृषि और संबद्ध क्षेत्रों का GVA में कितना हिस्सा था?",
        "options_hi": ["20.4%", "18.3%", "17.6%", "18.9%"],
        "answer_index": 0,
        "explanation_en": "The suggested source reports a 20.4 percent share for 2020-21.",
        "explanation_hi": "सुझाए गए स्रोत में 2020-21 के लिए 20.4 प्रतिशत हिस्सा दिया गया है।",
        "tags": ["gva", "agriculture"],
        "source_title": "Agriculture share in total GVA",
        "source_url": "https://example.gov.in/economy/gva",
        "source_publisher": "Example Government Publisher",
    }

    records = records_for(None, [pair], "2026-10-15", category="economy")

    assert [record["language"] for record in records] == ["en", "hi"]
    assert all(record["source"]["license"].startswith("Unverified") for record in records)
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


def test_gemini_wraps_bare_question_array(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b'{"candidates":[{"content":{"parts":[{"text":"[{\\"slug\\":\\"test\\"}]"}]}}]}'

    monkeypatch.setattr("scripts.generate_questions.urlopen", lambda *_args, **_kwargs: FakeResponse())

    assert call_gemini("prompt", "test-secret", "gemini-test") == {"questions": [{"slug": "test"}]}


def test_gemini_retries_temporary_service_unavailable(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b'{"candidates":[{"content":{"parts":[{"text":"{\\"questions\\":[]}"}]}}]}'

    calls = 0
    delays = []

    def fake_urlopen(request, timeout):
        nonlocal calls
        calls += 1
        if calls < 3:
            headers = Message()
            headers["Retry-After"] = "0"
            raise HTTPError(request.full_url, 503, "Unavailable", headers, io.BytesIO(b'{"error":{"message":"busy"}}'))
        return FakeResponse()

    monkeypatch.setattr("scripts.generate_questions.urlopen", fake_urlopen)
    monkeypatch.setattr("scripts.generate_questions.time.sleep", delays.append)

    assert call_gemini("prompt", "test-secret", "gemini-test") == {"questions": []}
    assert calls == 3
    assert delays == [0.0, 0.0]


def test_gemini_uses_fallback_model_after_primary_503s(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b'{"candidates":[{"content":{"parts":[{"text":"{\\"questions\\":[]}"}]}}]}'

    calls_by_model = {}

    def fake_urlopen(request, timeout):
        model = request.full_url.split("/models/")[1].split(":")[0]
        calls_by_model[model] = calls_by_model.get(model, 0) + 1
        if model == "primary-model":
            raise HTTPError(request.full_url, 503, "Unavailable", Message(), io.BytesIO(b"busy"))
        return FakeResponse()

    monkeypatch.setattr("scripts.generate_questions.urlopen", fake_urlopen)
    monkeypatch.setattr("scripts.generate_questions.time.sleep", lambda _: None)

    assert call_gemini("prompt", "test-secret", "primary-model") == {"questions": []}
    assert calls_by_model == {"primary-model": 4, "gemini-3.5-flash-lite": 1}