from ja_voice_input.dictionary import Dictionary, Term


def make_dict():
    return Dictionary([
        Term(surface="Claude Code", readings=["クロードコード", "クロード コード"],
             notes="AI コーディングエージェント"),
        Term(surface="Ollama", readings=["オラマ"]),
        Term(surface="プルリクエスト", readings=["プルリク"]),
    ])


class TestApply:
    def test_replaces_readings_with_surface(self):
        d = make_dict()
        assert d.apply("クロードコードに指示して") == "Claude Codeに指示して"
        assert d.apply("オラマで動かす") == "Ollamaで動かす"

    def test_longest_match_wins(self):
        # 「プルリクエスト」自体は readings に無いが、「プルリク」を含む。
        # 長い読みを先にマッチさせるので二重置換にならないことを確認
        d = Dictionary([
            Term(surface="プルリクエスト", readings=["プルリク", "プルリクエス"]),
        ])
        assert d.apply("プルリクエス出して") == "プルリクエスト出して"

    def test_no_terms_is_noop(self):
        d = Dictionary([])
        assert d.apply("そのまま") == "そのまま"

    def test_regex_special_chars_escaped(self):
        d = Dictionary([Term(surface="C++", readings=["シープラプラ", "C++."])])
        assert d.apply("C++.で書く") == "C++で書く"


class TestPrompt:
    def test_prompt_section_lists_terms(self):
        section = make_dict().prompt_section()
        assert "Claude Code" in section
        assert "クロードコード" in section
        assert "AI コーディングエージェント" in section

    def test_empty_dictionary_gives_empty_section(self):
        assert Dictionary([]).prompt_section() == ""

    def test_stt_hint_joins_surfaces(self):
        hint = make_dict().stt_hint()
        assert "Claude Code" in hint and "Ollama" in hint


class TestLoad:
    def test_missing_file_gives_empty_dict(self, tmp_path):
        d = Dictionary.load(tmp_path / "nope.yaml")
        assert d.terms == []

    def test_load_yaml(self, tmp_path):
        p = tmp_path / "terms.yaml"
        p.write_text(
            "terms:\n"
            "  - surface: Kubernetes\n"
            "    readings: [クバネティス, クーベルネイティス]\n"
            "    notes: k8s\n",
            encoding="utf-8",
        )
        d = Dictionary.load(p)
        assert len(d.terms) == 1
        assert d.apply("クバネティスにデプロイ") == "Kubernetesにデプロイ"
