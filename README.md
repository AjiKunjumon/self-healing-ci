# Self-Healing CI Demo

This portfolio experiment demonstrates AI-assisted Python test-failure diagnosis with a local Llama model through [Ollama](https://ollama.com/). It uses per-test coverage contexts to identify source files executed by each failing test, then provides the failed test, relevant source code, and pytest output to the model. It does not need a paid model API; GitHub Actions runner limits still apply.

## What it does

1. GitHub Actions runs tests and records pytest's JSON report plus per-test coverage contexts.
2. If tests fail, a context builder maps each failed test to its test file and Python source files executed by that test. If coverage mapping is unavailable, it falls back to local imports found in the test file.
3. Ollama runs `llama3.2:1b` locally on the runner and receives the failure log plus bounded source context.
4. A concise diagnosis appears in the job log and run summary; the full response and selected source context are uploaded as artifacts.
5. The workflow ends red because the original tests failed. It does not edit code, create a PR, or merge anything.

Coverage is a search aid, not proof: an executed file or line is not necessarily the cause of a failure. Review the diagnosis and source changes yourself.

## Run the demo

1. Open **Actions** and select **Self-healing CI**.
2. Select **Run workflow** on `main`.
3. Open the run. The intentional double-tax test should fail; inspect the diagnosis step and download the `ai-diagnosis` artifact for the full JSON and selected source context.

No API key or repository secret is needed for Ollama. The first failing run downloads the model (about 1.3 GB) and may take a few minutes.

## Run tests locally

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q --cov=. --cov-context=test --cov-report= --json-report --json-report-file=pytest-report.json
python scripts/build_failure_context.py
```

Then, with Ollama installed and running, run:

```bash
ollama pull llama3.2:1b
python scripts/diagnose_failure.py
```

## Safety and limitations

- Only repository Python files associated with failed tests are included, with size limits. Review the artifact before sharing it; source code can contain sensitive material.
- Coverage narrows candidate files but cannot prove causality. Import-based fallback is approximate.
- The model's diagnosis can be wrong; confidence is a model-generated label, not a calibrated probability.
- The workflow does not modify repository files, create PRs, or auto-merge.
- The small model may provide incomplete diagnoses. Validate suggestions by reviewing code and rerunning tests.
