"""Behaviour tests for HeuristicNameFinder."""

import re

import pytest

from wizard.security import HeuristicNameFinder


@pytest.fixture
def finder():
    return HeuristicNameFinder(allowlist_patterns=[])


class TestHonorificDetection:
    def test_dr_single_name(self, finder):
        spans = finder.find_spans("Referred by Dr Ahmed.")
        assert any(t == "Dr Ahmed" for _, _, t in spans)

    def test_dr_two_names(self, finder):
        spans = finder.find_spans("Meeting with Dr Sarah Ahmed today.")
        assert any(t == "Dr Sarah Ahmed" for _, _, t in spans)

    def test_mr_single(self, finder):
        spans = finder.find_spans("Mr Jones called.")
        assert any(t == "Mr Jones" for _, _, t in spans)

    def test_prof_two_names(self, finder):
        spans = finder.find_spans("Supervised by Prof James Clark.")
        assert any(t == "Prof James Clark" for _, _, t in spans)


class TestTitleCasePairs:
    def test_two_title_case_words(self, finder):
        spans = finder.find_spans("John Smith attended the meeting.")
        assert any(t == "John Smith" for _, _, t in spans)

    def test_single_title_case_not_matched(self, finder):
        spans = finder.find_spans("Monday is the deadline.")
        texts = [t for _, _, t in spans]
        assert "Monday" not in texts

    def test_product_blocklist_skipped(self, finder):
        spans = finder.find_spans("Synced from Notion today.")
        texts = [t for _, _, t in spans]
        assert not any("Notion" in t for t in texts)


class TestContextTriggers:
    def test_meeting_with(self, finder):
        spans = finder.find_spans("meeting with Sarah Connor about the project.")
        assert any("Sarah Connor" in t for _, _, t in spans)

    def test_spoke_with(self, finder):
        spans = finder.find_spans("spoke with James Brown re: deployment.")
        assert any("James Brown" in t for _, _, t in spans)

    def test_single_name_after_trigger(self, finder):
        spans = finder.find_spans("meeting with Smith about the project.")
        texts = [t for _, _, t in spans]
        # Should capture just "Smith", not "Smith about"
        assert any(t == "Smith" for t in texts)
        assert not any("about" in t for t in texts)


class TestFalsePositiveGuards:
    def test_month_names_skipped(self, finder):
        spans = finder.find_spans("Due in January.")
        texts = [t for _, _, t in spans]
        assert "January" not in texts

    def test_claude_skipped(self, finder):
        spans = finder.find_spans("Used Claude Code for this.")
        texts = [t for _, _, t in spans]
        assert not any("Claude" in t for t in texts)

    def test_allowlist_pattern_not_detected_as_name(self):
        finder_with_al = HeuristicNameFinder(
            allowlist_patterns=[re.compile(r"ENG-\d+")]
        )
        spans = finder_with_al.find_spans("John Smith closed ENG-123.")
        texts = [t for _, _, t in spans]
        assert any("John Smith" in t for t in texts)
        assert not any("ENG-123" in t for t in texts)

    def test_all_caps_not_matched(self, finder):
        spans = finder.find_spans("JOHN SMITH attended.")
        texts = [t for _, _, t in spans]
        assert "JOHN SMITH" not in texts


class TestSpanBoundaries:
    def test_returns_correct_offsets(self, finder):
        text = "Referred by Dr Ahmed today."
        spans = finder.find_spans(text)
        for start, end, matched in spans:
            assert text[start:end] == matched

    def test_no_overlapping_spans(self, finder):
        text = "Dr John Smith joined."
        spans = finder.find_spans(text)
        for i, (s1, e1, _) in enumerate(spans):
            for j, (s2, e2, _) in enumerate(spans):
                if i != j:
                    assert e1 <= s2 or e2 <= s1, f"Overlapping: {spans}"
