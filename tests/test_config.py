from data_agent import config


def test_load_dotenv_keys_reads_declared_keys(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "# comment",
                "PG_USER=pgethan",
                "PG_PASSWORD='secret=value'",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert config._load_dotenv_keys() == {"PG_USER", "PG_PASSWORD"}


def test_dotenv_key_prevents_legacy_postgres_override(monkeypatch) -> None:
    monkeypatch.delenv("PG_USER", raising=False)
    monkeypatch.setattr(config, "_load_dotenv_keys", lambda: {"PG_USER"})
    monkeypatch.setattr(
        config,
        "_load_legacy_postgres_env",
        lambda: {"pg_user": "legacy_user"},
    )

    config.get_settings.cache_clear()
    try:
        settings = config.get_settings()
    finally:
        config.get_settings.cache_clear()

    assert settings.pg_user != "legacy_user"
