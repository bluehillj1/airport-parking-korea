import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_payload() -> dict:
    return json.loads((FIXTURES / "sample_response.json").read_text(encoding="utf-8"))


@pytest.fixture
def access_path() -> Path:
    return Path(__file__).parent.parent / "data" / "lot_access.json"
