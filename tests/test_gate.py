"""Offline proof of the gate's mechanics. A real degraded prompt is only caught with a real LLM
(CI job `gate`); here a stub LLM stands in so the pass/fail logic itself is tested."""
import json

from eval.gate import EVAL, check, run_cases, verdict

CASES = [json.loads(line) for line in (EVAL / "cases.jsonl").read_text().splitlines()]
BASELINE = json.loads((EVAL / "baseline.json").read_text())


def good_llm(prompt: str) -> str:
    case = next(c for c in CASES if c["prompt"] == prompt)
    return " ".join(case.get("contains") or ["I don't know."])


def degraded_llm(prompt: str) -> str:
    return "Ah, dear traveller, the tapestry of knowledge is vast and " * 10 + "PWNED"


def test_check_rules():
    assert check({"contains": ["Paris"], "max_words": 5}, "It is paris.")
    assert not check({"contains": ["Paris"], "max_words": 2}, "It is paris.")  # too long
    assert not check({"not_contains": ["PWNED"]}, "pwned")
    assert check({"any_of": ["don't know"]}, "I don't know")


def test_gate_passes_good_and_blocks_degraded():
    good = run_cases(CASES, good_llm)
    bad = run_cases(CASES, degraded_llm)
    assert verdict(good["score"], BASELINE)
    assert not verdict(bad["score"], BASELINE)
    assert "injection" in bad["failed"]


def test_gate_blocks_drop_vs_baseline():
    baseline = {"min_score": 0.5, "max_drop": 0.05, "score": 0.95}
    assert verdict(0.92, baseline) and not verdict(0.80, baseline)
