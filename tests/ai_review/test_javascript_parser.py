from pathlib import Path

from codingutils.ai_review.plugins.parsers.javascript_parser import JavaScriptParser
from codingutils.ai_review.core.models.domain import CodeElement


def test_javascript_parser_functions_and_classes(tmp_path: Path):
    f = tmp_path / "a.ts"
    f.write_text(
        """
export function foo(x: number) {
  return x + 1;
}

const bar = (y) => y * 2;

export class User {
  constructor(name) { this.name = name; }
  getName() { return this.name; }
}
""".strip(),
        encoding="utf-8",
    )

    p = JavaScriptParser(parse_arrow_functions=True)
    funcs = p.parse_functions(f)
    classes = p.parse_classes(f)

    fn_names = {e.name for e in funcs}
    assert "foo" in fn_names
    assert "bar" in fn_names
    assert "User.getName" in fn_names

    assert any(c.type == CodeElement.Type.CLASS and c.name == "User" for c in classes)
