"""
Tests for src.config.settings

These verify that configuration is genuinely read from the environment
(defaults apply when unset, real values are picked up when set) -- not
just that the module imports without raising an exception.
"""

import importlib


def _reload_settings_module():
    """
    Re-import src.config.settings so load_settings() logic can be
    exercised against whatever environment variables the test just
    changed via monkeypatch.
    """
    import src.config.settings as settings_module

    importlib.reload(settings_module)
    return settings_module


def test_defaults_when_env_vars_unset(monkeypatch):
    """If APP_NAME/ENVIRONMENT/DEBUG are not set, sensible defaults apply.

    Note: reload() re-runs load_dotenv(), which re-populates os.environ
    from the local .env file. So the target keys are cleared AFTER the
    reload, not before -- otherwise a developer's real .env (e.g.
    DEBUG=True) would silently repopulate them and this test would not
    actually be testing the "unset" case.
    """
    settings_module = _reload_settings_module()

    for key in ("APP_NAME", "ENVIRONMENT", "DEBUG"):
        monkeypatch.delenv(key, raising=False)

    result = settings_module.load_settings()

    assert result.app_name == "Veltrix"
    assert result.environment == "development"
    assert result.debug is False


def test_reads_values_from_environment(monkeypatch):
    """Settings must actually reflect what's in the environment, not just defaults."""
    monkeypatch.setenv("APP_NAME", "VeltrixTest")
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("NOTIFICATION_EMAIL", "owner@example.com")

    settings_module = _reload_settings_module()
    result = settings_module.load_settings()

    assert result.app_name == "VeltrixTest"
    assert result.environment == "staging"
    assert result.debug is True
    assert result.smtp_port == 2525
    assert result.notification_email == "owner@example.com"


def test_smtp_port_is_integer_not_string(monkeypatch):
    """SMTP_PORT must be usable as an int elsewhere in the code (e.g. smtplib)."""
    monkeypatch.delenv("SMTP_PORT", raising=False)

    settings_module = _reload_settings_module()
    result = settings_module.load_settings()

    assert isinstance(result.smtp_port, int)
    assert result.smtp_port == 587


def test_debug_flag_accepts_common_truthy_strings(monkeypatch):
    """DEBUG should parse common truthy spellings, not just the literal 'True'."""
    settings_module = _reload_settings_module()

    for truthy_value in ("1", "true", "True", "yes", "on"):
        monkeypatch.setenv("DEBUG", truthy_value)
        result = settings_module.load_settings()
        assert result.debug is True, f"Expected DEBUG={truthy_value!r} to parse as True"

    for falsy_value in ("0", "false", "False", "no", "off", ""):
        monkeypatch.setenv("DEBUG", falsy_value)
        result = settings_module.load_settings()
        assert result.debug is False, f"Expected DEBUG={falsy_value!r} to parse as False"