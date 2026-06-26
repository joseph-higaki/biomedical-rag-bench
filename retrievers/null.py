"""retrievers/null.py — the closed-book baseline (build step 4).

`NullRetriever` (name `closed_book`) returns empty context. Not a mechanism under test —
the baseline measuring how much retrieval adds at all (H7), since frontier models have
memorized most of Hetionet's famous entities.

Doubles as the per-question token baseline: its billed input_tokens is the non-retrieval
payload, so a retriever's true cost is input_tokens(retriever) − input_tokens(closed_book),
same tokenizer (see base.py on units).
"""
from __future__ import annotations

from retrievers.base import RetrievalResult


class NullRetriever:
    """Returns empty context. Deliberately bypasses base.build_result.

    The result is a hand-built constant matching the contract documented in the
    README exactly: there is nothing to tokenize (so no proxy count and no
    `context_tokenizer` stamp would be meaningful), and the retriever does no work
    (so its retrieval latency is zero by definition — it is a baseline, not a
    mechanism whose speed we measure).

    The build_result bypass means two stamps it would otherwise add are resolved here
    by hand, asymmetrically: `mechanism: "none"` is stamped (informative — labels the
    row a no-retrieval baseline, keeping `mechanism` a universal discriminator across
    all four retrievers), but `context_tokenizer` is deliberately omitted (vacuous —
    empty context is 0 tokens under any tokenizer). The legacy `retriever: "none"` key
    predates the `mechanism` convention and is kept vestigial: removal would break the
    additive-only contract.
    """

    name = "closed_book"

    def retrieve(self, query: str) -> RetrievalResult:
        return RetrievalResult(
            context="",
            context_tokens=0,
            latency_ms=0.0,
            sources=[],
            traversal_info={"mechanism": "none", "retriever": "none"},
        )
