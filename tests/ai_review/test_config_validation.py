import pytest

from codingutils.common_utils import FilterConfig
from codingutils.ai_review.core.models.config import AIReviewConfig, LLMConfig, ProcessingConfig
from codingutils.ai_review.core.models.errors import ConfigValidationError


def test_default_config_creates():
    cfg = AIReviewConfig(filter_config=FilterConfig(directories=["."]))
    assert cfg.llm.provider
    assert cfg.llm.model


def test_context_window_validation():
    with pytest.raises(ConfigValidationError):
        AIReviewConfig(
            filter_config=FilterConfig(directories=["."]),
            llm=LLMConfig(context_window=100, max_output_tokens=80),
            processing=ProcessingConfig(max_input_tokens=50),
        )
