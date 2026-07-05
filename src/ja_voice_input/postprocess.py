"""認識テキストの整形。Ollama のローカル LLM でフィラー除去・用語補正を行う。

LLM が使えない場合は正規表現ベースの簡易整形にフォールバックする。
"""
from __future__ import annotations

import logging
import re

import requests

from .config import LlmConfig
from .dictionary import Dictionary

log = logging.getLogger(__name__)

# LLM 無効時・障害時のフォールバック用フィラーパターン
FILLER_PATTERN = re.compile(
    r"(?:えーっと|えーと|えっと|あのー|あのう|そのー|えー、|あー、|うーん、|まあ、|なんか、)"
)

SYSTEM_PROMPT = """あなたは日本語音声認識の後処理を行うアシスタントです。
入力は音声認識の生テキストです。以下のルールで整形し、結果のテキストだけを出力してください。

- 「えーと」「あのー」などのフィラー(言い淀み)を削除する
- 認識誤りと思われる箇所を文脈から自然に修正する
- 話し言葉の冗長さは残してよいが、意味は変えない
- 句読点を適切に補う
- 用語辞書がある場合は、辞書の表記に統一する
- 説明・前置き・引用符は一切付けず、整形後のテキストのみを出力する
{dictionary}"""


def basic_cleanup(text: str) -> str:
    """LLM を使わない簡易整形。フィラー除去と空白の正規化のみ。"""
    text = FILLER_PATTERN.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


class PostProcessor:
    def __init__(self, cfg: LlmConfig, dictionary: Dictionary):
        self.cfg = cfg
        self.dictionary = dictionary
        dict_section = dictionary.prompt_section()
        self.system_prompt = SYSTEM_PROMPT.format(
            dictionary=("\n" + dict_section) if dict_section else ""
        )

    def process(self, text: str) -> str:
        if not text.strip():
            return ""
        # 決定論的な辞書置換を先に当てる(LLM に正しい表記を見せる)
        text = self.dictionary.apply(text)
        if self.cfg.enabled:
            refined = self._llm_refine(text)
            if refined is not None:
                # LLM 出力にも辞書を再適用(取りこぼしの保険)
                return self.dictionary.apply(refined)
            log.warning("LLM post-processing failed; falling back to basic cleanup")
        return self.dictionary.apply(basic_cleanup(text))

    def _llm_refine(self, text: str) -> str | None:
        try:
            resp = requests.post(
                f"{self.cfg.base_url.rstrip('/')}/api/chat",
                json={
                    "model": self.cfg.model,
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": text},
                    ],
                    "stream": False,
                    "options": {"temperature": self.cfg.temperature},
                },
                timeout=self.cfg.timeout,
            )
            resp.raise_for_status()
            content = resp.json().get("message", {}).get("content", "")
            content = content.strip()
            return content or None
        except (requests.RequestException, ValueError) as e:
            log.warning("ollama request failed: %s", e)
            return None
