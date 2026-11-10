import pytest

from lepisma.config import Config
from lepisma.engine import lint_text, load_nlp


@pytest.fixture(scope="session")
def nlp():
    return load_nlp()


@pytest.fixture
def lint(nlp):
    def run(text: str, cfg: Config | None = None):
        return list(lint_text("doc.md", text, cfg or Config(), nlp).warnings)

    return run
