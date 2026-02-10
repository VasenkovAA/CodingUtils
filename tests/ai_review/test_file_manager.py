from pathlib import Path

from codingutils.ai_review.infrastructure import FileManager


def test_file_manager_cache_hit_and_touch(tmp_path: Path):
    fm = FileManager(max_memory_mb=1)
    fm.max_memory_bytes = 10_000  # делаем маленький лимит для теста

    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")

    with fm.read_file(f) as c1:
        assert c1 == "hello"

    # Меняем файл на диске, но второй read должен вернуть из кэша
    f.write_text("changed", encoding="utf-8")

    with fm.read_file(f) as c2:
        assert c2 == "hello"

    # Проверяем что кэш реально содержит файл
    assert str(f.resolve()) in fm._file_contents  # noqa: SLF001


def test_file_manager_eviction_lru(tmp_path: Path):
    fm = FileManager(max_memory_mb=1)
    fm.max_memory_bytes = 120  # хватает на 2 файла по ~50 байт, но не на 3

    f1 = tmp_path / "1.txt"
    f2 = tmp_path / "2.txt"
    f3 = tmp_path / "3.txt"

    f1.write_text("a" * 50, encoding="utf-8")
    f2.write_text("b" * 50, encoding="utf-8")
    f3.write_text("c" * 50, encoding="utf-8")

    # загружаем f1 и f2 в кэш
    with fm.read_file(f1):
        pass
    with fm.read_file(f2):
        pass

    # делаем f1 самым свежим (LRU порядок станет: f2 (oldest), f1 (newest))
    with fm.read_file(f1):
        pass

    # добавление f3 должно вытеснить f2
    with fm.read_file(f3):
        pass

    cached = set(fm._file_contents.keys())  # noqa: SLF001
    assert str(f1.resolve()) in cached
    assert str(f3.resolve()) in cached
    assert str(f2.resolve()) not in cached


def test_file_manager_cleanup(tmp_path: Path):
    fm = FileManager(max_memory_mb=1)
    fm.max_memory_bytes = 100

    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")

    with fm.read_file(f) as _:
        pass

    fm.cleanup()
    assert fm._file_contents == {}  # noqa: SLF001
    assert fm._lru == []  # noqa: SLF001
    assert fm._total_memory == 0  # noqa: SLF001
