import pytest
from verify import OPENALEX_KEY_VARIABLE


@pytest.fixture(autouse=True)
def no_openalex_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep a key set on the machine out of every request a test inspects."""
    monkeypatch.delenv(OPENALEX_KEY_VARIABLE, raising=False)
