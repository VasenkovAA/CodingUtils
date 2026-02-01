from datetime import datetime, timedelta
from pathlib import Path

from codingutils.ai_review.core.models.domain import CodeElement, ReviewResult, ReviewSummary


def test_code_element_size_and_full_name(tmp_path: Path):
    p = tmp_path / "a.py"
    e = CodeElement(
        type=CodeElement.Type.FUNCTION,
        name="f",
        content="print('x')\n",
        file_path=p,
    )
    assert "a.py:f" in e.full_name
    assert e.size > 0


def test_review_result_is_meaningful():
    e = CodeElement(
        type=CodeElement.Type.FILE,
        name="a.py",
        content="x=1",
        file_path=Path("a.py"),
    )
    r1 = ReviewResult(element=e, review_text="Too short", tokens_used=10, timestamp=datetime.now())
    assert r1.is_meaningful is False

    r2 = ReviewResult(element=e, review_text=("a" * 60), tokens_used=10, timestamp=datetime.now())
    assert r2.is_meaningful is True


def test_review_summary_success_rate_and_duration():
    start = datetime.now()
    end = start + timedelta(seconds=3)
    s = ReviewSummary(
        total_elements=10,
        saved_count=7,
        errors=[],
        warnings=[],
        metrics={"start_time": start, "end_time": end},
        timestamp=end,
    )
    assert abs(s.success_rate - 0.7) < 1e-9
    assert abs(s.duration - 3.0) < 0.001
