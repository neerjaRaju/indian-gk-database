"""Lightweight source metadata policy check; does not fact-check answers."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
issues = []
for path in sorted((ROOT / "data/source").glob("*.json")):
    for i, q in enumerate(json.loads(path.read_text(encoding="utf-8"))):
        src = q.get("source", {})
        for field in ("title", "url", "publisher", "accessed_on", "license"):
            if not src.get(field):
                issues.append(f"{path.name}[{i}] ({q.get('id')}): missing source.{field}")
        if src.get("license", "").lower().startswith(("unknown", "todo", "tbd", "unverified")):
            issues.append(f"{path.name}[{i}] ({q.get('id')}): source license needs review")
if issues:
    raise SystemExit("\n".join(issues))
print("Source metadata checks passed.")
