import pytest

from finbro.config import DEFAULT_LLM_MODEL, DEFAULT_LLM_URL, ConfigError, Settings, load_dotenv


def test_reads_all_variables():
    settings = Settings.from_env(
        {
            "DATABASE_URL": "postgresql+psycopg://u:p@db:5432/finbro",
            "LLM_URL": "http://model-runner.docker.internal/engines/v1",
            "LLM_MODEL": "ai/gemma4:E2B",
        }
    )
    assert settings.database_url == "postgresql+psycopg://u:p@db:5432/finbro"
    assert settings.llm_url == "http://model-runner.docker.internal/engines/v1"
    assert settings.llm_model == "ai/gemma4:E2B"


def test_llm_url_and_model_have_defaults():
    settings = Settings.from_env({"DATABASE_URL": "postgresql+psycopg://u:p@h/db", "LLM_MODEL": ""})
    assert settings.llm_url == DEFAULT_LLM_URL
    assert settings.llm_model == DEFAULT_LLM_MODEL == "ai/gemma4:E2B"


@pytest.mark.parametrize("environ", [{}, {"DATABASE_URL": "  "}])
def test_missing_database_url_is_an_error(environ):
    with pytest.raises(ConfigError, match="DATABASE_URL"):
        Settings.from_env(environ)


def test_load_dotenv_does_not_override_existing(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# komentarz\nDATABASE_URL=postgresql+psycopg://z-pliku\nLLM_MODEL='model'\n\nBEZ_ROWNOSCI\n",
        encoding="utf-8",
    )
    environ = {"DATABASE_URL": "postgresql+psycopg://ze-srodowiska"}
    load_dotenv(env_file, environ)
    assert environ == {
        "DATABASE_URL": "postgresql+psycopg://ze-srodowiska",
        "LLM_MODEL": "model",
    }


def test_load_dotenv_ignores_missing_file(tmp_path):
    environ: dict[str, str] = {}
    load_dotenv(tmp_path / "brak.env", environ)
    assert environ == {}
