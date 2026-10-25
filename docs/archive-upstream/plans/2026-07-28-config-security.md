# Configuration Security Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enforce independent settings encryption keys outside development while retaining a warned development fallback and secure CORS defaults.

**Architecture:** `Settings` owns environment-specific configuration validation. `secret_crypto` consumes the validated configuration and emits a development-only compatibility warning when it derives encryption from the JWT key. Tests instantiate `Settings` directly so validation is deterministic and independent of process-wide cached settings.

**Tech Stack:** Python 3.10+, Pydantic Settings, cryptography Fernet, pytest.

---

### Task 1: Define the failing production-key validation tests

**Files:**
- Modify: `test/test_config_security.py`

**Step 1: Write the failing tests**

Add tests proving that staging and production reject a missing `SETTINGS_ENCRYPTION_KEY`, a key shorter than 32 characters, and a key equal to `JWT_SECRET_KEY`. Add one success test using distinct valid keys.

```python
with pytest.raises(ValueError, match="SETTINGS_ENCRYPTION_KEY"):
    Settings(
        ENVIRONMENT="staging",
        CORS_ORIGINS=["https://staging.sciminer.example.com"],
        JWT_SECRET_KEY="j" * 32,
    )
```

**Step 2: Run the focused tests and verify they fail**

Run: `pytest -q test/test_config_security.py`

Expected: the newly added tests fail because `Settings` does not validate the independent encryption key.

**Step 3: Implement the minimal validator**

Modify `backend/app/config.py` so staging and production require an encryption key with at least 32 characters that differs from the JWT key. Keep the existing JWT, CORS and production DEBUG checks unchanged.

**Step 4: Run the focused tests and verify they pass**

Run: `pytest -q test/test_config_security.py`

Expected: all configuration security tests pass.

### Task 2: Define and implement the warned development compatibility fallback

**Files:**
- Modify: `test/test_secret_crypto.py`
- Modify: `backend/app/common/secret_crypto.py`

**Step 1: Write the failing test**

Patch the module-level settings object in `app.common.secret_crypto` with a development settings instance that has a JWT key but no encryption key. Assert `_fernet()` emits a warning and still encrypts/decrypts a value.

**Step 2: Run the focused test and verify it fails**

Run: `pytest -q test/test_secret_crypto.py`

Expected: the warning assertion fails because the fallback is currently silent.

**Step 3: Implement the minimal fallback**

Modify `_fernet()` to prefer `SETTINGS_ENCRYPTION_KEY`. When it is absent in development, emit a module logger warning once and use `JWT_SECRET_KEY`. Do not add fallback behavior for staging or production because configuration construction rejects those states.

**Step 4: Run the focused tests and verify they pass**

Run: `pytest -q test/test_secret_crypto.py`

Expected: encryption round-trip and fallback-warning tests pass.

### Task 3: Secure defaults and documentation

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Modify: `test/test_config_security.py`

**Step 1: Write the failing default-CORS test**

Add a test asserting development defaults contain only local frontend origins and do not contain `"*"`.

**Step 2: Run the focused test and verify it fails**

Run: `pytest -q test/test_config_security.py::TestCORSDefaults`

Expected: failure because the current default uses a wildcard.

**Step 3: Implement the smallest configuration change**

Set `CORS_ORIGINS` to the documented local Vite origins. Update `.env.example` to use the same list and document independent `SETTINGS_ENCRYPTION_KEY` requirements for staging and production without providing secret values.

**Step 4: Run the focused tests and verify they pass**

Run: `pytest -q test/test_config_security.py`

Expected: all tests pass.

### Task 4: Run regression verification

**Files:**
- Test: `test/test_config_security.py`
- Test: `test/test_secret_crypto.py`
- Test: `test/test_model_services_service.py`

**Step 1: Run the security and service regression suite**

Run: `pytest -q test/test_config_security.py test/test_secret_crypto.py test/test_model_services_service.py`

Expected: all tests pass.

**Step 2: Check code formatting and imports**

Run: `python -m py_compile backend/app/config.py backend/app/common/secret_crypto.py`

Expected: exit code 0.

**Step 3: Commit after approval**

Run:

```bash
git add backend/app/config.py backend/app/common/secret_crypto.py backend/.env.example test/test_config_security.py test/test_secret_crypto.py docs/plans/2026-07-28-config-security-design.md docs/plans/2026-07-28-config-security.md
git commit -m "fix(security): validate settings encryption keys"
```
