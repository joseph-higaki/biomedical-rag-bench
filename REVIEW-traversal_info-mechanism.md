# Review packet — `traversal_info.mechanism` universality

Self-contained record of an incoming change request from the analytics consumer
(`rag-bench-analytics`) and the producer-side review. Persisted at repo root so it can be
committed, pushed, and read offline. Originally a pure decision document; the accepted change
has since been applied — kept as the "why" record (see Status).

- **Producer:** biomedical-rag-bench (this repo)
- **Consumer:** rag-bench-analytics
- **Subject:** make `traversal_info.mechanism` present on all four retrievers
- **Status:** DECIDED + IMPLEMENTED 2026-06-26 — `retrievers/null.py` stamps
  `mechanism: "none"` (decision-table rows 1+2+4); rows 3 & 5 rejected, rows 6 & 7 deferred.
  Regression-guarded by `tests/test_null.py`.

---

# Part 1 — The change request (verbatim, as received)

> # Change request → biomedical-rag-bench: make `traversal_info.mechanism` universal
>
> **From:** rag-bench-analytics (the analytics consumer)
> **Scope:** one telemetry inconsistency in the retriever layer. Everything else the
> consumer flagged was a *diagram* problem on the consumer side, not a producer bug —
> do **not** act on `sparse`/`dropped`/`graph`/`all`/`echo`; those are annotation terms
> in the consumer's ERD, not keys you emit.
>
> ## The finding
>
> `closed_book` is the only retriever that is telemetry-inconsistent with the other three:
>
> | retriever | file:line | emits `traversal_info.mechanism`? | emits `traversal_info.retriever`? |
> |---|---|:-:|:-:|
> | `vector` (dense) | `retrievers/vector.py:99` | ✅ `"dense"` | ❌ |
> | `graph_neighborhood` | `retrievers/graph.py:223,242` | ✅ `"neighborhood"` | ❌ |
> | `graph_sparqlgen` | `retrievers/sparqlgen.py:250` | ✅ `"sparqlgen"` | ❌ |
> | `closed_book` | `retrievers/null.py:34` | ❌ **(missing)** | ✅ `"none"` (only here) |
>
> `context_tokenizer` is correctly universal — `build_result` in `retrievers/base.py`
> stamps it on every result.
>
> Two consequences for the consumer:
>
> 1. **`traversal_info.mechanism` cannot be used as a universal discriminator.** Every
>    downstream query that wants "group by mechanism" has to special-case closed_book,
>    because the key simply isn't there.
> 2. **`traversal_info.retriever` is a lone key present in exactly one retriever**, and it
>    duplicates the top-level `retriever` field on the row. It's dead weight everywhere
>    else and confusing to read.
>
> ## Bug, or deliberate?
>
> Defensible either way, and that's the producer's call:
>
> - **"No retrieval ⇒ no mechanism"** is a coherent stance: closed_book doesn't retrieve,
>   so an empty-ish `traversal_info` is *meaningful*, not a gap.
> - **But** the additive-only contract (`retrievers/base.py`, `retrievers/README.md`) sells
>   `traversal_info` as the uniform per-retrieval telemetry seam. A discriminator that's
>   present for 3 of 4 retrievers undercuts that uniformity. Making it universal is cheap
>   and additive.
>
> We recommend making it universal. Pick the value you prefer; we'll conform.
>
> ## Recommended change (additive, contract-safe)
>
> In `retrievers/null.py:34`, add a `mechanism`:
>
> ```python
> # before
> traversal_info={"retriever": "none"},
> # after
> traversal_info={"mechanism": "none", "retriever": "none"},
> ```
>
> - Value `"none"` matches the `"none"` you already chose for `retriever`. `"closed_book"`
>   is the alternative if you'd rather mechanism map 1:1 to the retriever name. Either is
>   fine; just pick one and it becomes the contract.
> - This is **purely additive** — no existing key renamed or removed, so it honors the
>   additive-only contract.
> - Leave `traversal_info.retriever` as-is. Removing it *would* be a breaking change under
>   your own contract; it's harmless to keep as a closed_book-only legacy key. (If you ever
>   want it universal instead, stamp it in `build_result` for all retrievers — but that's
>   optional and not what this request asks for.)
>
> ## You do NOT need to re-run evals
>
> Re-running the 81 runs / 3,461 records costs real LLM spend for **zero analytical gain**.
> The discriminator for closed_book is trivially derivable, so:
>
> - **Producer:** ship the `null.py` one-liner so all *future* runs carry `mechanism`.
> - **Consumer:** backfills the discriminator in staging without touching your files —
>   `coalesce(traversal_info->>'mechanism', case when retriever = 'closed_book' then 'none' end)`.
>
> A re-run is only worth it if you specifically want the *historical files on disk* to be
> self-consistent (e.g. for republishing the dataset). For analysis it's unnecessary.
>
> ## Acceptance
>
> - New `closed_book` rows have `traversal_info.mechanism == "none"` (or your chosen value).
> - `traversal_info.mechanism` is now present on 100% of rows across all four retrievers.
> - No other `traversal_info` key changed.

