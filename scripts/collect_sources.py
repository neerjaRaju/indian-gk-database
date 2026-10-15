import argparse
import json
import os
import re
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "config" / "source_catalog.json"
DEFAULT_OUTPUT = ROOT / "data" / "collected" / "sources.json"
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARACTERS = 20000
ALLOWED_LICENSES = {
    "CC0-1.0",
    "CC-BY-4.0",
    "Government Open Data License - India (GODL)",
    "Public Domain",
}


class PageTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "nav", "header", "footer", "noscript", "svg"}:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "nav", "header", "footer", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data):
        if not self.skip_depth:
            text = " ".join(data.split())
            if text:
                self.parts.append(text)


def load_categories():
    categories = json.loads((ROOT / "config" / "categories.json").read_text(encoding="utf-8"))
    return {item["id"] for item in categories}


def validate_source(source, allowed_categories):
    required = ("id", "category", "title", "publisher", "url", "license", "license_url")
    missing = [field for field in required if not source.get(field)]
    if missing:
        raise ValueError(f"missing fields: {', '.join(missing)}")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", source["id"]):
        raise ValueError("id must be lowercase kebab-case")
    if source["category"] not in allowed_categories:
        raise ValueError(f"unknown category {source['category']!r}")
    if source.get("reuse_approved") is not True:
        raise ValueError("reuse_approved must be true after a human license review")
    if source["license"] not in ALLOWED_LICENSES:
        raise ValueError(f"license must be one of: {', '.join(sorted(ALLOWED_LICENSES))}")
    for field in ("url", "license_url"):
        parsed = urlparse(source[field])
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"{field} must be an absolute HTTPS URL")
    if "api_resource_id" in source:
        if urlparse(source["url"]).hostname not in {"data.gov.in", "www.data.gov.in"}:
            raise ValueError("api_resource_id is supported only for data.gov.in resources")
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", source["api_resource_id"]):
            raise ValueError("api_resource_id must be a UUID")


def fetch_text(source):
    request = Request(
        source["url"],
        headers={"User-Agent": "IndianGKDatabaseSourceCollector/1.0", "Accept": "text/html,text/plain"},
    )
    with urlopen(request, timeout=20) as response:
        final_url = response.geturl()
        if urlparse(final_url).hostname != urlparse(source["url"]).hostname:
            raise ValueError("redirect changed the source host; review the redirect before collection")
        content_type = response.headers.get_content_type()
        if content_type not in {"text/html", "text/plain"}:
            raise ValueError(f"unsupported content type {content_type!r}; only HTML and plain text are collected")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError(f"response exceeds {MAX_RESPONSE_BYTES} bytes")
    decoded = raw.decode("utf-8", errors="replace")
    if content_type == "text/html":
        parser = PageTextParser()
        parser.feed(decoded)
        decoded = " ".join(parser.parts)
    text = " ".join(decoded.split())[:MAX_TEXT_CHARACTERS]
    if len(text) < 100:
        raise ValueError("collected page has too little readable text")
    return final_url, text


def fetch_ogd_records(source):
    api_key = os.environ.get("DATA_GOV_API_KEY")
    if not api_key:
        raise ValueError("set DATA_GOV_API_KEY to fetch data.gov.in table rows")
    endpoint = f"https://api.data.gov.in/resource/{source['api_resource_id']}?{urlencode({'api-key': api_key, 'format': 'json', 'limit': 100})}"
    request = Request(endpoint, headers={"User-Agent": "IndianGKDatabaseSourceCollector/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=30) as response:
        content_type = response.headers.get_content_type()
        if content_type != "application/json":
            raise ValueError(f"data.gov.in API returned unsupported content type {content_type!r}")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError(f"API response exceeds {MAX_RESPONSE_BYTES} bytes")
    payload = json.loads(raw.decode("utf-8"))
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list) or not records:
        raise ValueError("data.gov.in API returned no records")
    text = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    return source["url"], text


def main():
    parser = argparse.ArgumentParser(description="Collect text only from explicitly reviewed, reuse-approved sources.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    try:
        catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
        if not isinstance(catalog, list) or not catalog:
            raise ValueError("source catalogue must be a non-empty JSON array")
        allowed_categories = load_categories()
        seen_ids = set()
        collected = []
        for item in catalog:
            if not isinstance(item, dict):
                raise ValueError("each catalogue entry must be an object")
            validate_source(item, allowed_categories)
            if item["id"] in seen_ids:
                raise ValueError(f"duplicate source id {item['id']!r}")
            seen_ids.add(item["id"])
            if item.get("api_resource_id"):
                url, text = fetch_ogd_records(item)
            else:
                url, text = fetch_text(item)
            collected.append({
                "id": item["id"],
                "category": item["category"],
                "title": item["title"],
                "publisher": item["publisher"],
                "url": url,
                "license": item["license"],
                "license_url": item["license_url"],
                "accessed_on": date.today().isoformat(),
                "text": text,
            })
    except (OSError, json.JSONDecodeError, URLError, ValueError, KeyError) as exc:
        print(f"Source collection failed: {exc}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(collected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Collected {len(collected)} approved source(s) into {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())