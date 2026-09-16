from kira.core.config import get_config, reload_config


def test_config_loads_defaults():
    cfg = reload_config()
    assert cfg.kira.name == "KIRA"
    assert cfg.models.fast.provider == "ollama"
    assert cfg.models.embeddings.model == "nomic-embed-text"


def test_config_server_binds_lan():
    cfg = get_config()
    assert cfg.server.host == "0.0.0.0"
    assert cfg.server.port == 8750