---

# Part 2 — Producer-side review

## Verdict

Accept the one-liner — it's correct, minimal, and contract-safe. But two of the CR's
supporting claims are wrong or incomplete, and one of them changes how to think about the
fix. The CR found the symptom without noticing the mechanism that produced it.

## What checks out

Verified directly against the code:

- `vector.py:99` → `mechanism: "dense"`; `graph.py:223,242` → `"neighborhood"`;
  `sparqlgen.py:250` → `"sparqlgen"`. ✓
- `null.py:34` emits only `{"retriever": "none"}` — no `mechanism`. ✓
- A current closed_book row on disk (`eval/results/20260615T202958-closed_book-anthropic.jsonl`)
  carries `traversal_info = {"retriever": "none"}`, `context_tokens_proxy: 0`. The table is
  accurate for current-schema runs. ✓ (Older June-6 files predate the row schema and have no
  `traversal_info` key at all — irrelevant to this request.)

## What the CR gets wrong — and it matters

**"`context_tokenizer` is correctly universal — `build_result` stamps it on every result" is
false.** `build_result` stamps it, yes — but `null.py` *deliberately bypasses `build_result`*
(see `null.py:17` and its docstring). So closed_book rows carry **neither `mechanism` nor
`context_tokenizer`**. Both keys are missing, for one shared structural reason: `build_result`
is the stamping seam, and closed_book is the single retriever that doesn't pass through it.

This isn't pedantry — it breaks the CR's framing of "one telemetry inconsistency." There are
two missing keys, and the CR's own uniformity argument ("present for 3 of 4 undercuts the
discriminator") applies verbatim to `context_tokenizer`. The producer has to decide it too.

Resolve it **asymmetrically** — add `mechanism`, do **not** add `context_tokenizer`:
closed_book's context is `""`, so `context_tokens = 0` under any tokenizer. A tokenizer stamp
on a guaranteed-zero count is vacuous. `mechanism: "none"` is genuinely informative (labels the
row a no-retrieval baseline without special-casing the retriever name). The two keys *look*
symmetric (both absent) but aren't symmetric in value. The `null.py` docstring already makes
exactly this argument for the tokenizer, and it's right.

## Refinements to the recommendation

- **Value `"none"` is correct, but the CR's reason is weak.** It says "to match the `none` you
  chose for `retriever`." The real reason: `mechanism` is a *how-retrieval-happens* vocabulary
  (dense / neighborhood / sparqlgen), orthogonal to retriever *names* (vector / graph_* /
  closed_book). `"none"` is the honest mechanism descriptor for "no retrieval." The CR's
  alternative `"closed_book"` would conflate mechanism with retriever name and pollute the
  vocabulary — reject it, don't call it "equally fine."

- **`retriever: "none"` is mischaracterized.** The CR calls it a duplicate of the top-level
  `retriever` field. It isn't — top-level is `"closed_book"`, this is `"none"`. What it actually
  is: the *pre-`mechanism` naming for the same concept*. null.py was written with
  `retriever: "none"` as its telemetry marker before the `mechanism` convention solidified in
  the other three. So adding `mechanism: "none"` is a rename-by-addition. The CR's advice to
  leave the old key in place (removal = breaking under the additive contract) is right — keep
  it, vestigial but harmless.

