# Contributing to Self-Healing CI

Thank you for your interest in this project! This is a portfolio/proof-of-concept project, and we welcome feedback, suggestions, and community engagement.

## Ways to Contribute

### 1. Report Issues & Bugs

Found a problem? Help us improve:

- **Search first**: Check [existing issues](https://github.com/AjiKunjumon/self-healing-ci/issues) to avoid duplicates
- **Be detailed**: Include:
  - What you were trying to do
  - What happened (error messages, logs)
  - Expected behavior
  - Your environment (Python version, OS, etc.)
  - Steps to reproduce

### 2. Suggest Improvements

Have ideas to enhance the project?

- Open a [Discussion](https://github.com/AjiKunjumon/self-healing-ci/discussions) or [Issue](https://github.com/AjiKunjumon/self-healing-ci/issues)
- Describe your use case and what would help
- Reference related issues or discussions

### 3. Improve Documentation

Documentation improvements are always valuable:

- Found unclear sections? Open an issue with suggestions
- Spot typos or grammar issues? Feel free to propose fixes
- Want to add tutorials or examples? Let's discuss!

### 4. Code Contributions

Interested in submitting code?

1. **Fork the repository**
   ```bash
   git clone https://github.com/your-username/self-healing-ci.git
   cd self-healing-ci
   git checkout -b feature/your-feature
   ```

2. **Set up development environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   ```

3. **Make your changes**
   - Follow existing code style
   - Add comments for complex logic
   - Update relevant documentation

4. **Test your changes**
   ```bash
   python -m pytest -q --cov=. --cov-context=test --cov-report= --json-report
   ```

5. **Open a Pull Request**
   - Provide a clear description of changes
   - Reference related issues
   - Be open to feedback and iteration

## Workflow Guidelines

### For Bug Fixes
- Create a focused PR with just the fix
- Include tests demonstrating the bug and fix
- Reference the issue being fixed

### For Features
- Open a Discussion first to get feedback
- Keep changes scoped and focused
- Add tests and documentation
- Update README if adding new functionality

### For Documentation
- Create a focused PR with documentation changes
- Preview changes locally if possible
- Keep language clear and concise

## Code Standards

- **Python**: Follow [PEP 8](https://pep8.org/) style guide
- **Tests**: Use pytest; aim for meaningful test coverage
- **Comments**: Write clear, helpful comments
- **Git Commits**: Use descriptive commit messages

## Review Process

All contributions go through review:

1. We'll review your submission and provide feedback
2. You may be asked to make revisions
3. Once approved, your contribution will be merged
4. Your work will be recognized in the project history

## Questions?

- **Have questions?** Open a [Discussion](https://github.com/AjiKunjumon/self-healing-ci/discussions)
- **Need help?** Check the [README](README.md) or existing issues
- **Found a security issue?** Please report it responsibly

## Code of Conduct

Please be respectful and constructive in all interactions. We're building this together!

---

Thank you for contributing to making Self-Healing CI better! 🚀
