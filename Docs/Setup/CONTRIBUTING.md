# Kynetic AI — Contributing Guidelines

Thank you for your interest in contributing to **Kynetic AI**, the compute-first, AI-native marketplace! We welcome contributions from developers, security researchers, and community members.

---

## 1. Code of Conduct

Kynetic AI enforces a zero-tolerance policy for harassment, discrimination, or abusive behavior. All contributors are expected to uphold a professional, respectful, and inclusive environment.

---

## 2. Development Workflow & Branching Strategy

We follow a structured Git feature-branch workflow:

```
main  ──────────────────────────────────────────────────────────► (Production Ready)
        \                                         /
         └───► feature/intent-router-v2 ────────► PR Review ──┘
         └───► fix/wallet-overdraft-bug ────────► PR Review ──┘
```

### Branch Naming Conventions
- `feature/<short-description>`: New features or service expansions (e.g., `feature/ebpf-firewall-v2`)
- `fix/<issue-description>`: Bug fixes or security patches (e.g., `fix/jwt-expiry-handling`)
- `docs/<doc-title>`: Documentation updates (e.g., `docs/api-spec-update`)
- `refactor/<module-name>`: Code restructuring without functional changes

---

## 3. Pull Request Guidelines

Before submitting a Pull Request (PR):
1. **Sync with Main**: Ensure your branch is rebased against the latest `main`:
   ```bash
   git fetch origin
   git rebase origin/main
   ```
2. **Run All Tests**: All 170 unit, integration, infrastructure, financial, legal, and security tests must pass cleanly:
   ```bash
   python3 -m pytest tests/ -v
   ```
3. **Lint & Format Code**: Check formatting using `ruff`, `black`, and `mypy`:
   ```bash
   black --check kynetic-ai/
   ruff check kynetic-ai/
   mypy kynetic-ai/
   ```
4. **Descriptive PR Title & Summary**: Describe what changes were made, why they were made, and reference any linked GitHub issues.

---

## 4. Test-Driven Development (TDD) Requirement

- Every new API endpoint, database schema change, billing calculation, or security policy **MUST** include corresponding automated unit/integration tests in `tests/`.
- Never delete or comment out existing assertions to pass tests. Fix the underlying implementation contract.

---

## 5. Security & Responsible Disclosure

If you discover a potential security vulnerability (e.g., container escape, authentication bypass, data leakage), **DO NOT** open a public issue. Email our security team directly at `security@kynetic.ai`. We will respond within 24 hours.
