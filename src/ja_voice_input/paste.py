"""macOS の入力先とクリップボードを保護したテキスト貼り付け。"""
from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .config import PasteConfig

log = logging.getLogger(__name__)


def _copy_ax_attribute(element: Any, attribute: str) -> Any | None:
    try:
        import ApplicationServices as AS

        error, value = AS.AXUIElementCopyAttributeValue(element, attribute, None)
        return value if error == 0 else None
    except Exception:
        return None


def _ax_pid(element: Any) -> int | None:
    try:
        import ApplicationServices as AS

        error, pid = AS.AXUIElementGetPid(element, None)
        return int(pid) if error == 0 else None
    except Exception:
        return None


def _cf_equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    try:
        from CoreFoundation import CFEqual

        return bool(CFEqual(left, right))
    except Exception:
        return left == right


def _front_window_id(pid: int) -> int | None:
    """画面上で最前面にある対象プロセスの通常ウィンドウIDを返す。"""
    try:
        import Quartz

        options = (
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements
        )
        windows = Quartz.CGWindowListCopyWindowInfo(
            options, Quartz.kCGNullWindowID
        ) or []
        owned = [
            window
            for window in windows
            if int(window.get(Quartz.kCGWindowOwnerPID, -1)) == pid
        ]
        for window in owned:  # 通常のmacOSウィンドウ
            if int(window.get(Quartz.kCGWindowLayer, -1)) == 0:
                return int(window[Quartz.kCGWindowNumber])
        # 一部のWebView系アプリは独自レイヤーだけを持つ。巨大な背景面や
        # 小さなオーバーレイを除き、前面から最初の実ウィンドウを採用する。
        for window in owned:
            bounds = window.get(Quartz.kCGWindowBounds, {})
            width = float(bounds.get("Width", 0))
            height = float(bounds.get("Height", 0))
            if 200 <= width <= 10000 and 100 <= height <= 10000:
                return int(window[Quartz.kCGWindowNumber])
    except Exception:
        log.debug("CGWindow から入力先を取得できません", exc_info=True)
    return None


@dataclass(frozen=True)
class FocusTarget:
    """録音開始時にフォーカスされていたアプリ・ウィンドウ・UI要素。"""

    pid: int
    window_id: int | None = None
    window: Any | None = None
    element: Any | None = None

    @classmethod
    def capture(cls) -> "FocusTarget | None":
        """取得可能な最も細かい粒度で現在の入力先を記録する。"""
        try:
            from AppKit import NSWorkspace

            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            fallback_pid = int(app.processIdentifier()) if app is not None else None
        except Exception:
            fallback_pid = None

        try:
            import ApplicationServices as AS

            system = AS.AXUIElementCreateSystemWide()
            focused_app = _copy_ax_attribute(system, AS.kAXFocusedApplicationAttribute)
            if focused_app is not None:
                pid = _ax_pid(focused_app) or fallback_pid
                if pid is not None:
                    return cls(
                        pid=pid,
                        window_id=_front_window_id(pid),
                        window=_copy_ax_attribute(focused_app, AS.kAXFocusedWindowAttribute),
                        element=_copy_ax_attribute(focused_app, AS.kAXFocusedUIElementAttribute),
                    )
        except Exception:
            log.debug("Accessibility API から入力先を取得できません", exc_info=True)

        return (
            cls(fallback_pid, window_id=_front_window_id(fallback_pid))
            if fallback_pid is not None
            else None
        )

    def matches_current(self) -> bool:
        current = self.capture()
        if current is None or current.pid != self.pid:
            return False
        if self.window_id is not None:
            if current.window_id is None or current.window_id != self.window_id:
                return False
        if self.window is not None:
            if current.window is None or not _cf_equal(self.window, current.window):
                return False
        if self.element is not None:
            if current.element is None or not _cf_equal(self.element, current.element):
                return False
        return True


@dataclass
class ClipboardSnapshot:
    """NSPasteboard の全アイテム・全表現を保持するスナップショット。"""

    items: list[dict[str, bytes]]

    @classmethod
    def capture(cls) -> "ClipboardSnapshot | None":
        try:
            from AppKit import NSPasteboard

            items: list[dict[str, bytes]] = []
            for item in NSPasteboard.generalPasteboard().pasteboardItems() or []:
                representations: dict[str, bytes] = {}
                for type_name in item.types() or []:
                    data = item.dataForType_(type_name)
                    if data is not None:
                        representations[str(type_name)] = bytes(data)
                items.append(representations)
            return cls(items)
        except Exception:
            log.debug("クリップボードの全形式を保存できません", exc_info=True)
            return None

    def restore(self) -> None:
        from AppKit import NSData, NSPasteboard, NSPasteboardItem

        objects = []
        for representations in self.items:
            item = NSPasteboardItem.alloc().init()
            for type_name, raw in representations.items():
                data = NSData.dataWithBytes_length_(raw, len(raw))
                item.setData_forType_(data, type_name)
            objects.append(item)
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        if objects:
            pasteboard.writeObjects_(objects)


def _pasteboard_change_count() -> int | None:
    try:
        from AppKit import NSPasteboard

        return int(NSPasteboard.generalPasteboard().changeCount())
    except Exception:
        return None


def _pbcopy(text: str, timeout: float) -> None:
    subprocess.run(
        ["pbcopy"], input=text.encode("utf-8"), check=True, timeout=timeout
    )


def _send_cmd_v(timeout: float) -> None:
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "System Events" to keystroke "v" using command down',
        ],
        check=True,
        capture_output=True,
        timeout=timeout,
    )


class PasteResult(Enum):
    PASTED = "pasted"
    COPIED = "copied"
    TARGET_CHANGED = "target_changed"


def paste_text(
    text: str, cfg: PasteConfig, target: FocusTarget | None = None
) -> PasteResult:
    if not text:
        return PasteResult.COPIED
    previous = (
        ClipboardSnapshot.capture()
        if cfg.method == "keystroke" and cfg.restore_clipboard
        else None
    )
    _pbcopy(text, cfg.subprocess_timeout)
    written_change_count = _pasteboard_change_count()
    if cfg.method == "clipboard":
        return PasteResult.COPIED

    time.sleep(cfg.keystroke_delay)
    if cfg.cancel_on_focus_change and target is not None and not target.matches_current():
        log.info("入力先が変わったため自動貼り付けを中止しました")
        return PasteResult.TARGET_CHANGED  # 結果はクリップボードに残す
    try:
        _send_cmd_v(cfg.subprocess_timeout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        stderr = getattr(e, "stderr", None)
        detail = stderr.decode("utf-8", errors="replace") if stderr else str(e)
        log.error(
            "Cmd+V の送出に失敗しました。システム設定 > プライバシーとセキュリティ > "
            "アクセシビリティ でターミナルを許可してください: %s",
            detail,
        )
        return PasteResult.COPIED

    if cfg.restore_clipboard and previous is not None:
        time.sleep(cfg.restore_delay)
        # 待機中にユーザーがコピーした場合、その新しい内容を上書きしない。
        if (
            written_change_count is not None
            and _pasteboard_change_count() == written_change_count
        ):
            try:
                previous.restore()
            except Exception:
                log.warning("クリップボードの復元に失敗しました", exc_info=True)
    return PasteResult.PASTED
