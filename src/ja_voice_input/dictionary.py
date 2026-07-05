"""専門用語辞書。誤認識されやすい読みを正しい表記に変換する。

辞書ファイル (YAML):

    terms:
      - surface: "Claude Code"          # 正しい表記
        readings: ["クロードコード"]     # 音声認識が出しがちな表記
        notes: "AI コーディングエージェント"  # LLM への補足(任意)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Term:
    surface: str
    readings: list[str] = field(default_factory=list)
    notes: str = ""


class Dictionary:
    def __init__(self, terms: list[Term] | None = None):
        self.terms = terms or []
        # 長い読みから先にマッチさせる(部分文字列の誤置換を防ぐ)
        pairs = sorted(
            ((r, t.surface) for t in self.terms for r in t.readings if r),
            key=lambda p: len(p[0]),
            reverse=True,
        )
        self._pattern = (
            re.compile("|".join(re.escape(r) for r, _ in pairs)) if pairs else None
        )
        self._mapping = dict(pairs)

    @classmethod
    def load(cls, path: str | Path) -> "Dictionary":
        p = Path(path).expanduser()
        if not p.is_file():
            return cls([])
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        terms = [
            Term(
                surface=str(item["surface"]),
                readings=[str(r) for r in item.get("readings", [])],
                notes=str(item.get("notes", "")),
            )
            for item in data.get("terms", [])
            if item and item.get("surface")
        ]
        return cls(terms)

    def apply(self, text: str) -> str:
        """読み → 表記の決定論的な置換。LLM を通せない場合の保険にもなる。"""
        if not self._pattern:
            return text
        return self._pattern.sub(lambda m: self._mapping[m.group(0)], text)

    def prompt_section(self) -> str:
        """LLM のシステムプロンプトに埋め込む用語一覧を生成する。"""
        if not self.terms:
            return ""
        lines = ["## 用語辞書(音声認識の誤変換をこの表記に統一すること)"]
        for t in self.terms:
            entry = f"- 「{t.surface}」"
            if t.readings:
                entry += f" (誤変換例: {', '.join(t.readings)})"
            if t.notes:
                entry += f" — {t.notes}"
            lines.append(entry)
        return "\n".join(lines)

    def stt_hint(self, limit: int = 30) -> str:
        """STT の initial_prompt に使う用語列。"""
        return "、".join(t.surface for t in self.terms[:limit])
