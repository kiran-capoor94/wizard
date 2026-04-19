from wizard.exceptions import ConfigurationError


def test_configuration_error_is_exception():
    err = ConfigurationError("bad config")
    assert str(err) == "bad config"
    assert isinstance(err, Exception)
