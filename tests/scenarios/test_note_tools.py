from wizard.tools.note_tools import rewind_task, what_am_i_missing


def test_rewind_task_is_importable():
    assert callable(rewind_task)


def test_what_am_i_missing_is_importable():
    assert callable(what_am_i_missing)
