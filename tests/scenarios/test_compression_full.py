"""Behaviour tests for full-level compression rules."""
from wizard.compression import compress


def test_middleware_abbreviated():
    assert compress("the middleware throws an error") == "mw throws err"


def test_repository_abbreviated():
    assert compress("the repository returns none") == "repo returns none"


def test_configuration_abbreviated():
    assert compress("the configuration is invalid") == "config is invalid"


def test_authentication_abbreviated():
    assert compress("the authentication failed") == "auth failed"


def test_database_abbreviated():
    assert compress("the database connection timed out") == "db connection timed out"


def test_environment_abbreviated():
    assert compress("the environment variable is missing") == "env var is missing"


def test_function_abbreviated():
    assert compress("the function returns none") == "fn returns none"


def test_parameter_abbreviated():
    assert compress("the parameter is required") == "param is required"


def test_abbreviations_skip_protected_tokens():
    # 'middleware' inside backticks must NOT be abbreviated
    assert "`middleware`" in compress("call `middleware` to handle")


def test_leading_we_should_dropped():
    assert compress("we should add a refresh path") == "add refresh path"


def test_leading_you_should_dropped():
    assert compress("you should restart the server") == "restart server"


def test_leading_it_should_dropped():
    assert compress("it should return none when empty") == "return none @ empty"


def test_leading_we_need_dropped():
    assert compress("we need to fix the auth bug") == "fix auth bug"


def test_leading_subject_mid_sentence_kept():
    result = compress("fixed the bug. we should deploy now")
    assert result.startswith("fixed")
    assert "deploy now" in result


def test_when_replaced_with_at():
    assert compress("throws 401 when session token expires") == "throws 401 @ session token expires"


def test_when_in_protected_token_untouched():
    assert "`when`" in compress("use `when` clause in query")


def test_cavemem_reference_example():
    """Canonical Cavemem full-level example from https://getcaveman.dev."""
    inp = "The auth middleware throws a 401 when the session token expires; we should add a refresh path."
    out = compress(inp)
    assert "mw" in out
    assert "auth" in out
    assert "401" in out
    assert "@" in out
    assert "session" in out
    assert "refresh" in out
    assert "we should" not in out.lower()
    assert "the auth middleware" not in out.lower()
