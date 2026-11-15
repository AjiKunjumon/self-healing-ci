# Self-Healing CI Demo

This portfolio experiment demonstrates GitHub Copilot cloud-agent-assisted Python test-failure diagnosis and repair proposals. GitHub Actions records pytest's JSON report and per-test coverage contexts, then invokes Copilot's Agent Tasks REST API to analyze failures and propose an application-only repair. No local model downloads or third-party model API keys are used.

## What it does

1. GitHub Actions runs tests and records pytest's JSON report plus per-test coverage contexts.
2. If tests fail, a context builder records every failure and maps tests to their test file and Python source files executed by that test. If coverage mapping is unavailable, it falls back to local imports found in the test file. Source snippets are size-limited and may be omitted when the shared budget is exhausted.
3. The workflow sends bounded failure logs and source context to a Copilot cloud-agent task. The agent commits a structured diagnosis report to its task branch; the workflow validates and saves it as `ai-diagnosis.json`.
4. The concise diagnosis appears in the job log and run summary; the full response and selected source context are uploaded as artifacts.
5. The regular workflow ends red when the baseline tests fail. It does not apply code changes or open PRs.

## Optional draft repair PR

A separate workflow, **Self-healing CI - draft repair PR**, can generate a narrowly scoped patch and open a draft PR after the patched tests pass.

1. Open **Actions** and run **Self-healing CI - draft repair PR** manually.
2. Select the branch to test. Enable `create_draft_pr` only when you want to attempt a repair proposal; it defaults to true.
3. The workflow runs the baseline tests, diagnoses failures, and builds per-test source context.
4. If enabled, a second Copilot cloud-agent task may propose a patch. The workflow rejects agent tasks that change files other than `app.py` and the temporary patch artifact. The patch itself must apply cleanly to the current checkout and may modify only the existing `app.py`.
5. The workflow reruns the complete test suite against the patch and again on the proposed PR tree based on `main`. It opens a **draft** PR containing only `app.py` if both runs pass; otherwise it stops and reports the failure.
6. Review the diff and diagnosis yourself. The workflow does not merge changes.

The baseline test failure remains recorded as a failed workflow even when a repair PR is opened. A passing test run is not proof of correctness. Require normal human review and branch protection before merging; configure required approvals in the repository's rulesets/branch protection settings.

The PR workflow is manual-only and has write permissions to create its branch and PR. Do not add `pull_request` triggers to that workflow. The normal diagnosis workflow remains separate.

## Setup

Create a fine-grained personal access token for this repository with **Agent tasks: read and write** permission and add it as the Actions repository secret `COPILOT_AGENT_TOKEN`. The Copilot cloud agent must be enabled and available to the token's user (Copilot Business or Enterprise). The workflow uses the GitHub Copilot Agent Tasks REST API, which is in public preview and may change.

No third-party model API key is needed. **The cloud-agent Tasks API does not accept the automatic Actions `GITHUB_TOKEN`**; the user token secret is required for API authentication. The agent's asynchronous execution time depends on GitHub and is not guaranteed to finish within two minutes. Each task is limited to four minutes and each workflow job has a ten-minute maximum.

## Run the demo

1. Configure `COPILOT_AGENT_TOKEN` as described above.
2. Open **Actions** and select **Self-healing CI**.
3. Select **Run workflow** on `main`.
4. Open the run. The intentional double-tax test should fail; inspect the diagnosis step and download the `ai-diagnosis` artifact.

No local model or model download is needed. Runs with failed tests require an available Copilot cloud agent and may take several minutes.

## Run tests locally

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q --cov=. --cov-context=test --cov-report= --json-report --json-report-file=pytest-report.json
python scripts/build_failure_context.py
```

The Python tests and failure-context builder run locally without Copilot credentials. To run diagnosis or patch-proposal scripts locally, set `COPILOT_AGENT_TOKEN` to a user-to-server token with Agent tasks read/write access, and set `GITHUB_REPOSITORY`, `GITHUB_REF_NAME`, and `GITHUB_SHA` to a repository and branch/commit the token can access. These scripts create cloud-agent tasks and fetch their resulting branches; they are not offline commands.

## Safety and limitations

- Only repository Python files associated with failed tests are included, with size limits. Review artifacts before sharing them; source code can contain sensitive material.
- Coverage narrows candidate files but cannot prove causality. Import-based fallback is approximate.
- The diagnosis and patch can be wrong. Confidence is an agent-generated label, not a calibrated probability.
- Patch generation can be disabled with the `create_draft_pr` input and is limited to `app.py`. The workflow validates the task's changed-file set and patch paths, checks that the patch applies cleanly, and runs all tests before creating a draft PR. All changes still require human review.
- The repair workflow requires a user-to-server token with Agent tasks read/write access and a Copilot plan that supports the cloud agent. Cloud-agent task duration and API availability are outside the workflow's control.
- The normal `pull_request` workflow skips diagnosis when the token is unavailable, including for fork pull requests where GitHub withholds repository secrets.
- Copilot tasks create remote working branches for their results. Those branches are not merged automatically; review and clean them up in the repository when appropriate.
