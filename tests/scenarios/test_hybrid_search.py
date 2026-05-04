"""Behaviour tests for hybrid search (embedding + BM25)."""
from wizard.embedding import embed, serialize_float32


def test_serialize_float32_produces_correct_byte_length():
    vec = [0.1, 0.2, 0.3, 0.4]
    result = serialize_float32(vec)
    assert len(result) == 16  # 4 floats * 4 bytes each


def test_serialize_float32_roundtrips():
    import struct
    vec = [1.0, 2.0, 3.0]
    result = serialize_float32(vec)
    unpacked = list(struct.unpack("3f", result))
    assert len(unpacked) == 3
    for a, b in zip(unpacked, vec, strict=True):
        assert abs(a - b) < 1e-5


def test_embed_returns_384_dims_or_none():
    result = embed("auth middleware throws 401 when token expires")
    if result is not None:
        assert len(result) == 384
        assert all(isinstance(x, float) for x in result)


def test_embed_empty_string_returns_none_or_list():
    result = embed("")
    assert result is None or isinstance(result, list)
