from pathlib import Path

from codingutils.ai_review.infrastructure import HashStorage


def test_hash_storage_save_load(tmp_path: Path):
    p = tmp_path / "hashes.json"
    hs = HashStorage(p)
    assert hs.has_changed("x", "abc") is True
    hs.update_hash("x", "abc")
    assert hs.has_changed("x", "abc") is False
    hs.save()

    hs2 = HashStorage(p)
    assert hs2.has_changed("x", "abc") is False
    assert hs2.has_changed("x", "abcd") is True
