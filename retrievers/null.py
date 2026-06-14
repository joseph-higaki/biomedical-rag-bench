"""retrievers/null.py — the closed-book baseline (build step 4).

`NullRetriever` (name `closed_book`) returns empty context. It is NOT a retrieval
mechanism under test; it is the *baseline* that measures how much retrieval
contributes to answer quality, independent of which retriever is used. Without it
the benchmark cannot distinguish "graph beats vector" from "both retrievers add
nothing the generator didn't already know from training data" — a real risk for
biomedical knowledge that frontier models have largely memorized (most of
Hetionet's famous entities). See the root README for the H7 retrieval-necessity
hypothesis this baseline exists to test.

It doubles as the per-question *token* baseline: because it injects no context, its
billed input_tokens is exactly the non-retrieval payload (system + question + framing)
for that question. A retriever's true injected cost is then
input_tokens(retriever) - input_tokens(closed_book), both in the generator's
tokenizer — the one unit-safe token decomposition (see base.py on units).
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
    """

    name = "closed_book"

    def retrieve(self, query: str) -> RetrievalResult:
        return RetrievalResult(
            context="",
            context_tokens=0,
            latency_ms=0.0,
            sources=[],
            traversal_info={"retriever": "none"},
        )
