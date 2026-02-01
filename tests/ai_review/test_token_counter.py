import sys
import types

from codingutils.ai_review.infrastructure import TokenCounter


def test_token_counter_approximate():
    tc = TokenCounter(method="approximate")
    assert tc.estimate("abcd") >= 1
    assert tc.estimate("a" * 100) > tc.estimate("a" * 10)


def test_token_counter_tiktoken_success(monkeypatch):
    # Подсовываем фейковый tiktoken
    fake = types.SimpleNamespace()

    class FakeEnc:
        def encode(self, text):
            return list(range(len(text)))  # 1 char = 1 token

    def encoding_for_model(_model):
        return FakeEnc()

    def get_encoding(_name):
        return FakeEnc()

    fake.encoding_for_model = encoding_for_model
    fake.get_encoding = get_encoding

    monkeypatch.setitem(sys.modules, "tiktoken", fake)

    tc = TokenCounter(method="tiktoken")
    assert tc.method == "tiktoken"
    assert tc.estimate("hello", model="any-model") == 5


def test_token_counter_tiktoken_fallback_on_error(monkeypatch):
    fake = types.SimpleNamespace()

    class BadEnc:
        def encode(self, _text):
            raise RuntimeError("boom")

    def encoding_for_model(_model):
        return BadEnc()

    def get_encoding(_name):
        return BadEnc()

    fake.encoding_for_model = encoding_for_model
    fake.get_encoding = get_encoding

    monkeypatch.setitem(sys.modules, "tiktoken", fake)

    tc = TokenCounter(method="tiktoken")
    # при ошибке должен переключиться на approximate
    n = tc.estimate("abcd" * 10, model="any-model")
    assert tc.method == "approximate"
    assert n > 0
