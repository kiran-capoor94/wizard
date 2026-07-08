"""Deterministic Caveman-style text compressor for note content.

Applies grammar rules to reduce prose token count while preserving all
technical content (file paths, function names, error messages, code,
version numbers, identifiers) byte-for-byte.

Reference: https://getcaveman.dev — deterministic compression primitive.
"""

from __future__ import annotations

import re

_FILLER_WORDS = re.compile(
    r"\b(a|an|the|just|really|basically|actually|simply|essentially|generally)\b ",
    re.IGNORECASE,
)

_HEDGING = re.compile(
    r"\b(it might be worth|you could consider|it would be good to|"
    r"you should|make sure to|remember to|please note that|note that)\b",
    re.IGNORECASE,
)

_VERBOSE_PHRASES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bin order to\b", re.IGNORECASE), "to"),
    (re.compile(r"\bmake sure to\b", re.IGNORECASE), "ensure"),
    (re.compile(r"\bthe reason is because\b", re.IGNORECASE), "because"),
    (re.compile(r"\bhowever,?\s*", re.IGNORECASE), ""),
    (re.compile(r"\bfurthermore,?\s*", re.IGNORECASE), ""),
    (re.compile(r"\badditionally,?\s*", re.IGNORECASE), ""),
    (re.compile(r"\bin addition,?\s*", re.IGNORECASE), ""),
    (re.compile(r"\bimplemented a solution for\b", re.IGNORECASE), "fixed"),
    (re.compile(r"\bextensive\b", re.IGNORECASE), "large"),
    (re.compile(r"\butilize[sd]?\b", re.IGNORECASE), "use"),
    (re.compile(r"\bperform(?:ed|ing)?\b", re.IGNORECASE), "run"),
]

_ABBREVIATIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bmiddleware\b", re.IGNORECASE), "mw"),
    (re.compile(r"\brepositor(?:y|ies)\b", re.IGNORECASE), "repo"),
    (re.compile(r"\bconfiguration\b", re.IGNORECASE), "config"),
    (re.compile(r"\bauthentication\b", re.IGNORECASE), "auth"),
    (re.compile(r"\bauthorization\b", re.IGNORECASE), "authz"),
    (re.compile(r"\bdatabase\b", re.IGNORECASE), "db"),
    (re.compile(r"\benvironment\b", re.IGNORECASE), "env"),
    (re.compile(r"\bfunction\b", re.IGNORECASE), "fn"),
    (re.compile(r"\bparameter\b", re.IGNORECASE), "param"),
    (re.compile(r"\bimplementation\b", re.IGNORECASE), "impl"),
    (re.compile(r"\bapplication\b", re.IGNORECASE), "app"),
    (re.compile(r"\bdependenc(?:y|ies)\b", re.IGNORECASE), "dep"),
    (re.compile(r"\binfrastructure\b", re.IGNORECASE), "infra"),
    (re.compile(r"\borganization\b", re.IGNORECASE), "org"),
    (re.compile(r"\bintegration\b", re.IGNORECASE), "intg"),
    (re.compile(r"\bdocumentation\b", re.IGNORECASE), "docs"),
    (re.compile(r"\bgenerate[sd]?\b", re.IGNORECASE), "gen"),
    (re.compile(r"\bmaximum\b", re.IGNORECASE), "max"),
    (re.compile(r"\bminimum\b", re.IGNORECASE), "min"),
    (re.compile(r"\bmessage\b", re.IGNORECASE), "msg"),
    (re.compile(r"\brequest\b", re.IGNORECASE), "req"),
    (re.compile(r"\bresponse\b", re.IGNORECASE), "resp"),
    (re.compile(r"\berror\b", re.IGNORECASE), "err"),
    (re.compile(r"\bexception\b", re.IGNORECASE), "exc"),
    (re.compile(r"\btemporary\b", re.IGNORECASE), "tmp"),
    (re.compile(r"\bnumber\b", re.IGNORECASE), "num"),
    (re.compile(r"\bpointer\b", re.IGNORECASE), "ptr"),
    (re.compile(r"\bvalue\b", re.IGNORECASE), "val"),
    (re.compile(r"\bvariable\b", re.IGNORECASE), "var"),
    (re.compile(r"\bproperty\b", re.IGNORECASE), "prop"),
    (re.compile(r"\battribute\b", re.IGNORECASE), "attr"),
    (re.compile(r"\binstance\b", re.IGNORECASE), "inst"),
    (re.compile(r"\bobject\b", re.IGNORECASE), "obj"),
    (re.compile(r"\bpackage\b", re.IGNORECASE), "pkg"),
    (re.compile(r"\bsecret\b", re.IGNORECASE), "sec"),
    (re.compile(r"\btransaction\b", re.IGNORECASE), "tx"),
    (re.compile(r"\breference\b", re.IGNORECASE), "ref"),
    (re.compile(r"\bsynchronize[sd]?\b", re.IGNORECASE), "sync"),
    (re.compile(r"\basynchronous(?:ly)?\b", re.IGNORECASE), "async"),
    (re.compile(r"\btimestamp\b", re.IGNORECASE), "ts"),
    (re.compile(r"\bidentifier\b", re.IGNORECASE), "id"),
    (re.compile(r"\bprevious\b", re.IGNORECASE), "prev"),
]

