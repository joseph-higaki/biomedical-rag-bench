"""eval/judge/deterministic.py — the nine-of-ten deterministic judges (build step 5).

Five scoring strategies cover nine of the ten question types; only `semantic`
(type 10) needs an LLM (semantic.py, a later increment). Each judge here is
pure-stdlib and hermetic — no network, no API key — so the headline accuracy on
factual/structural questions never depends on a model's judgment or on spend.

The hard part of every one of these is *extraction*: the generator returns free
text, the ground truth is a number / boolean / label set derived from the graph, and
the judge has to bridge them. The guiding rule is to be lenient about *form* (phrasing,
list style, surrounding prose) and strict about *content* (is the right number / the
right set / the right polarity actually asserted?). Where extraction can't be done
deterministically without guessing — chiefly precision on prose set answers and true
hallucination detection — the judge reports what it *can* verify and flags the rest,
matching eval/README's "escalate to LLM entity linking if too brittle" path rather
than silently over-claiming a verdict.
"""
from __future__ import annotations

import re

from eval.judge.base import Judge, JudgeResult, normalize

# Numbers the model might write as "1,184" or "184"; commas stripped before int().
_NUMBER = re.compile(r"\d[\d,]*")
# Typographic apostrophes models emit ("I don't", U+2019/U+2018/U+02BC) folded to ASCII
# so the contraction cues below match regardless of the answer's typography.
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'"})
# Explicit negation/empty-answer cues for the unanswerable / boolean judges. A refusal
# almost always arrives as a contraction ("I don't have …", "there isn't …"), so the
# contraction family carries as much weight here as the spelled-out forms; "not" already
# covers the "does not"/"is not" spelled variants.
_NEGATION = re.compile(
    r"\b(no|none|not|cannot|never|unanswerable|unknown|zero|empty|nothing|"
    r"no such|not aware|no known|"
    r"can't|don't|doesn't|didn't|isn't|aren't|wasn't|weren't|"
    r"won't|wouldn't|couldn't|shouldn't|haven't|hasn't|hadn't)\b"
)


def _has_negation(text: str) -> bool:
    """True if `text` carries an explicit negation/refusal cue, apostrophe-insensitive."""
    return bool(_NEGATION.search(text.lower().translate(_APOSTROPHES)))


def _tokens(text: str) -> list[str]:
    return normalize(text).split()


def _contains_phrase(haystack: list[str], phrase: list[str]) -> bool:
    """True if the token list `phrase` appears as a contiguous run in `haystack`.

    Token-level (not substring) so "11" does not match inside "111" and a multi-word
    label like "non small cell" matches only as the whole phrase, not its parts.
    """
    n = len(phrase)
    if not n or n > len(haystack):
        return False
    return any(haystack[i : i + n] == phrase for i in range(len(haystack) - n + 1))


# --- type 01: single attribute value ---------------------------------------
class StringMatchJudge:
    """`string_match` — is the single ground-truth value asserted in the answer?

    Ground truth is one string (e.g. the chromosome "11"). Correct iff its normalized
    token run appears anywhere in the normalized answer — lenient about surrounding
    prose ("It's on chromosome 11."), strict about the value itself.
    """

    scoring = "string_match"
    # Per-strategy version (not a shared "deterministic-vN"): each judge bumps independently
    # so a fix to one judge's logic never re-labels results the others produced unchanged.
    version = "v1"

    def score(self, predicted, ground_truth, *, answer_var=None, question=None) -> JudgeResult:
        gt = str(ground_truth)
        found = _contains_phrase(_tokens(predicted), _tokens(gt))
        return JudgeResult(
            scoring=self.scoring,
            score=1.0 if found else 0.0,
            passed=found,
            verdict=f"value {gt!r} {'found' if found else 'not found'} in answer",
            details={"expected": gt},
        )


