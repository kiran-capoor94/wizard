"""Behaviour tests for hybrid search (embedding + BM25)."""
from wizard.embedding import embed, serialize_float32


def test_serialize_float32_length_matches_vector():
    # 4-element vector → 16 bytes (4 bytes per float32)
    assert len(serialize_float32([0.1, 0.2, 0.3, 0.4])) == 16


def test_serialize_float32_roundtrips():
    import struct
    vec = [1.0, 2.0, 3.0]
    result = serialize_float32(vec)
    unpacked = list(struct.unpack("3f", result))
    for a, b in zip(unpacked, vec, strict=True):
        assert abs(a - b) < 1e-5


def test_embed_returns_384_dims_or_none():
    result = embed("auth middleware throws 401 when token expires")
    if result is not None:
        assert len(result) == 384
        assert all(isinstance(x, float) for x in result)


def test_embed_empty_string_returns_none():
    assert embed("") is None


def test_embed_whitespace_returns_none():
    assert embed("   ") is None
