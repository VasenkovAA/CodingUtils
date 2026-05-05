from __future__ import annotations

from textual.widget import Widget

from codingutils.tui.plugin_api import ModuleContext
from .ui import CommentCleanerUI


PLUGIN_META = {
    "id": "builtin.comment_cleaner",
    "name": "Comment Cleaner",
    "version": "0.1.0",
    "description": "Interactive comment removal: scan → review → apply (with saved decisions).",
}


def create_ui(ctx: ModuleContext) -> Widget:
    return CommentCleanerUI(ctx)

