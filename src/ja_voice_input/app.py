"""アプリ本体。ホットキー → 録音 → 認識 → 整形 → 貼り付け のパイプライン。"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import replace
from enum import Enum

from .config import Config
from .dictionary import Dictionary
from .feedback import Feedback
from .paste import FocusTarget, PasteResult, paste_text
from .postprocess import PostProcessor
from .recorder import Recorder
from .stt import create_backend

log = logging.getLogger(__name__)


class SessionState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    PASTING = "pasting"


class App:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.feedback = Feedback(cfg.sounds, cfg.notifications)
        self.dictionary = Dictionary.load(cfg.dictionary_path)
        log.info("dictionary: %d terms", len(self.dictionary.terms))

        # 辞書の用語を STT のヒントに流用(明示指定があればそちらを優先)
        stt_cfg = cfg.stt
        if not stt_cfg.initial_prompt and self.dictionary.terms:
            stt_cfg = replace(stt_cfg, initial_prompt=self.dictionary.stt_hint())

        self.recorder = Recorder(cfg.audio)
        self.stt = create_backend(stt_cfg)
        self.post = PostProcessor(cfg.llm, self.dictionary)

        self._stop_recording = threading.Event()
        self._session_lock = threading.Lock()
        self._state = SessionState.IDLE
        self._state_lock = threading.Lock()
        self._stt_lock = threading.Lock()
        self._post_lock = threading.Lock()
        self._warmup_started = False

    # --- ホットキー ---------------------------------------------------

    def on_hotkey(self) -> None:
        """録音中なら打ち切り、待機中なら新しいセッションを開始する。"""
        with self._state_lock:
            if self._state is SessionState.RECORDING:
                self._stop_recording.set()
                return
            if self._state is not SessionState.IDLE:
                self.feedback.notify("ja-voice-input", "音声を変換中です")
                return
            self._stop_recording.clear()
            self._state = SessionState.RECORDING
        target = (
            FocusTarget.capture()
            if self.cfg.paste.method == "keystroke" and self.cfg.paste.cancel_on_focus_change
            else None
        )
        threading.Thread(target=self._run_session, args=(target,), daemon=True).start()

    # --- パイプライン -------------------------------------------------

    def _set_state(self, state: SessionState) -> None:
        with self._state_lock:
            self._state = state

    def _run_session(self, target: FocusTarget | None = None) -> None:
        if not self._session_lock.acquire(blocking=False):
            return  # 前のセッションの処理中
        started_at = time.perf_counter()
        try:
            self.feedback.sound("start")
            audio = self.recorder.record(self._stop_recording)
            self.feedback.sound("stop")
            recorded_at = time.perf_counter()
            self._set_state(SessionState.PROCESSING)

            if audio is None:
                self.feedback.notify("ja-voice-input", "音声が検出されませんでした")
                return

            with self._stt_lock:
                raw = self.stt.transcribe(audio, self.cfg.audio.sample_rate)
            transcribed_at = time.perf_counter()
            log.debug("raw transcript: %s", raw)
            if not raw.strip():
                self.feedback.notify("ja-voice-input", "認識結果が空でした")
                return

            with self._post_lock:
                text = self.post.process(raw)
            processed_at = time.perf_counter()
            log.debug("refined transcript: %s", text)
            if not text:
                self.feedback.notify("ja-voice-input", "整形結果が空でした")
                return

            self._set_state(SessionState.PASTING)
            result = paste_text(text, self.cfg.paste, target)
            pasted_at = time.perf_counter()
            log.info(
                "session timing: record=%.0fms stt=%.0fms post=%.0fms paste=%.0fms total=%.0fms chars=%d",
                (recorded_at - started_at) * 1000,
                (transcribed_at - recorded_at) * 1000,
                (processed_at - transcribed_at) * 1000,
                (pasted_at - processed_at) * 1000,
                (pasted_at - started_at) * 1000,
                len(text),
            )
            if result is PasteResult.TARGET_CHANGED:
                self.feedback.notify(
                    "ja-voice-input",
                    "入力先が変わったため自動貼り付けを中止しました。結果はクリップボードにあります",
                )
                return
            self.feedback.sound("done")
        except Exception:
            log.exception("session failed")
            self.feedback.sound("error")
            self.feedback.notify("ja-voice-input", "エラーが発生しました(ログ参照)")
        finally:
            self._set_state(SessionState.IDLE)
            self._session_lock.release()

    def process_once(self) -> str | None:
        """ホットキーなしで 1 回だけ実行(動作確認用)。整形済みテキストを返す。"""
        self.feedback.sound("start")
        audio = self.recorder.record()
        self.feedback.sound("stop")
        if audio is None:
            return None
        with self._stt_lock:
            raw = self.stt.transcribe(audio, self.cfg.audio.sample_rate)
        log.debug("raw transcript: %s", raw)
        with self._post_lock:
            return self.post.process(raw)

    def _start_warmup(self) -> None:
        if self._warmup_started:
            return
        self._warmup_started = True

        def warmup_stt() -> None:
            if self.cfg.stt.warmup:
                started = time.perf_counter()
                try:
                    with self._stt_lock:
                        self.stt.warmup()
                    log.info(
                        "STT warm-up completed in %.0fms",
                        (time.perf_counter() - started) * 1000,
                    )
                except Exception:
                    log.warning("STT warm-up failed", exc_info=True)

        def warmup_postprocessor() -> None:
            with self._post_lock:
                self.post.warmup()

        threading.Thread(
            target=warmup_stt, name="ja-voice-input-stt-warmup", daemon=True
        ).start()
        threading.Thread(
            target=warmup_postprocessor, name="ja-voice-input-llm-warmup", daemon=True
        ).start()

    # --- 常駐 -----------------------------------------------------------

    def run(self) -> None:
        from pynput import keyboard  # macOS では入力監視権限が必要

        from .hotkey import (
            DoubleTapDetector,
            double_tap_key_name,
            is_double_tap_spec,
            resolve_target_keys,
        )

        self._start_warmup()
        log.info("hotkey: %s で音声入力を開始します(Ctrl+C で終了)", self.cfg.hotkey)
        if not is_double_tap_spec(self.cfg.hotkey):
            with keyboard.GlobalHotKeys({self.cfg.hotkey: self.on_hotkey}) as listener:
                listener.join()
            return

        targets = resolve_target_keys(double_tap_key_name(self.cfg.hotkey))
        detector = DoubleTapDetector()

        def on_press(key):
            if detector.on_press(key in targets):
                self.on_hotkey()

        def on_release(key):
            detector.on_release(key in targets)

        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()
