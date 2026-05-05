"""Scenario: task-start SKILL-POST contains the note trigger decision tree."""
from wizard.skills import SKILL_TASK_START, load_skill_post


def test_skill_post_loads_and_contains_triggers():
    """load_skill_post(SKILL_TASK_START) returns the note trigger content."""
    content = load_skill_post(SKILL_TASK_START)
    assert content is not None, "SKILL-POST.md for task-start should exist"
    assert "Note Triggers" in content
    assert "save_note" in content


def test_skill_post_contains_all_five_triggers():
    """SKILL-POST lists all five note trigger conditions."""
    content = load_skill_post(SKILL_TASK_START)
    assert content is not None
    # Each trigger corresponds to a numbered entry
    assert "root cause" in content        # trigger 1
    assert "implementation approaches" in content  # trigger 2
    assert "test failed" in content       # trigger 3
    assert "contradicts" in content       # trigger 4
    assert "switch tasks" in content      # trigger 5


def test_skill_post_contains_mental_model_hint():
    """SKILL-POST includes the mental model inclusion rule."""
    content = load_skill_post(SKILL_TASK_START)
    assert content is not None
    assert "mental_model" in content
    assert "latest_mental_model" in content
