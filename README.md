# Self-Healing CI Demo

This repository shows a realistic portfolio experiment: a GitHub Actions workflow runs tests, sends the failure to an OpenAI model, and explains the likely root cause and fix. The goal is to demonstrate a practical AI-for-dev workflow without giving the agent full control over the repo.

Why this is a good portfolio project:
- It is easy to explain in one sentence.
- It combines CI/CD, testing, and AI.
- It shows real engineering thinking around safety and review.
- It is reproducible and can be presented in a demo or live walk-through.

## What the repo does

1. A test suite runs in GitHub Actions.
2. If a test fails, the workflow captures the failing output.
3. The failure details are sent to OpenAI.
4. The model returns a likely diagnosis and a fix suggestion.
5. The workflow prints the diagnosis for review and iteration.

This is intentionally limited and safe: it does not auto-merge or auto-edit code. A human still reviews the result.

## Example architecture

- GitHub Actions executes tests
- Python app contains a tiny intentionally broken function
- OpenAI API receives the failure log
- AI diagnosis is saved in the workflow output

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pytest -q
```

## GitHub setup

Create a GitHub Actions secret named `OPENAI_API_KEY`.

In your repository:
- Settings -> Secrets and variables -> Actions
- Add secret: `OPENAI_API_KEY`

## Repository structure

```text
.
├── app.py
├── requirements.txt
├── tests/
│   └── test_app.py
├── scripts/
│   └── diagnose_failure.py
├── .github/
│   └── workflows/
│       └── self-healing.yml
├── .gitignore
└── README.md
```

## Demo flow

1. The app contains a small, known bug.
2. The test suite fails.
3. The workflow triggers the AI diagnosis step.
4. The output shows the likely fix.
5. You can then manually patch the code and commit the change.

## Safety notes

- The workflow does not merge automatically.
- The AI is only used to diagnose and suggest a fix.
- No production credentials should be stored in the repo.
- Use repository permissions and branch protections in a real team setup.

## Next upgrades

- Add automatic PR creation for safe fixes.
- Add a second provider option, such as Azure OpenAI or Anthropic.
- Add a small evaluation harness to compare model diagnosis quality.
- Add a stronger app with multiple failing scenarios.

This repo is intentionally small, readable, and demo-friendly so it can be explained quickly in a job interview or portfolio review.
