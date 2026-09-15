# KIRA evals

Small YAML-defined test cases for the intent classifier, model router, and memory retrieval.

Run all:

```bash
python evals/run_evals.py
```

Run one:

```bash
python evals/run_evals.py evals/cases/intent_classification.yaml
```

Cases exercise the live Ollama fast model — Ollama must be running.
