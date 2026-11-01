import copy
import json
from pathlib import Path
import pytest

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "limit_teaching_package.json"

@pytest.fixture
def teacher_package():
    return copy.deepcopy(json.loads(SAMPLE.read_text(encoding="utf-8")))