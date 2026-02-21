
"""
Регистрация встроенных плагинов TUI.
Каждый модуль внутри этого пакета должен сам регистрировать плагин в tool_registry.
"""

from . import tree_generator #noqa F401
from . import selective_comment_removal #noqa F401
