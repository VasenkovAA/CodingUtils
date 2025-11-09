from setuptools import setup, find_packages
import pathlib

here = pathlib.Path(__file__).parent.resolve()

long_description = (here / "README.md").read_text(encoding="utf-8")

setup(
    name="codingutils",
    version="1.0.0",
    description="A comprehensive set of Python utilities for code analysis and file management",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="VasenkovAA",
    author_email="NoN",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    keywords="code, comments, file management, project structure, utilities",
    packages=find_packages(),
    python_requires=">=3.9, <4",
    install_requires=[
        "langdetect>=1.0.9",
    ],
    entry_points={
        "console_scripts": [
            "comment-extractor=codingutils.comment_extractor:main",
            "file-merger=codingutils.merger:main",
            "tree-generator=codingutils.tree_generater:main",
        ],
    },
    project_urls={
        "Bug Reports": "https://github.com/VasenkovAA/CodingUtils/issues",
        "Source": "https://github.com/VasenkovAA/CodingUtils",
    },
)