# --- types 02, 03, 04, 06, 07: label sets -----------------------------------
def _looks_like_list(text: str) -> bool:
    """List-shaped answer: ≥2 non-empty lines, or bullet/numbered markers.

    Only then is precision (over-claiming) measurable deterministically: we can split
    the answer into discrete claimed items. Comma-in-prose ("A, B and C") is *not*
    treated as a list — splitting prose on commas shreds multi-word labels and
    manufactures false members — so prose answers are scored recall-only.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 2:
        return True
    return bool(re.search(r"(^|\n)\s*([-*•]|\d+[.)])\s+", text))


def _is_scaffolding(line: str) -> bool:
    """A non-entity scaffolding line — a markdown header or a bare 'Section:' label —
    that must not be counted as a claimed set member. Filtering these is *extraction*,
    not leniency: a title like '# Genes Expressed in Semicircular Canal' or a lead-in
    like 'The genes are:' is not an entity the model claimed, and counting it as one
    wrongly inflates the 'extra' set and depresses precision (FINDINGS caveat #2). The
    prose-sentence preamble case ('To answer this, I need to…') is left to the system
    prompt's format steering — it can't be told from a real label deterministically."""
    s = line.strip()
    return s.startswith("#") or s.endswith(":")


def _split_items(text: str) -> list[str]:
    """Split a list-shaped answer into claimed items (strip bullets/numbering, drop
    scaffolding lines that are not entities)."""
    items: list[str] = []
    for ln in text.splitlines():
        ln = re.sub(r"^\s*([-*•]|\d+[.)])\s+", "", ln).strip()
        if not ln or _is_scaffolding(ln):
            continue
        # A single line may still pack several comma/semicolon-separated items.
        items.extend(p.strip() for p in re.split(r"[;,]", ln) if p.strip())
    return items


class SetMatchJudge:
    """`set_match` — compare the answer's entity set to the ground-truth set.

    Recall is always measurable: each ground-truth label is searched as a token run in
    the whole answer (form-independent). Precision (did the model name things that
    aren't in the answer set — i.e. over-claim?) is only measurable when the answer is
    list-shaped enough to split into discrete claims; on prose we report recall only and
    flag `basis="recall_only"`, because deterministically separating real labels from
    surrounding words isn't reliable (eval/README's escalation point). When precision is
    available, `score` is F1 and `passed` requires an exact set; on prose, `score` is
    recall and `passed` requires full recall.
    """

    scoring = "set_match"
    version = "v1"

    def score(self, predicted, ground_truth, *, answer_var=None, question=None) -> JudgeResult:
        gt = [str(x) for x in (ground_truth or [])]
        gt_norm = [normalize(x) for x in gt]
        toks = _tokens(predicted)

        found = [g for g, gn in zip(gt, gt_norm) if _contains_phrase(toks, gn.split())]
        recall = len(found) / len(gt) if gt else 1.0
        missing = [g for g in gt if g not in found]
        details: dict = {"expected_count": len(gt), "found_count": len(found),
                         "missing": missing}

        if _looks_like_list(predicted):
            items = _split_items(predicted)
            gt_set = set(gt_norm)
            # An item counts as on-target if it equals or contains a ground-truth label.
            matched = [it for it in items
                       if normalize(it) in gt_set
                       or any(_contains_phrase(_tokens(it), g.split()) for g in gt_norm)]
            precision = len(matched) / len(items) if items else 1.0
            extra = [it for it in items if it not in matched]
            f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
            passed = recall == 1.0 and not extra
            details |= {"precision": round(precision, 4), "recall": round(recall, 4),
                        "f1": round(f1, 4), "extra": extra, "basis": "set"}
            score = f1
            verdict = f"set F1={f1:.2f} (recall {len(found)}/{len(gt)}, {len(extra)} extra)"
        else:
            passed = recall == 1.0
            details |= {"precision": None, "recall": round(recall, 4), "basis": "recall_only"}
            score = recall
            verdict = f"prose answer: recall {len(found)}/{len(gt)} (precision not measurable)"

        return JudgeResult(scoring=self.scoring, score=score, passed=passed,
                           verdict=verdict, details=details)


# --- type 05: count ---------------------------------------------------------
class NumericalJudge:
    """`numerical` — does the ground-truth count appear among the answer's numbers?

    Lenient: extracts every integer in the answer and passes iff the expected value is
    one of them, so "Galantamine causes 184 side effects" passes whether or not other
    numbers (years, dose) are mentioned. Coincidental matches are possible but unlikely
    for these counts; the first extracted number is recorded for transparency.
    """

    scoring = "numerical"
    version = "v1"

    def score(self, predicted, ground_truth, *, answer_var=None, question=None) -> JudgeResult:
        expected = int(str(ground_truth).replace(",", ""))
        nums = [int(m.group().replace(",", "")) for m in _NUMBER.finditer(predicted)]
        passed = expected in nums
        return JudgeResult(
            scoring=self.scoring,
            score=1.0 if passed else 0.0,
            passed=passed,
            verdict=f"expected {expected}; {'matched' if passed else 'not among'} {nums or 'no numbers'}",
            details={"expected": expected, "extracted": nums,
                     "first": nums[0] if nums else None},
        )


# --- type 08: negative / unanswerable ---------------------------------------
class BinaryJudge:
    """`binary` — for unanswerables (empty ground truth): refused, or hallucinated?

    The correct answer is "there are none / this can't be answered". Deterministically
    we can verify an explicit refusal/empty assertion (a negation cue). We cannot, here,
    prove the *absence* of hallucinated entities without entity linking, so this judge
    scores refusal-detection: passed iff the answer asserts emptiness/negation. Real
    hallucination detection (did it name fake entities?) is the eval/README LLM-linking
    escalation. Guarded to the designed empty-ground-truth case.
    """

    scoring = "binary"
    version = "v1"

    def score(self, predicted, ground_truth, *, answer_var=None, question=None) -> JudgeResult:
        is_empty_gt = not ground_truth
        refused = _has_negation(predicted)
        if is_empty_gt:
            passed = refused
            verdict = ("correctly refused / asserted none" if refused
                       else "did not refuse — likely hallucinated an answer")
        else:  # not the designed shape, but score it honestly rather than crash
            passed = not refused
            verdict = "answer expected but refused" if refused else "answered (non-empty ground truth)"
        return JudgeResult(
            scoring=self.scoring,
            score=1.0 if passed else 0.0,
            passed=passed,
            verdict=verdict,
            details={"empty_ground_truth": is_empty_gt, "refusal_detected": refused},
        )


# --- type 09: path existence ------------------------------------------------
class BooleanJudge:
    """`boolean` — does the answer's yes/no polarity match the ground truth?

    Ground truth is "true"/"false". Detects an affirmative (yes/true/"there is a path")
    or a negative (no/false/"does not exist") cue. Ambiguous answers (both or neither
    cue) fail with an `ambiguous` flag rather than guessing.
    """

    scoring = "boolean"
    version = "v1"

    def score(self, predicted, ground_truth, *, answer_var=None, question=None) -> JudgeResult:
        expected = str(ground_truth).strip().lower() in ("true", "yes", "1")
        toks = set(_tokens(predicted))
        says_true = bool({"yes", "true"} & toks) or "there is a path" in predicted.lower()
        says_false = bool({"no", "false"} & toks) or _has_negation(predicted)
        ambiguous = says_true == says_false  # both or neither
        predicted_bool = says_true and not says_false
        passed = (not ambiguous) and (predicted_bool == expected)
        return JudgeResult(
            scoring=self.scoring,
            score=1.0 if passed else 0.0,
            passed=passed,
            verdict=("ambiguous polarity" if ambiguous
                     else f"answer {'true' if predicted_bool else 'false'} vs expected {expected}"),
            details={"expected": expected, "says_true": says_true,
                     "says_false": says_false, "ambiguous": ambiguous},
        )


# The deterministic registry: `scoring` value -> judge instance. The harness looks a
# judge up by the question's `scoring` field; the `semantic` strategy (type 10) joins
# from semantic.py (the LLM judge). Built from each judge's own `scoring`
# attribute so the key and the verdict's reported strategy cannot drift.
_JUDGES: list[Judge] = [
    StringMatchJudge(), SetMatchJudge(), NumericalJudge(), BinaryJudge(), BooleanJudge(),
]
DETERMINISTIC_JUDGES: dict[str, Judge] = {j.scoring: j for j in _JUDGES}
