import io
import pytest
from email.message import Message
from jsonschema import Draft202012Validator, FormatChecker
from urllib.error import HTTPError

from scripts.collect_sources import validate_source
from scripts.generate_questions import (
    call_gemini,
    existing_slugs,
    generate_pairs,
    main,
    merge_new_records_first,
    records_for,
    validate_pair,
)
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


def test_generation_batches_more_than_twenty_pairs(monkeypatch):
    calls = []

    def fake_call_gemini(prompt, api_key, model):
        count = int(prompt.split("Create exactly ", 1)[1].split(" ", 1)[0])
        start = sum(call[0] for call in calls)
        calls.append((count, prompt))
        return {"questions": [
            {
                "slug": f"history-fact-{index}",
                "difficulty": "easy",
                "question_en": f"English question {index}?",
                "options_en": ["A", "B", "C", "D"],
                "question_hi": f"हिंदी प्रश्न {index}?",
                "options_hi": ["क", "ख", "ग", "घ"],
                "answer_index": 0,
                "explanation_en": "Supported explanation.",
                "explanation_hi": "समर्थित स्पष्टीकरण।",
                "tags": ["history"],
                "source_title": "Suggested official source",
                "source_url": "https://example.gov.in/history",
                "source_publisher": "Example Government Publisher",
            }
            for index in range(start, start + count)
        ]}

    monkeypatch.setattr("scripts.generate_questions.call_gemini", fake_call_gemini)

    pairs = generate_pairs("history", 21, "test-key", "test-model")

    assert len(pairs) == 21
    assert [call[0] for call in calls] == [20, 1]
    assert "history-fact-0" in calls[1][1]


def test_existing_category_slugs_are_excluded_and_new_records_prepend(monkeypatch):
    old_records = [
        {"id": f"history-previous-question-{index}-{'en' if index % 2 == 0 else 'hi'}"}
        for index in range(112)
    ]
    old_slugs = existing_slugs("history", old_records)
    prompts = []

    def fake_call_gemini(prompt, api_key, model):
        prompts.append(prompt)
        return {"questions": [{
            "slug": "new-history-question",
            "difficulty": "easy",
            "question_en": "A new question?",
            "options_en": ["A", "B", "C", "D"],
            "question_hi": "नया प्रश्न?",
            "options_hi": ["क", "ख", "ग", "घ"],
            "answer_index": 0,
            "explanation_en": "Explanation.",
            "explanation_hi": "व्याख्या।",
            "tags": ["history"],
            "source_title": "Suggested source",
            "source_url": "https://example.gov.in/history",
            "source_publisher": "Example Publisher",
        }]}

    monkeypatch.setattr("scripts.generate_questions.call_gemini", fake_call_gemini)
    pairs = generate_pairs("history", 1, "test-key", "test-model", excluded_slugs=old_slugs)
    new_records = records_for(None, pairs, "2026-10-15", category="history")
    merged = merge_new_records_first(new_records, old_records)

    assert len(old_slugs) == 112
    assert "previous-question-0" in prompts[0]
    assert len(merged) == 114
    assert merged[:2] == new_records
    assert merged[2:] == old_records


def test_generation_regenerates_batch_with_non_array_options(monkeypatch):
    valid_pair = {
        "slug": "geography-river-source",
        "difficulty": "easy",
        "question_en": "Which river rises in the Himalayas?",
        "options_en": ["Ganga", "Godavari", "Kaveri", "Narmada"],
        "question_hi": "कौन-सी नदी हिमालय से निकलती है?",
        "options_hi": ["गंगा", "गोदावरी", "कावेरी", "नर्मदा"],
        "answer_index": 0,
        "explanation_en": "The Ganga rises in the Himalayas.",
        "explanation_hi": "गंगा हिमालय से निकलती है।",
        "tags": ["rivers"],
        "source_title": "Suggested geography source",
        "source_url": "https://example.gov.in/rivers",
        "source_publisher": "Example Government Publisher",
    }
    malformed_pair = {**valid_pair, "options_en": "Ganga, Godavari, Kaveri, Narmada"}
    prompts = []

    def fake_call_gemini(prompt, api_key, model):
        prompts.append(prompt)
        pair = malformed_pair if len(prompts) == 1 else valid_pair
        return {"questions": [pair]}

    monkeypatch.setattr("scripts.generate_questions.call_gemini", fake_call_gemini)

    pairs = generate_pairs("geography", 1, "test-key", "test-model")

    assert len(pairs) == 1
    assert len(prompts) == 2
    assert "previous response failed validation" in prompts[1]


