# Indian GK Database (English + Hindi)

A static, versioned MCQ database starter for a Flutter Android GK app. Source records are stored in `data/source/`; GitHub Actions validates, tests, builds, and publishes release artifacts.

## Important status

This repository is a **pipeline starter**, not a finished 100,000-question dataset. It contains two example questions (one English and one Hindi) and empty category files. Do not claim 100,000 questions until the full dataset has been authored/imported, reviewed, and the CI count check has been configured.

## Question format

Each record includes:
- Stable `id`
- `category`, `difficulty`, `type`, `language`
- `question`, `options`, `answer_index`, `explanation`
- `tags`
- `source` metadata (`title`, `url`, `publisher`, `accessed_on`, `license`)
- `updated_at`

English and Hindi are separate records with distinct IDs. If they are translations of the same fact, add a shared `translation_group_id` field only after updating the JSON Schema and validator.

## Local development

Requires Python 3.12+.

```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/validate_database.py
python scripts/verify_sources.py
pytest -q
python scripts/build_database.py
```

Generated output appears in `dist/`: full database, English-only and Hindi-only JSON, per-category JSON, gzip JSON, and `manifest.json` with SHA-256 checksums.

## GitHub setup

1. Create a public repository named `indian-gk-database`.
2. Commit and push these files to `main`.
3. In Settings → Actions → General, allow GitHub Actions and allow the workflow's repository permissions as required.
4. The `Database CI` workflow runs on pushes and pull requests.
5. `Publish database` creates a GitHub Release for changes merged to `main`, using an immutable commit-derived tag such as `build-<sha>`. You can manually run it with a semantic version such as `v1.0.0`.
6. For app distribution, use versioned GitHub Release asset URLs. Avoid relying on the mutable `main` branch URL as a production version pin.

## Enforce 100,000 records

After the dataset is complete, set the `EXPECTED_QUESTION_COUNT` environment variable to `100000` in the validation step or change the script default. If English and Hindi are each represented as separate MCQs, decide whether “100,000 questions” means 100,000 records total or 100,000 concepts with 200,000 language records. This starter counts records.

Example strict check in CI:

```yaml
- name: Validate exact production count
  env:
    EXPECTED_QUESTION_COUNT: "100000"
  run: python scripts/validate_database.py
```

## Data source policy

Prefer facts from official and clearly licensed sources. Record the exact source and license/terms per record. Examples to investigate:
- NCERT / ePathshala educational material: https://epathshala.nic.in/
- Legislative Department, Constitution of India: https://www.legislative.gov.in/constitution-of-indiaConstitution
- Open Government Data Platform India: https://www.data.gov.in/ and https://www.data.gov.in/Godl

A source being publicly accessible does **not** automatically mean its question wording, images, or compilations can be republished. Review the license attached to each dataset and any third-party content. Keep original question wording and explanations where permission is uncertain.

## Flutter consumption

For production, use a versioned Release asset or a stable CDN URL, download to app storage, verify SHA-256 from the manifest, then parse JSON. For large datasets, prefer `questions.en.json` / `questions.hi.json` or category files instead of downloading all records. Add HTTP timeout/retry, cache versioning, and a last-known-good offline fallback. Static GitHub hosting has no write API, authentication system, or per-user progress storage.

## Review limits

The scripts validate shape, identifiers, answer index bounds, source metadata, and build outputs. They cannot establish that every fact is true, that a translation is accurate, or that a source license allows redistribution. Human/editorial review is required before release.
