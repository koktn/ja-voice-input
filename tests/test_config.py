import pytest

from ja_voice_input.config import Config, load_config


class TestLoadConfig:
    def test_defaults_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # カレントの config.yaml を拾わないように
        monkeypatch.setattr(
            "ja_voice_input.config.DEFAULT_CONFIG_PATHS",
            [tmp_path / "missing.yaml"],
        )
        cfg = load_config()
        assert isinstance(cfg, Config)
        assert cfg.stt.backend == "whispercpp"
        assert cfg.llm.model == "gemma4:e4b"
        assert cfg.audio.silence_duration == 1.2

    def test_partial_override(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text(
            "hotkey: '<cmd>+<shift>+d'\n"
            "stt:\n"
            "  backend: mlx\n"
            "  model: turbo\n"
            "audio:\n"
            "  silence_duration: 0.8\n",
            encoding="utf-8",
        )
        cfg = load_config(p)
        assert cfg.hotkey == "<cmd>+<shift>+d"
        assert cfg.stt.backend == "mlx"
        assert cfg.stt.model == "turbo"
        assert cfg.stt.language == "ja"  # 未指定はデフォルト維持
        assert cfg.audio.silence_duration == 0.8
        assert cfg.llm.enabled is True

    def test_unknown_keys_ignored(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text("stt: {backend: whispercpp, bogus_key: 1}\nfuture_option: x\n",
                     encoding="utf-8")
        cfg = load_config(p)
        assert cfg.stt.backend == "whispercpp"

    def test_explicit_missing_path_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nope.yaml")
