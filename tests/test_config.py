from app.config import Settings


def test_admin_ids_are_parsed_from_csv() -> None:
    settings = Settings(
        bot_token="123456:example",
        admin_ids="123, 456,789",
        database_url="postgresql+asyncpg://user:pass@localhost/test",
    )
    assert settings.admin_ids == [123, 456, 789]


def test_defaults_are_usable() -> None:
    settings = Settings(
        bot_token="123456:example",
        admin_ids=[],
        database_url="postgresql+asyncpg://user:pass@localhost/test",
    )
    assert settings.min_players == 5
    assert settings.max_players == 15
    assert settings.default_language == "uz"
