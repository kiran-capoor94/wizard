def test_agent_registration_imports_without_syntax_error():
    """Importing agent_registration must not raise SyntaxError."""
    import wizard.agent_registration  # noqa: F401
