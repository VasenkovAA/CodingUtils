import subprocess
from typing import Optional

def run(cmd: str, timeout: Optional[int] = None) -> str:
    # intentionally naive example
    result = subprocess.check_output(cmd, shell=True, timeout=timeout)
    return result.decode("utf-8")

class User:
    def __init__(self, name: str):
        self.name = name

    def greeting(self) -> str:
        return f"Hello, {self.name}"
