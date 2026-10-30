"""Prompt/model regression gate: run eval/cases.jsonl through the service in-process (real upstream),
score with deterministic rules, exit 1 if quality is below the baseline. CI runs this on every push.

    python -m eval.gate [--prompt prompts/system_degraded.txt]
"""
import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

EVAL = Path(__file__).parent


def check(case: dict, text: str) -> bool:
    t = text.lower()
    return (
        all(s.lower() in t for s in case.get("contains", []))
        and (not case.get("any_of") or any(s.lower() in t for s in case["any_of"]))
        and not any(s.lower() in t for s in case.get("not_contains", []))
        and len(text.split()) <= case.get("max_words", 80)
    )


def run_cases(cases: list[dict], ask) -> dict:
    passed = {c["id"]: check(c, ask(c["prompt"])) for c in cases}
    return {"score": sum(passed.values()) / len(passed),
            "failed": [k for k, ok in passed.items() if not ok]}


def verdict(score: float, baseline: dict) -> bool:
    if score < baseline["min_score"]:
        return False
    return baseline.get("score") is None or score >= baseline["score"] - baseline["max_drop"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", help="system prompt file (default: SYSTEM_PROMPT_FILE or v1)")
    args = ap.parse_args()
    if args.prompt:
        os.environ["SYSTEM_PROMPT_FILE"] = args.prompt  # must be set before serving.config imports

    from fastapi.testclient import TestClient

    from serving import config as cfg
    from serving.app import create_app

    cases = [json.loads(line) for line in (EVAL / "cases.jsonl").read_text().splitlines()]
    baseline = json.loads((EVAL / "baseline.json").read_text())

    with TestClient(create_app()) as c:
        def ask(prompt: str) -> str:
            r = c.post("/v1/chat/completions",
                       json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 120})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]

        res = run_cases(cases, ask)

    ok = verdict(res["score"], baseline)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = {"timestamp": ts, "model": cfg.MODEL, "system_prompt": os.getenv(
        "SYSTEM_PROMPT_FILE", "prompts/system_v1.txt"), **res, "baseline": baseline, "passed": ok}
    (EVAL / "results").mkdir(exist_ok=True)
    (EVAL / "results" / f"gate_{ts}.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
