# Self-Healing CI Demo

This portfolio experiment demonstrates AI-assisted Python test-failure diagnosis with a local Llama model through [Ollama](https://ollama.com/). It uses per-test coverage contexts to identify source files executed by each failing test, then provides the failed test, relevant source code, and pytest output to the model. It does not need a paid model API; GitHub Actions runner limits still apply.

## What it does

1. GitHub Actions runs tests and records pytest's JSON report plus per-test coverage contexts.
2. If tests fail, a context builder maps each failed test to its test file and Python source files executed by that test. If coverage mapping is unavailable, it falls back to local imports found in the test file.
3. Ollama runs `llama3.2:1b` locally on the runner and receives the failure log plus bounded source context.
4. A concise diagnosis appears in the job log and run summary; the full response and selected source context are uploaded as artifacts.
5. The regular workflow ends red when the baseline tests fail. It does not modify code or open PRs.

## Optional draft repair PR

A separate workflow, **Self-healing CI - draft repair PR**, can generate a narrowly scoped patch and open a draft PR after the patched tests pass.

1. Open **Actions** and run **Self-healing CI - draft repair PR** manually.
2. Select the branch to test. Enable `create_draft_pr` only when you want to attempt a repair proposal; it defaults to false.
3. The workflow runs the baseline tests, diagnoses failures, and builds per-test source context.
4. If enabled, Llama may propose a patch. A validator only allows edits to existing application `.py` files selected by the context builder. It refuses changes to tests, workflows, scripts, new files, renames, and paths outside the repository.
5. The workflow applies the patch in its temporary checkout and reruns pytest. It opens a **draft** PR only if the patch applies, passes validation, and all tests pass.
6. Review the diff and diagnosis yourself. The workflow does not merge changes.

The baseline test failure remains recorded as a failed workflow even when a repair PR is opened. A passing test run is not proof of correctness. Require normal human review and branch protection before merging; configure required approvals in the repository's rulesets/branch protection settings.

The PR workflow is manual-only and has write permissions to create its branch and PR. Do not add `pull_request` triggers to that workflow. The normal diagnosis workflow remains separate.

## Run the demo

1. Open **Actions** and select **Self-healing CI**.
2. Select **Run workflow** on `main`.
3. Open the run. The intentional double-tax test should fail; inspect the diagnosis step and download the `ai-diagnosis` artifact.

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

- Only repository Python files associated with failed tests are included, with size limits. Review artifacts before sharing them; source code can contain sensitive material.
- Coverage narrows candidate files but cannot prove causality. Import-based fallback is approximate.
- The model's diagnosis and patch can be wrong; confidence is a model-generated label, not a calibrated probability.
- Patch generation is opt-in and limited to selected application Python files. Tests must pass before a draft PR is created; all changes still require human review.
- The workflow uses a GitHub-hosted runner and downloads Ollama/model on runs that need diagnosis.
