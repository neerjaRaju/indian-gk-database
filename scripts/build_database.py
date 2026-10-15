import gzip, hashlib, json, os, shutil
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "data" / "source"
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
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    records = []
    for source in sorted(SOURCE_DIR.glob("*.json")):
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
        if p.is_file():
            manifest["files"][p.name] = {"size_bytes": p.stat().st_size, "sha256": sha256(p)}
    dump_json(DIST / "manifest.json", manifest)
    print(json.dumps({"version": version, "count": len(records), "dist": str(DIST)}, indent=2))

if __name__ == "__main__":
    main()
