import pytest

from finbro.config import ConfigError, Settings, load_dotenv


def test_reads_database_url():
    settings = Settings.from_env({"DATABASE_URL": " postgresql+psycopg://u:p@db:5432/finbro "})
    assert settings.database_url == "postgresql+psycopg://u:p@db:5432/finbro"


@pytest.mark.parametrize("environ", [{}, {"DATABASE_URL": "  "}])
def test_missing_database_url_is_an_error(environ):
    with pytest.raises(ConfigError, match="DATABASE_URL"):
        Settings.from_env(environ)


def test_load_dotenv_does_not_override_existing(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# komentarz\nDATABASE_URL=postgresql+psycopg://z-pliku\nTEST_DATABASE_URL='postgresql+psycopg://test'\n\nBEZ_ROWNOSCI\n",
        encoding="utf-8",
    )
    environ = {"DATABASE_URL": "postgresql+psycopg://ze-srodowiska"}
    load_dotenv(env_file, environ)
    assert environ == {
        "DATABASE_URL": "postgresql+psycopg://ze-srodowiska",
        "TEST_DATABASE_URL": "postgresql+psycopg://test",
    }


def test_load_dotenv_ignores_missing_file(tmp_path):
    environ: dict[str, str] = {}
    load_dotenv(tmp_path / "brak.env", environ)
    assert environ == {}
