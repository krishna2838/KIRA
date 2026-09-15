"""Simple eval runner. Loads YAML cases and runs them against the live stack."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import yaml

from kira.brain.intent import IntentClassifier
from kira.brain.ollama_client import OllamaClient
from kira.brain.router import ModelRouter
from kira.config import get_config


async def run_intent_cases(cases_file: Path) -> tuple[int, int]:
    data = yaml.safe_load(cases_file.read_text())
    config = get_config()
    ollama = OllamaClient()
    clf = IntentClassifier(ollama, config.models.fast.model)

    passed = 0
    total = len(data["cases"])
    for case in data["cases"]:
        got = await clf.classify(case["input"])
        ok = got == case["expected"]
        passed += int(ok)
        mark = "✓" if ok else "✗"
        print(f"  {mark} {case['input']!r} -> {got} (expected {case['expected']})")
    await ollama.close()
    return passed, total


async def run_routing_cases(cases_file: Path) -> tuple[int, int]:
    data = yaml.safe_load(cases_file.read_text())
    config = get_config()
    ollama = OllamaClient()
    # Gemini not needed just for the routing decision
    router = ModelRouter(config, ollama, None)

    passed = 0
    total = len(data["cases"])
    for case in data["cases"]:
        tier = await router.route(case["input"], {})
        ok = tier.value == case["expected_tier"]
        passed += int(ok)
        mark = "✓" if ok else "✗"
        print(f"  {mark} {case['input']!r} -> {tier.value} (expected {case['expected_tier']})")
    await ollama.close()
    return passed, total


DISPATCH = {
    "intent_classification": run_intent_cases,
    "model_routing": run_routing_cases,
}


async def run_file(path: Path) -> None:
    data = yaml.safe_load(path.read_text())
    name = data.get("name", path.stem)
    print(f"\n== {name} ==")
    fn = DISPATCH.get(name)
    if not fn:
        print(f"  (no runner for {name}; skipping)")
        return
    passed, total = await fn(path)
    print(f"  {passed}/{total} passed")


async def main() -> None:
    here = Path(__file__).parent
    if len(sys.argv) > 1:
        files = [Path(a) for a in sys.argv[1:]]
    else:
        files = sorted((here / "cases").glob("*.yaml"))
    for f in files:
        await run_file(f)


if __name__ == "__main__":
    asyncio.run(main())
