import sys
import os
import pytest


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

@pytest.fixture(autouse=True)
def cleanup_output_files():
    """Автоматическая очистка выходных файлов после тестов."""
    before_test = set()
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.txt') and 'merged' in file:
                before_test.add(os.path.join(root, file))

    yield

    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.txt') and 'merged' in file:
                filepath = os.path.join(root, file)
                if filepath not in before_test:
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
