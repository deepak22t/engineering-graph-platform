from packages.common.config.settings import get_settings


def test_settings_load():
    settings = get_settings()

    assert settings.app_name == "Engineering Graph Platform"
    assert settings.app_env == "development"
    assert settings.app_port == 8000
