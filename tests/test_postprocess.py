from unittest import mock

from ja_voice_input.config import LlmConfig
from ja_voice_input.dictionary import Dictionary, Term
from ja_voice_input.postprocess import PostProcessor, basic_cleanup


class TestBasicCleanup:
    def test_removes_fillers(self):
        assert basic_cleanup("えーとこの関数をえっとリファクタして") == "この関数をリファクタして"

    def test_normalizes_whitespace(self):
        assert basic_cleanup("  テスト   を  実行  ") == "テスト を 実行"


def make_processor(enabled=True):
    d = Dictionary([Term(surface="Claude Code", readings=["クロードコード"])])
    return PostProcessor(LlmConfig(enabled=enabled), d)


class TestPostProcessor:
    def test_dictionary_applied_before_and_after_llm(self):
        p = make_processor()
        with mock.patch.object(p, "_llm_refine", return_value="クロードコードに頼む") as m:
            result = p.process("クロードコードで直して")
        # LLM には辞書適用済みテキストが渡る
        m.assert_called_once_with("Claude Codeで直して")
        # LLM 出力の取りこぼしも再置換される
        assert result == "Claude Codeに頼む"

    def test_falls_back_to_basic_cleanup_when_llm_fails(self):
        p = make_processor()
        with mock.patch.object(p, "_llm_refine", return_value=None):
            result = p.process("えーとクロードコードでテスト書いて")
        assert result == "Claude Codeでテスト書いて"

    def test_llm_disabled_uses_basic_cleanup(self):
        p = make_processor(enabled=False)
        assert p.process("あのークロードコードお願い") == "Claude Codeお願い"

    def test_empty_input(self):
        assert make_processor().process("   ") == ""

    def test_system_prompt_includes_dictionary(self):
        p = make_processor()
        assert "Claude Code" in p.system_prompt

    def test_llm_refine_calls_ollama_api(self):
        p = make_processor()
        fake_resp = mock.Mock()
        fake_resp.json.return_value = {"message": {"content": " 整形済み "}}
        fake_resp.raise_for_status.return_value = None
        with mock.patch("ja_voice_input.postprocess.requests.post",
                        return_value=fake_resp) as post:
            assert p._llm_refine("生テキスト") == "整形済み"
        url = post.call_args.args[0]
        payload = post.call_args.kwargs["json"]
        assert url == "http://localhost:11434/api/chat"
        assert payload["model"] == "gemma4:e4b"
        assert payload["stream"] is False
        assert payload["messages"][1]["content"] == "生テキスト"

    def test_llm_refine_returns_none_on_connection_error(self):
        import requests

        p = make_processor()
        with mock.patch("ja_voice_input.postprocess.requests.post",
                        side_effect=requests.ConnectionError("refused")):
            assert p._llm_refine("テキスト") is None
