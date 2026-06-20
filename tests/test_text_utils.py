from __future__ import annotations

from githublab_sync.text_utils import contains_ai_attribution, strip_ai_attribution


def test_strips_claude_coauthor_trailer():
    message = (
        "Fix the parser\n\n"
        "Handle empty input gracefully.\n\n"
        "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>\n"
    )
    cleaned = strip_ai_attribution(message)
    assert "Claude" not in cleaned
    assert "anthropic.com" not in cleaned
    assert "Fix the parser" in cleaned
    assert "Handle empty input gracefully." in cleaned


def test_strips_generated_with_marker_inline_and_line():
    body = "Implements feature\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"
    cleaned = strip_ai_attribution(body)
    assert "Generated with" not in cleaned
    assert cleaned.strip() == "Implements feature"


def test_preserves_normal_coauthors():
    message = "Title\n\nCo-authored-by: Jane Dev <jane@example.com>\n"
    cleaned = strip_ai_attribution(message)
    assert "Jane Dev" in cleaned


def test_empty_input():
    assert strip_ai_attribution("") == ""
    assert not contains_ai_attribution("")


def test_contains_detection():
    assert contains_ai_attribution("x\nCo-Authored-By: Claude <noreply@anthropic.com>")
    assert not contains_ai_attribution("just a normal message")


def test_trailing_newline_preserved():
    assert strip_ai_attribution("hello\n") == "hello\n"
