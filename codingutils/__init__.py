"""
CodingUtils - A comprehensive set of Python utilities for code analysis, 
file management, and project documentation.
"""

from .comment_extractor import CommentProcessor, main as comment_extractor_main
from .merger import FileMerger, main as merger_main
from .tree_generater import ProjectMapper, main as tree_generator_main

__version__ = "1.0.0"
__author__ = "VasenkovAA"
__email__ = "NoN"

__all__ = [
    "CommentProcessor",
    "FileMerger", 
    "ProjectMapper",
    "comment_extractor_main",
    "merger_main",
    "tree_generator_main",
]