## The deeper point the CR doesn't raise

The one-liner fixes closed_book but leaves `mechanism` a **copy-paste convention, not a
contract-enforced field**. The very inconsistency the CR found exists *because* `mechanism` is
hand-set in each retriever body instead of stamped by the shared seam the way `context_tokenizer`
is. The next retriever (P3's Neo4j/LPG) is just as free to forget it.

If `mechanism` is load-bearing as a universal discriminator — the CR's whole premise — the
structural fix is to promote it into the contract: a `mechanism` class attribute the harness
stamps, so it can't be forgotten. Wrinkle: closed_book bypasses `build_result`, so a
`build_result`-only stamp wouldn't reach it; you'd stamp at the harness/class-attribute level.
Given only 4 retrievers and one more coming, this is **optional, not required** — and CLAUDE.md's
"~100-line hand-rolled, no abstraction machinery" rule argues against over-building it. But it's
the honest answer to "how do we stop this recurring," which the CR doesn't ask.

## On "no re-run"

Agree. The `coalesce(traversal_info->>'mechanism', case when retriever='closed_book' then 'none'
end)` backfill is sound; on-disk historical inconsistency is analytically irrelevant. One thing
for the consumer to know: closed_book lacks `context_tokenizer` too, so any downstream code that
asserts `context_tokenizer` is present on every row will trip on closed_book — and that assertion
would itself be the bug (zero-token empty context has no meaningful tokenizer).

## If implemented

The edit is the CR's one-liner in `null.py:34`. Also touch the **null.py docstring** (lines
17–24): it reasons explicitly about what the hand-built constant emits and why it skips
`build_result`; add a clause that `mechanism` is now stamped as the discriminator even though
`context_tokenizer` still isn't. `retrievers/README.md`'s closed_book section (110–119) doesn't
enumerate its `traversal_info` keys, so it likely needs no change.

---

# Part 3 — Decision table (accept / do not accept)

Each row is an independent call. The minimal accepted change is rows 1, 4, and 7 together
(the one-liner plus its value choice plus the doc-sync). Everything else is reject or defer.

| # | Decision point | My call | Why |
|---|---|---|---|
| 1 | Add `mechanism: "none"` to `null.py:34` | **ACCEPT** | Additive, contract-safe, makes `mechanism` a true universal discriminator. The core of the request. |
| 2 | Use value `"none"` (not `"closed_book"`) | **ACCEPT `"none"` / REJECT `"closed_book"`** | `mechanism` is a how-retrieval-happens vocabulary, orthogonal to retriever names. `"closed_book"` conflates the two. |
| 3 | Also add `context_tokenizer` to closed_book | **DO NOT ACCEPT** | Vacuous: empty context → 0 tokens under any tokenizer. The null docstring's own reasoning. (CR implied this via its uniformity argument; reject it explicitly.) |
| 4 | Doc-sync: update `null.py` docstring clause | **ACCEPT (if #1 lands)** | The docstring reasons about exactly what the constant emits; it must stay truthful. |
| 5 | Remove the legacy `retriever: "none"` key | **DO NOT ACCEPT** | Removal is a breaking change under the additive-only contract. Keep it vestigial. |
| 6 | Re-run the 81 runs / 3,461 records to backfill on disk | **DO NOT (defer)** | Real LLM spend, zero analytical gain. Consumer backfills in staging. Only worth it if republishing the dataset as a self-consistent artifact. |
| 7 | Promote `mechanism` to a contract-enforced class attribute (root-cause fix) | **DEFER (optional)** | Prevents recurrence for P3's new retriever, but adds structure CLAUDE.md's no-abstraction rule pushes back on. Revisit when P3 lands, not now. |

## TL;DR

- **Smallest correct change:** rows 1 + 2 + 4 — add `mechanism: "none"` to `null.py` and fix
  the docstring. One file touched, fully additive, honors the contract.
- **Explicitly reject:** adding `context_tokenizer` to closed_book (#3) and removing
  `retriever: "none"` (#5).
- **Defer, don't forget:** the re-run (#6, only if republishing) and the structural root-cause
  fix (#7, revisit at P3).
