# secrets/

**Purpose.** Per-user credentials live here: the GraphDB license and a `.env` of API keys.
**Nothing in here is committed except this README and `*.example` templates**
(see the repo `.gitignore`). The directory itself is tracked so the
`docker-compose.yml` bind-mount source exists on a fresh clone.

**Where it sits.** Cross-cutting setup; the license gates GraphDB writes (ingestion), the
`.env` gates every LLM role (generator, SPARQL writer, semantic judge) and the PubMed fetch.

| File | What | Committed? |
|---|---|---|
| `graphdb.license` | GraphDB Free license (see below) | no |
| `.env` | API keys / `GENERATOR_MODEL` | no |
| `.env.example` | template for `.env` | yes |
| `README.md` | this file | yes |

## API keys (`secrets/.env`)

Copy `.env.example` to `.env` and fill in. It is **not** auto-discovered:
`python-dotenv`'s `find_dotenv()` walks up the tree for a root `.env` and never
descends into subdirectories. App code loads it by explicit, file-anchored path:

```python
load_dotenv(Path(__file__).resolve().parents[N] / "secrets" / ".env")
```

Centralize that in one settings module so every entry point shares it.

## GraphDB license (required)

As of **GraphDB 11.0**, the Free edition is no longer distributed license-free:
the engine starts and answers reads, but **writes fail with `No license was set`**
until a license file is present. The Free license costs nothing but is
email-gated.

### Get it

1. Request GraphDB Free from the download page at <https://www.ontotext.com/products/graphdb/download/>
   (registration required). The license arrives by email as a `.license` file.
2. Save it here as exactly:

   ```
   secrets/graphdb.license
   ```

3. Recreate the container so it picks up the mount:

   ```bash
   make down && make up
   ```

`docker-compose.yml` mounts `./secrets` read-only at `/opt/graphdb/secrets` and
sets `-Dgraphdb.license.file=/opt/graphdb/secrets/graphdb.license`. Keeping the
license here (not under `graphdb-data/`) means `make clean-graphdb` can wipe the
triplestore without destroying the license.

### Reproducibility note

This is the one manual step `docker compose up` cannot satisfy on a fresh
machine — each developer fetches their own free license. Documented as a known
gotcha, consistent with the project's reproducibility goal.
