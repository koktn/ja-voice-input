# ja-voice-input

macOS でローカル動作する日本語音声入力ツール。coding agent(Claude Code など)への音声指示を想定。

```
ホットキー → 録音(無音で自動終了) → 音声認識(whisper) → ローカルLLMで整形 → アクティブな入力欄に貼り付け
```

- **完全ローカル**: 音声認識は whisper.cpp / mlx-whisper、整形は Ollama。ネットワークに音声もテキストも出ない
- **フィラー除去・用語補正**: 「えーと」「あのー」を除去し、専門用語辞書で「クロードコード → Claude Code」のような表記統一を行う
- **辞書は二段構え**: 決定論的な文字列置換 + LLM プロンプトへの注入。LLM が落ちていても辞書変換は効く

## セットアップ

### 1. 依存のインストール

```bash
brew install portaudio uv   # portaudio は sounddevice が使う
git clone https://github.com/koktn/ja-voice-input.git
cd ja-voice-input

# Apple Silicon(推奨: 高速)
uv sync --extra mlx --extra vad

# Intel Mac / 汎用
uv sync --extra whispercpp --extra vad
```

`uv sync` が Python の用意から仮想環境の作成・依存のインストールまで行います。以降のコマンドは `uv run` 経由で実行します(venv の activate は不要)。Python のバージョンは `.python-version`(3.12)で固定してあり、未導入の場合は `uv` が自動でインストールします。

### 2. Ollama の準備

```bash
brew install ollama
ollama serve &          # 常駐させる場合は brew services start ollama
ollama pull gemma4:e4b  # 軽量で日本語に強い(実効4B)。qwen2.5:3b なども可
```

### 3. 設定と辞書

```bash
mkdir -p ~/.config/ja-voice-input
cp config.example.yaml ~/.config/ja-voice-input/config.yaml
cp dict/terms.example.yaml ~/.config/ja-voice-input/terms.yaml
```

Apple Silicon なら `config.yaml` の STT を mlx にするのがおすすめ:

```yaml
stt:
  backend: mlx
  model: turbo   # whisper-large-v3-turbo。初回にモデルをダウンロード
```

### 4. macOS の権限

初回実行時にターミナル(iTerm2 等)へ以下を許可する:

| 権限 | 用途 | 場所 |
|---|---|---|
| マイク | 録音 | 初回録音時にダイアログ |
| 入力監視 | グローバルホットキー | システム設定 > プライバシーとセキュリティ |
| アクセシビリティ | Cmd+V の自動送出 | 同上 |

### 5. 動作確認

```bash
uv run ja-voice-input doctor   # 環境チェック
uv run ja-voice-input once     # 1回だけ録音→認識→整形して表示
```

## 使い方

```bash
uv run ja-voice-input          # 常駐開始
```

1. ターミナルなどテキスト入力欄にカーソルを置く
2. `Ctrl+Option+Space`(変更可)を押す → ポン♪ と鳴ったら話す
3. 話し終えて約 1.2 秒無音になると自動で認識・整形され、カーソル位置に貼り付けられる
4. 長考したいときは録音中にもう一度ホットキーを押すと即座に打ち切って変換に進む

ログイン時に自動起動したい場合は `launchd` か「ログイン項目」に登録してください。

## 用語辞書

`~/.config/ja-voice-input/terms.yaml` に社内用語・プロジェクト用語を追加:

```yaml
terms:
  - surface: "Claude Code"              # 正しい表記
    readings: ["クロードコード"]         # 音声認識が出しがちな表記(決定論的に置換)
    notes: "AI コーディングエージェント"  # LLM への補足(任意)
```

辞書の用語は whisper の `initial_prompt` にも自動注入され、認識段階の精度も上がります。

## パフォーマンスの目安

| 構成 | 5秒の発話の処理時間の目安 |
|---|---|
| mlx + turbo + gemma4:e4b (M2 以降) | 1〜2 秒 |
| whispercpp small + gemma4:e4b | 2〜4 秒 |

さらに速くしたい場合: `stt.model: base`、`llm.model: qwen2.5:1.5b`、または `llm.enabled: false`(辞書置換+簡易フィラー除去のみ)。なお `gemma4:e2b` はほぼ英語専用のため日本語整形には不向きです。

## 開発

```bash
uv sync --extra dev
uv run pytest
```

音声・macOS 依存を切り離してあるため、ロジック部分(VAD 状態機械・辞書・整形・設定)のテストはどの OS でも走ります。

## アーキテクチャ

```
src/ja_voice_input/
├── app.py          # パイプラインの配線とホットキー常駐
├── recorder.py     # sounddevice 録音 + 無音検出ループ
├── vad.py          # webrtcvad / RMS フォールバック + SilenceTracker 状態機械
├── stt/            # whispercpp / mlx バックエンド(差し替え可能)
├── postprocess.py  # Ollama でフィラー除去・整形(失敗時は正規表現フォールバック)
├── dictionary.py   # 用語辞書(置換 + プロンプト生成 + STT ヒント)
├── paste.py        # pbcopy + osascript Cmd+V(クリップボード復元付き)
└── feedback.py     # 効果音・通知
```
