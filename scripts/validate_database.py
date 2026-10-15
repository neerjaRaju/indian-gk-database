import json
import sys
import argparse
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "data" / "source"
GENERATED_DIR = ROOT / "data" / "generated"
SCHEMA_PATH = ROOT / "data" / "schema" / "question.schema.json"
ALLOWED_CATEGORIES = {x["id"] for x in json.loads((ROOT / "config/categories.json").read_text(encoding="utf-8"))}
EXPECTED_TOTAL = int(__import__("os").environ.get("EXPECTED_QUESTION_COUNT", "0"))

def main():
    parser = argparse.ArgumentParser(description="Validate source question records.")
    parser.add_argument("--include-generated", action="store_true", help="also validate data/generated/ review records")
    args = parser.parse_args()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors, all_ids, total, languages = [], set(), 0, {"en": 0, "hi": 0}
    source_dirs = [SOURCE_DIR]
    if args.include_generated:
        source_dirs.append(GENERATED_DIR)
    files = sorted(path for directory in source_dirs for path in directory.glob("*.json"))
    if not files:
        errors.append("No source JSON files found.")
    for path in files:
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{path.relative_to(ROOT)}: invalid JSON: {exc}")
            continue
        if not isinstance(records, list):
            errors.append(f"{path.relative_to(ROOT)}: root must be an array")
            continue
        file_ids = set()
        for index, record in enumerate(records):
            location = f"{path.relative_to(ROOT)}[{index}]"
            if not isinstance(record, dict):
                errors.append(f"{location}: record must be an object")
                continue
            for err in validator.iter_errors(record):
                errors.append(f"{location}: {'/'.join(map(str, err.absolute_path))}: {err.message}")
            qid = record.get("id")
            if qid:
                if qid in file_ids or qid in all_ids:
                    errors.append(f"{location}: duplicate ID {qid}")
                file_ids.add(qid)
                all_ids.add(qid)
            if record.get("category") not in ALLOWED_CATEGORIES:
                errors.append(f"{location}: unknown category {record.get('category')!r}")
            opts, answer = record.get("options"), record.get("answer_index")
            if isinstance(opts, list) and isinstance(answer, int) and not isinstance(answer, bool):
                if not 0 <= answer < len(opts):
                    errors.append(f"{location}: answer_index outside options range")
                if len(opts) != len(set(opts)):
                    errors.append(f"{location}: duplicate option strings")
            if record.get("language") in languages:
                languages[record["language"]] += 1
            total += 1
    if EXPECTED_TOTAL and total != EXPECTED_TOTAL:
        errors.append(f"Expected {EXPECTED_TOTAL} questions but found {total}.")
    if errors:
        print("\n".join(f"ERROR: {e}" for e in errors), file=sys.stderr)
        print(f"Validation failed: {len(errors)} issue(s); {total} records scanned.", file=sys.stderr)
        return 1
    print(f"Validation passed: {total} questions; English={languages['en']}; Hindi={languages['hi']}.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