# Drops "subject + auxiliary" at sentence/bullet start.
_SUBJECT_AUX = re.compile(
    r"(?:(?:^|(?<=\n))[ \t]*|(?<=[.!?;])[ \t]+)"
    r"(?:we|you|i|it|they|one)\s+"
    r"(?:should|would|could|will|can|need to|must|have to|want to)\s+",
    re.IGNORECASE | re.MULTILINE,
)

# "when" → "@"
_WHEN = re.compile(r"\bwhen\b", re.IGNORECASE)

# Matches fenced code blocks, inline backtick content, URLs, file paths, env vars.
_PROTECTED = re.compile(
    r"```.*?```"           # fenced code blocks
    r"|`[^`]+`"            # inline code
    r"|https?://\S+"       # URLs
    r"|/[\w./-]+"          # unix paths
    r"|\$[A-Z_][A-Z0-9_]*" # env vars
    r"|\b\w+\.\w+\b",      # dotted identifiers / file extensions
    re.DOTALL,
)

_CHAR_LIMIT = 1000


def compress(text: str) -> str:
    """Compress prose while preserving all technical tokens.

    Splits text on protected regions (code, paths, URLs, identifiers),
    compresses only the prose segments, then re-joins. Truncates at a
    word boundary if the result exceeds _CHAR_LIMIT.

    Truncation stops adding segments once the limit is reached rather than
    slicing the final joined string blindly — a protected segment (e.g. a
    fenced code block) is only ever included whole or dropped entirely,
    never cut mid-way, so the trailing word-boundary trim below always lands
    inside prose, not inside a code fence or URL.
    """
    parts = _PROTECTED.split(text)
    protected = _PROTECTED.findall(text)

    compressed_parts: list[str] = []
    total_len = 0
    for i, part in enumerate(parts):
        compressed = _compress_prose(part)
        compressed_parts.append(compressed)
        total_len += len(compressed)
        if total_len > _CHAR_LIMIT:
            break
        if i < len(protected):
            segment = protected[i]
            if total_len + len(segment) > _CHAR_LIMIT:
                break
            compressed_parts.append(segment)
            total_len += len(segment)

    result = "".join(compressed_parts)
    if len(result) <= _CHAR_LIMIT:
        return result

    cut = result[:_CHAR_LIMIT]
    ws = cut.rfind(" ")
    return cut[:ws] if ws > _CHAR_LIMIT - 100 else cut


def _compress_prose(text: str) -> str:
    for pattern, replacement in _VERBOSE_PHRASES:
        text = pattern.sub(replacement, text)
    text = _HEDGING.sub("", text)
    text = _FILLER_WORDS.sub("", text)
    for pattern, replacement in _ABBREVIATIONS:
        text = pattern.sub(replacement, text)
    text = _SUBJECT_AUX.sub("", text)
    text = _WHEN.sub("@", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