def test_generation_retries_invalid_suggested_source_url(monkeypatch):
    valid_pair = {
        "slug": "environment-biodiversity",
        "difficulty": "easy",
        "question_en": "What does biodiversity describe?",
        "options_en": ["Variety of life", "Rainfall", "Soil depth", "Wind speed"],
        "question_hi": "जैव विविधता किसका वर्णन करती है?",
        "options_hi": ["जीवन की विविधता", "वर्षा", "मिट्टी की गहराई", "हवा की गति"],
        "answer_index": 0,
        "explanation_en": "Biodiversity is the variety of living organisms.",
        "explanation_hi": "जैव विविधता जीवों की विविधता है।",
        "tags": ["biodiversity"],
        "source_title": "Suggested environment source",
        "source_url": "https://example.gov.in/environment",
        "source_publisher": "Example Government Publisher",
    }
    prompts = []

    def fake_call_gemini(prompt, api_key, model):
        prompts.append(prompt)
        pair = dict(valid_pair)
        if len(prompts) < 3:
            pair["source_url"] = "www.example.gov.in/environment"
        return {"questions": [pair]}

    monkeypatch.setattr("scripts.generate_questions.call_gemini", fake_call_gemini)

    pairs = generate_pairs("environment", 1, "test-key", "test-model")

    assert pairs[0]["source_url"] == valid_pair["source_url"]
    assert len(prompts) == 3
    assert "source_url must be an absolute HTTPS URL" in prompts[1]
    assert "plain, absolute HTTPS URL with a hostname" in prompts[2]


def test_generator_refreshes_sqlite_after_writing_category_json(tmp_path, monkeypatch):
    pair = {
        "slug": "history-founding-emperor",
        "difficulty": "easy",
        "question_en": "Who founded the Mughal Empire in India?",
        "options_en": ["Babur", "Akbar", "Humayun", "Jahangir"],
        "question_hi": "भारत में मुगल साम्राज्य की स्थापना किसने की?",
        "options_hi": ["बाबर", "अकबर", "हुमायूँ", "जहाँगीर"],
        "answer_index": 0,
        "explanation_en": "Babur founded Mughal rule in India.",
        "explanation_hi": "बाबर ने भारत में मुगल शासन की स्थापना की।",
        "tags": ["mughal"],
        "source_title": "Suggested history source",
        "source_url": "https://example.gov.in/history",
        "source_publisher": "Example Government Publisher",
    }
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("sys.argv", [
        "generate_questions.py", "--category", "history", "--count", "1",
        "--output-dir", str(tmp_path),
    ])
    existing_records = [
        {"id": f"history-existing-question-{index}-en", "category": "history"}
        for index in range(112)
    ]
    (tmp_path / "history.json").write_text(json.dumps(existing_records), encoding="utf-8")
    generation_args = []

    def fake_generate_pairs(*args, **kwargs):
        generation_args.append((args, kwargs))
        return [pair]

    monkeypatch.setattr("scripts.generate_questions.generate_pairs", fake_generate_pairs)
    build_calls = []

    def fake_run(command, cwd, check):
        output_records = json.loads((tmp_path / "history.json").read_text(encoding="utf-8"))
        build_calls.append((command, cwd, check, output_records))

    monkeypatch.setattr("scripts.generate_questions.subprocess.run", fake_run)

    assert main() == 0

    assert len(build_calls) == 1
    command, cwd, check, output_records = build_calls[0]
    assert Path(command[-2]).name == "build_database.py"
    assert command[-1] == "--include-generated"
    assert cwd == ROOT
    assert check is True
    assert len(output_records) == 114
    assert output_records[:2][0]["id"] == "history-history-founding-emperor-en"
    assert output_records[2:] == existing_records
    assert len(generation_args[0][1]["excluded_slugs"]) == 112


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
        assert timeout == 180
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


def test_gemini_retries_read_timeout(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b'{"candidates":[{"content":{"parts":[{"text":"{\\"questions\\":[]}"}]}}]}'

    calls = 0
    delays = []

    def fake_urlopen(_request, timeout):
        nonlocal calls
        assert timeout == 180
        calls += 1
        if calls == 1:
            raise TimeoutError("The read operation timed out")
        return FakeResponse()

    monkeypatch.setattr("scripts.generate_questions.urlopen", fake_urlopen)
    monkeypatch.setattr("scripts.generate_questions.time.sleep", delays.append)

    assert call_gemini("prompt", "test-secret", "gemini-test") == {"questions": []}
    assert calls == 2
    assert delays == [1]


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