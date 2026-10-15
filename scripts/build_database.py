import argparse, gzip, hashlib, json, os, shutil
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "data" / "source"
GENERATED_DIR = ROOT / "data" / "generated"
DIST = ROOT / "dist"

def dump_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    parser = argparse.ArgumentParser(description="Build database JSON artifacts.")
    parser.add_argument("--include-generated", action="store_true", help="include data/generated/ review records")
    args = parser.parse_args()
    if DIST.exists():
        for path in DIST.iterdir():
            if path.name == ".gitkeep":
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    else:
        DIST.mkdir(parents=True)
    records = []
    source_dirs = [SOURCE_DIR]
    if args.include_generated:
        source_dirs.append(GENERATED_DIR)
    for directory in source_dirs:
        for source in sorted(directory.glob("*.json")):
            data = json.loads(source.read_text(encoding="utf-8"))
            records.extend(data)
    records.sort(key=lambda q: q["id"])
    version = os.environ.get("DATABASE_VERSION", "dev")
    build_time = datetime.now(timezone.utc).isoformat()
    dump_json(DIST / "questions.json", records)
    with (DIST / "questions.json").open("rb") as src, gzip.open(DIST / "questions.json.gz", "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    for language in ("en", "hi"):
        dump_json(DIST / f"questions.{language}.json", [q for q in records if q["language"] == language])
    for category in sorted({q["category"] for q in records}):
        dump_json(DIST / f"category-{category}.json", [q for q in records if q["category"] == category])
    manifest = {
        "schema_version": 1,
        "database_version": version,
        "built_at_utc": build_time,
        "question_count": len(records),
        "language_counts": {lang: sum(q["language"] == lang for q in records) for lang in ("en", "hi")},
        "categories": sorted({q["category"] for q in records}),
        "files": {}
    }
    for p in sorted(DIST.iterdir()):
        if p.is_file() and p.name != ".gitkeep":
            manifest["files"][p.name] = {"size_bytes": p.stat().st_size, "sha256": sha256(p)}
    dump_json(DIST / "manifest.json", manifest)
    print(json.dumps({"version": version, "count": len(records), "dist": str(DIST)}, indent=2))

if __name__ == "__main__":
    main()
