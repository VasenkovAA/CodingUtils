from pathlib import Path

from codingutils.ai_review.plugins.base import BaseParser


class P(BaseParser):
    name = "p"

    @classmethod
    def get_supported_config_keys(cls):
        return []

    @classmethod
    def supported_extensions(cls):
        return [".txt"]

    def parse_functions(self, file_path):
        return []

    def parse_classes(self, file_path):
        return []


def test_parse_whole_file(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")

    p = P()
    elem = p.parse_whole_file(f)
    assert elem.name == "a.txt"
    assert elem.content == "hello"
    assert elem.type.value == "file"
