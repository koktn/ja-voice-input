"""録音開始/終了などのユーザーフィードバック(効果音・通知)。"""
from __future__ import annotations

import logging
import subprocess

log = logging.getLogger(__name__)

SOUNDS = {
    "start": "/System/Library/Sounds/Pop.aiff",
    "stop": "/System/Library/Sounds/Bottle.aiff",
    "done": "/System/Library/Sounds/Glass.aiff",
    "error": "/System/Library/Sounds/Basso.aiff",
}


class Feedback:
    def __init__(self, sounds: bool = True, notifications: bool = True):
        self.sounds = sounds
        self.notifications = notifications

    def sound(self, name: str) -> None:
        if not self.sounds:
            return
        path = SOUNDS.get(name)
        if path:
            # 非同期再生(録音や認識をブロックしない)
            subprocess.Popen(
                ["afplay", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def notify(self, title: str, message: str) -> None:
        if not self.notifications:
            return
        script = 'display notification "{}" with title "{}"'.format(
            message.replace("\\", "\\\\").replace('"', '\\"'),
            title.replace("\\", "\\\\").replace('"', '\\"'),
        )
        subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
