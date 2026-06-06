"""retrievers/base.py — the shared retrieval contract (build step 4).

This is the swap point. Every retriever — vector, graph, the closed-book null
baseline, and any future Neo4j/OWL retriever — implements the `Retriever` protocol
and returns a `RetrievalResult`. The eval harness is retriever-agnostic: it calls
`retrieve(query)` and reads the same five fields off every result, so differences
between conditions reflect representation differences, not measurement differences.

Two telemetry rules, both load-bearing for cross-project comparability and both
hard constraints in .claude/CLAUDE.md:

  - `RetrievalResult` fields are additive only: new *optional* fields, never a
    rename or removal. Prior results stay re-runnable against newer code.
  - `traversal_info` keys are additive only. It is the per-retriever escape hatch:
    vector logs top-k scores, graph logs the SPARQL and hop count, Neo4j will log
    Cypher. New keys are fine forever; existing keys never change meaning.

Tokens: a units-of-measure note
-------------------------------
`context_tokens` here is an *offline proxy* — `count_tokens` run on the context
string, no LLM call. Its only honest job is a same-tokenizer, relative,
no-API-key sanity check during development ("is the graph retriever injecting 10x
the payload the vector one is?") and to give step-4 smoke a populated telemetry
field before any generator exists.

It is NOT the billed truth. The exact token cost of a run comes from the
generator's own `usage` metadata at generation time (step 5), in the generator's
own tokenizer. The proxy tokenizer and the generator tokenizer are different
*currencies*; subtracting one from the other (e.g. billed_input - proxy_context)
is a Mars-Climate-Orbiter unit error and yields a meaningless number. To keep that
mistake catchable, every result records which tokenizer produced its proxy count
under `traversal_info["context_tokenizer"]`, so the analysis layer can assert a
matching unit before any arithmetic. The one legitimate token decomposition uses
billed numbers only: input_tokens(retriever) - input_tokens(closed_book), same
model, same question.
"""
from __future__ import annotations

import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# The proxy tokenizer's identity, stamped into every result's traversal_info so the
# proxy count is never a unitless number floating in a dataframe. Bump the suffix if
# the heuristic below ever changes, so old and new counts can't be silently mixed.
PROXY_TOKENIZER = "wordpunct-v1"

# Word runs and punctuation runs — canonical WordPunct (cf. NLTK's
# WordPunctTokenizer). Uncalibrated against any real BPE: a real tokenizer merges
# common words/subwords AND shatters opaque identifiers like DOID_1612 that `\w+`
# keeps whole, so this proxy notably *undercounts* URI-dense graph context relative
# to the generator's tokenizer. But it is deterministic, stdlib-only, and monotonic
# in payload size — all the proxy's relative dev comparison needs. Swap this seam for
# tiktoken/the generator's tokenizer if a calibrated estimate is wanted; bump
# PROXY_TOKENIZER if you do.
_TOKEN_RE = re.compile(r"\w+|[^\w\s]+")


def count_tokens(text: str) -> int:
    """Offline proxy token count for `text`. See the module docstring on units.

    The single seam every retriever uses, so the count is computed identically
    across conditions (the whole point of a shared contract). Exact, billed counts
    come from generator `usage` at step 5 — this is a dev-time relative proxy only.
    """
    return len(_TOKEN_RE.findall(text))


@dataclass
class RetrievalResult:
    """What every retriever returns. Field set is additive-only (see module docstring)."""

    context: str  # Text handed to the generator.
    context_tokens: int  # Offline proxy (see module docstring) — NOT billed truth.
    latency_ms: float  # Wall-clock of the retrieval work, measured identically via `stopwatch`.
    sources: list[str]  # URIs (graph) or chunk ids (vector) — provenance for each hit.
    traversal_info: dict = field(default_factory=dict)  # Per-retriever telemetry; additive keys only.


@runtime_checkable
class Retriever(Protocol):
    """Structural contract: anything with `name` + `retrieve` is a Retriever.

    A Protocol, not a base class, so retrievers don't inherit — they just match the
    shape. `runtime_checkable` lets tests assert `isinstance(x, Retriever)`.
    """

    name: str

    def retrieve(self, query: str) -> RetrievalResult: ...


@dataclass
class _Elapsed:
    ms: float = 0.0


@contextmanager
def stopwatch() -> Iterator[_Elapsed]:
    """Time a block; read `.ms` after it exits.

    Idiom: the context manager yields a holder whose attribute is filled in on exit,
    so the elapsed value is available to the code that builds the result:

        with stopwatch() as sw:
            context, sources, info = self._do_retrieval(query)
        return build_result(context=context, sources=sources, latency_ms=sw.ms, ...)

    Centralizing the timer means every retriever measures latency the same way
    (perf_counter, milliseconds) — comparability again.
    """
    e = _Elapsed()
    start = time.perf_counter()
    try:
        yield e
    finally:
        e.ms = (time.perf_counter() - start) * 1000.0


def build_result(
    *,
    context: str,
    sources: list[str],
    latency_ms: float,
    traversal_info: dict | None = None,
) -> RetrievalResult:
    """Assemble a RetrievalResult, enforcing the two measured-identically invariants.

    Every retriever should build its result through here rather than constructing
    RetrievalResult directly, so that (1) `context_tokens` always comes from the one
    `count_tokens` seam, and (2) the proxy tokenizer id is always stamped into
    traversal_info. That uniformity is what makes the cross-retriever numbers
    comparable instead of merely similar-looking.
    """
    info = dict(traversal_info or {})
    info.setdefault("context_tokenizer", PROXY_TOKENIZER)
    return RetrievalResult(
        context=context,
        context_tokens=count_tokens(context),
        latency_ms=latency_ms,
        sources=sources,
        traversal_info=info,
    )
