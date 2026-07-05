"""アクティブなテキスト入力欄への貼り付け(macOS)。

クリップボード経由で Cmd+V を送出する。System Events を使うため
「アクセシビリティ」権限が必要。
"""
from __future__ import annotations

import logging
import subprocess
import time

from .config import PasteConfig

log = logging.getLogger(__name__)


def _pbcopy(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)


def _pbpaste() -> str:
    result = subprocess.run(["pbpaste"], capture_output=True, check=False)
    return result.stdout.decode("utf-8", errors="replace")


def _send_cmd_v() -> None:
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "System Events" to keystroke "v" using command down',
        ],
        check=True,
        capture_output=True,
    )


def paste_text(text: str, cfg: PasteConfig) -> None:
    if not text:
        return
    previous = _pbpaste() if cfg.restore_clipboard else None
    _pbcopy(text)
    if cfg.method == "keystroke":
        time.sleep(cfg.keystroke_delay)
        try:
            _send_cmd_v()
        except subprocess.CalledProcessError as e:
            log.error(
                "Cmd+V の送出に失敗しました。システム設定 > プライバシーとセキュリティ > "
                "アクセシビリティ でターミナルを許可してください: %s",
                e.stderr.decode("utf-8", errors="replace") if e.stderr else e,
            )
            return  # テキストはクリップボードに残す(手動で貼り付け可能)
        if cfg.restore_clipboard and previous is not None:
            time.sleep(0.3)  # ペースト完了を待ってから復元
            _pbcopy(previous)
