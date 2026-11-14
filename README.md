# Self-Healing CI Demo

This portfolio project demonstrates AI-assisted Python test-failure diagnosis and optional repair proposals using local models through [Ollama](https://ollama.com/). It uses pytest's JSON report and per-test coverage context to connect failures to relevant source files.

## Branch strategy

- **`main` is the healthy baseline.** Keep its application code and tests passing. The workflow and model integration live here; do not commit intentional breakages to `main`.
- **`test/self-healing-failure` is the sandbox/demo branch.** It contains deliberate test failures for exercising diagnosis and repair. Run the workflows against this branch when testing self-healing behavior. Do not merge the sandbox branch wholesale into `main`, because that can bring the intentionally broken application code and tests with it.
- To promote workflow improvements, make a clean branch from `main` and cherry-pick or reapply only the workflow, scripts, and documentation changes. Leave intentional failure fixtures behind. Open a PR from that clean branch to `main`, confirm its tests pass, then merge through normal review.

## What the diagnosis workflow does

1. GitHub Actions runs tests and records pytest's JSON report plus per-test coverage contexts.
2. If tests fail, a context builder maps each failed test to its test file and Python source files executed by that test. If coverage mapping is unavailable, it falls back to local imports found in the test file.
3. Ollama runs the lightweight `llama3.2:1b` model for diagnosis, using the failure log and bounded source context.
4. A diagnosis appears in the job log and run summary; failure context and diagnosis artifacts are uploaded for review.
5. The regular diagnosis workflow does not modify code or open PRs. A failing baseline run remains failed so the regression is visible.

## Optional draft repair PR

The separate **Self-healing CI - draft repair PR** workflow can generate a constrained repair and open a draft PR when the proposed changes pass the full test suite.

1. Open **Actions** and run **Self-healing CI - draft repair PR** manually.
2. Select the branch to test. Use `test/self-healing-failure` to exercise the deliberate regression; use `main` for the passing baseline.
3. Enable `create_draft_pr` only when you want to attempt a repair proposal.
4. The workflow downloads and uses two models: `llama3.2:1b` (`DIAGNOSIS_MODEL`) for failure diagnosis and `qwen2.5-coder:7b` (`PATCH_MODEL`) for code repair. The coder model is larger because generating code edits benefits from a stronger model.
5. The patch validator restricts edits to existing application Python files selected by the context builder. It refuses changes to tests, workflow files, scripts, and configuration.
6. The workflow tests the proposal and creates a **draft** PR only when the patch is accepted and the full test suite passes. Human review is required; the workflow never merges automatically.

The first run downloads both models (roughly 1.3 GB for the 7B coder model, plus the diagnosis model) and can take several minutes on a CPU-only GitHub-hosted runner. No Ollama API key or repository secret is required.

## Run the demo safely

1. Keep `main` passing and use it as the source for production changes.
2. Select `test/self-healing-failure` in the manual workflow to run the intentional failing-test scenario.
3. Review the diagnosis and patch artifacts. If a repair PR is created, inspect it; do not merge without normal code review and passing CI.
4. When promoting improvements to `main`, use a clean PR containing only the intended workflow, scripts, or documentation updates. Do not merge the sandbox branch wholesale.

## Run tests locally

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q --cov=. --cov-context=test --cov-report= --json-report --json-report-file=pytest-report.json
python scripts/build_failure_context.py
```

To run diagnosis locally with Ollama installed and running:

```bash
ollama pull llama3.2:1b
DIAGNOSIS_MODEL=llama3.2:1b python scripts/diagnose_failure.py
```

For local patch generation, also pull the coder model and set `PATCH_MODEL=qwen2.5-coder:7b`.

## Safety and limitations

- Only repository Python files associated with failed tests are included, with size limits. Review artifacts before sharing them; source code can contain sensitive material.
- Coverage narrows candidate files but cannot prove causality. Import-based fallback is approximate.
- Model diagnoses and patches can be wrong. Confidence labels are model-generated, not calibrated probabilities.
- Patch generation is opt-in and limited to selected application Python files. A passing test suite does not prove correctness; all changes still require human review.
- The workflow uses a GitHub-hosted runner and downloads the Ollama models when tests fail.
