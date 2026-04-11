from wizard.security import SecurityService


def test_email_is_redacted():
    svc = SecurityService()
    result = svc.scrub("Contact john.doe@example.com for help")
    assert "[EMAIL_1]" in result.clean
    assert "john.doe@example.com" not in result.clean
    assert result.was_modified is True


def test_multiple_emails_get_indexed_stubs():
    svc = SecurityService()
    result = svc.scrub("a@x.com and b@y.com")
    assert "[EMAIL_1]" in result.clean
    assert "[EMAIL_2]" in result.clean


def test_nhs_id_is_redacted():
    svc = SecurityService()
    result = svc.scrub("Patient NHS ID: 943 476 5919")
    assert "[NHS_ID_1]" in result.clean
    assert "943 476 5919" not in result.clean


def test_secret_token_is_redacted():
    svc = SecurityService()
    result = svc.scrub("Authorization: Bearer abc123xyz456def789ghi0")
    assert "[SECRET_1]" in result.clean


def test_clean_text_is_unchanged():
    svc = SecurityService()
    result = svc.scrub("This is safe text with no PII")
    assert result.clean == "This is safe text with no PII"
    assert result.was_modified is False


def test_allowlist_skips_pattern():
    svc = SecurityService(allowlist=["SISU"])
    result = svc.scrub("Team SISU is working on this")
    assert "SISU" in result.clean


def test_allowlist_regex_skips_jira_keys():
    svc = SecurityService(allowlist=[r"ENG-\d+"])
    result = svc.scrub("See ticket ENG-123 for details")
    assert "ENG-123" in result.clean


def test_original_to_stub_audit_map():
    svc = SecurityService()
    result = svc.scrub("Email: test@example.com")
    assert "test@example.com" in result.original_to_stub
    assert result.original_to_stub["test@example.com"] == "[EMAIL_1]"


def test_scrub_is_idempotent():
    svc = SecurityService()
    first = svc.scrub("Email: user@test.com")
    second = svc.scrub(first.clean)
    assert first.clean == second.clean
