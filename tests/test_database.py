def test_db_url_memory():
    from wizard.database import _db_url

    assert _db_url(":memory:") == "sqlite://"


def test_db_url_relative_path():
    from wizard.database import _db_url

    assert _db_url("wizard.db") == "sqlite:///wizard.db"


def test_db_url_absolute_path():
    from wizard.database import _db_url

    assert _db_url("/home/user/.wizard/wizard.db") == "sqlite:////home/user/.wizard/wizard.db"
