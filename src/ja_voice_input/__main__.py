"""CLI エントリポイント。

    ja-voice-input            # 常駐(ホットキー待ち)
    ja-voice-input once       # 1 回だけ録音 → 認識 → 整形して表示
    ja-voice-input doctor     # 環境チェック
"""
from __future__ import annotations

import argparse
import logging
import sys

from .config import ConfigError, load_config


def cmd_run(args) -> int:
    from .app import App

    App(load_config(args.config)).run()
    return 0


def cmd_once(args) -> int:
    from .app import App
    from .paste import FocusTarget, PasteResult, paste_text

    app = App(load_config(args.config))
    target = (
        FocusTarget.capture()
        if args.paste
        and app.cfg.paste.method == "keystroke"
        and app.cfg.paste.cancel_on_focus_change
        else None
    )
    print("録音中... 話し終えて無音になると自動で止まります", file=sys.stderr)
    text = app.process_once()
    if text is None:
        print("音声が検出されませんでした", file=sys.stderr)
        return 1
    print(text)
    if args.paste:
        result = paste_text(text, app.cfg.paste, target)
        if result is PasteResult.TARGET_CHANGED:
            print("入力先が変わったため貼り付けを中止しました", file=sys.stderr)
    return 0


def cmd_doctor(args) -> int:
    import requests

    cfg = load_config(args.config)
    ok = True

    def check(label: str, passed: bool, hint: str = "") -> None:
        nonlocal ok
        mark = "✅" if passed else "❌"
        print(f"{mark} {label}" + (f" — {hint}" if hint and not passed else ""))
        ok = ok and passed

    # 音声入力デバイス
    try:
        import sounddevice as sd

        devices = [d for d in sd.query_devices() if d["max_input_channels"] > 0]
        check(f"マイク入力デバイス ({len(devices)} 件)", bool(devices),
              "マイクが見つかりません")
    except Exception as e:
        check("sounddevice", False, str(e))

    # VAD
    from .vad import VoiceDetector

    det = VoiceDetector(cfg.audio.sample_rate, cfg.audio.vad_aggressiveness)
    check(f"VAD backend: {det.backend}", True)
    if det.backend == "rms":
        print("   (webrtcvad-wheels を入れると無音検出の精度が上がります)")

    # STT バックエンド
    try:
        if cfg.stt.backend == "whispercpp":
            import pywhispercpp  # noqa: F401
        elif cfg.stt.backend == "mlx":
            import mlx_whisper  # noqa: F401
        check(f"STT backend: {cfg.stt.backend} (model: {cfg.stt.model})", True)
    except ImportError as e:
        extra = "whispercpp" if cfg.stt.backend == "whispercpp" else "mlx"
        check(f"STT backend: {cfg.stt.backend}", False,
              f"uv sync --extra {extra} が必要です ({e})")

    # Ollama
    if cfg.llm.enabled:
        try:
            resp = requests.get(f"{cfg.llm.base_url.rstrip('/')}/api/tags", timeout=3)
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            has_model = any(m == cfg.llm.model or m.startswith(cfg.llm.model + ":")
                            for m in models)
            check(f"Ollama 接続 ({cfg.llm.base_url})", True)
            check(f"Ollama モデル: {cfg.llm.model}", has_model,
                  f"ollama pull {cfg.llm.model} を実行してください")
        except Exception as e:
            check("Ollama 接続", False, f"ollama serve が起動していますか? ({e})")
    else:
        print("ℹ️  LLM 整形は無効(llm.enabled: false)")

    # 辞書
    from .dictionary import Dictionary

    d = Dictionary.load(cfg.dictionary_path)
    print(f"ℹ️  用語辞書: {len(d.terms)} 語 ({cfg.dictionary_path})")

    print()
    print("macOS の権限(手動で確認):")
    print(" - マイク: 初回録音時にダイアログが出ます")
    print(" - アクセシビリティ: Cmd+V 送出に必要(システム設定 > プライバシーとセキュリティ)")
    print(" - 入力監視: グローバルホットキーに必要")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ja-voice-input",
                                     description="ローカル日本語音声入力 (macOS)")
    parser.add_argument("-c", "--config", help="設定ファイルのパス")
    parser.add_argument("-v", "--verbose", action="store_true", help="デバッグログ")
    sub = parser.add_subparsers(dest="command")
    once = sub.add_parser("once", help="1 回だけ実行して結果を表示")
    once.add_argument("--paste", action="store_true", help="結果を貼り付けまで行う")
    sub.add_parser("doctor", help="環境チェック")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        if args.command == "once":
            return cmd_once(args)
        if args.command == "doctor":
            return cmd_doctor(args)
        return cmd_run(args)
    except KeyboardInterrupt:
        return 130
    except ConfigError as e:
        print(f"設定エラー: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
