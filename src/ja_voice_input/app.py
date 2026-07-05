"""アプリ本体。ホットキー → 録音 → 認識 → 整形 → 貼り付け のパイプライン。"""
from __future__ import annotations

import logging
import threading

from .config import Config
from .dictionary import Dictionary
from .feedback import Feedback
from .paste import paste_text
from .postprocess import PostProcessor
from .recorder import Recorder
from .stt import create_backend

log = logging.getLogger(__name__)


class App:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.feedback = Feedback(cfg.sounds, cfg.notifications)
        self.dictionary = Dictionary.load(cfg.dictionary_path)
        log.info("dictionary: %d terms", len(self.dictionary.terms))

        # 辞書の用語を STT のヒントに流用(明示指定があればそちらを優先)
        if not cfg.stt.initial_prompt and self.dictionary.terms:
            cfg.stt.initial_prompt = self.dictionary.stt_hint()

        self.recorder = Recorder(cfg.audio)
        self.stt = create_backend(cfg.stt)  # モデルはここで事前ロード
        self.post = PostProcessor(cfg.llm, self.dictionary)

        self._stop_recording = threading.Event()
        self._session_lock = threading.Lock()
        self._recording = False

    # --- ホットキー ---------------------------------------------------

    def on_hotkey(self) -> None:
        """録音中なら打ち切り、待機中なら新しいセッションを開始する。"""
        if self._recording:
            self._stop_recording.set()
            return
        threading.Thread(target=self._run_session, daemon=True).start()

    # --- パイプライン -------------------------------------------------

    def _run_session(self) -> None:
        if not self._session_lock.acquire(blocking=False):
            return  # 前のセッションの処理中
        try:
            self._recording = True
            self._stop_recording.clear()
            self.feedback.sound("start")
            audio = self.recorder.record(self._stop_recording)
            self._recording = False
            self.feedback.sound("stop")

            if audio is None:
                self.feedback.notify("ja-voice-input", "音声が検出されませんでした")
                return

            raw = self.stt.transcribe(audio, self.cfg.audio.sample_rate)
            log.info("raw: %s", raw)
            if not raw.strip():
                self.feedback.notify("ja-voice-input", "認識結果が空でした")
                return

            text = self.post.process(raw)
            log.info("refined: %s", text)
            if not text:
                self.feedback.notify("ja-voice-input", "整形結果が空でした")
                return

            paste_text(text, self.cfg.paste)
            self.feedback.sound("done")
        except Exception:
            log.exception("session failed")
            self.feedback.sound("error")
            self.feedback.notify("ja-voice-input", "エラーが発生しました(ログ参照)")
        finally:
            self._recording = False
            self._session_lock.release()

    def process_once(self) -> str | None:
        """ホットキーなしで 1 回だけ実行(動作確認用)。整形済みテキストを返す。"""
        self.feedback.sound("start")
        audio = self.recorder.record()
        self.feedback.sound("stop")
        if audio is None:
            return None
        raw = self.stt.transcribe(audio, self.cfg.audio.sample_rate)
        log.info("raw: %s", raw)
        return self.post.process(raw)

    # --- 常駐 -----------------------------------------------------------

    def run(self) -> None:
        from pynput import keyboard  # macOS では入力監視権限が必要

        log.info("hotkey: %s で音声入力を開始します(Ctrl+C で終了)", self.cfg.hotkey)
        with keyboard.GlobalHotKeys({self.cfg.hotkey: self.on_hotkey}) as listener:
            listener.join()
