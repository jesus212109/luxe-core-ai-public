#!/usr/bin/env python3
"""
Voice note transcription tool for Luxe.
Downloads a Telegram voice note via Bot API, transcribes with faster-whisper.
Auto-uses Whisper daemon if available (fast), falls back to direct model loading.

Usage:
  voice_transcribe.py <telegram_file_id>           # small model (precise)
  voice_transcribe.py --fast <telegram_file_id>    # tiny model (fast)
  voice_transcribe.py --local <path/to/audio.ogg>  # local file
  echo "file_id" | voice_transcribe.py

Output: transcribed text to stdout.  Errors: stderr.  Exit 1 on failure.
"""

import os
import socket
import sys
import tempfile
import requests
from faster_whisper import WhisperModel

# --- Config ---
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
if not BOT_TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN environment variable not set", file=sys.stderr)
    sys.exit(1)
MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models", "whisper")
DAEMON_SOCKET = "/tmp/whisper_daemon.sock"
SUPPORTED_FORMATS = (".ogg", ".mp3", ".wav", ".m4a", ".flac", ".opus")


def parse_args() -> dict:
    args = sys.argv[1:]
    flags = {"fast": False, "local": False, "input": None}
    i = 0
    while i < len(args):
        if args[i] == "--fast":
            flags["fast"] = True
        elif args[i] == "--local":
            flags["local"] = True
        elif args[i] in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        elif not args[i].startswith("-"):
            flags["input"] = args[i]
        i += 1
    return flags


def get_input(flags: dict) -> str:
    if flags["input"]:
        return flags["input"]
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    print("ERROR: No input provided.", file=sys.stderr)
    sys.exit(1)


def download_voice(file_id: str) -> str:
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
            params={"file_id": file_id}, timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR: Telegram API: {e}", file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    if not data.get("ok"):
        print(f"ERROR: Telegram: {data.get('description', data)}", file=sys.stderr)
        sys.exit(1)

    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{data['result']['file_path']}"
    try:
        audio_resp = requests.get(file_url, timeout=30)
        audio_resp.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR: Download failed: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
        tmp.write(audio_resp.content)
        tmp.close()
    except OSError as e:
        print(f"ERROR: Cannot save: {e}", file=sys.stderr)
        sys.exit(1)
    return tmp.name


def validate_local_file(path: str) -> str:
    if not os.path.exists(path):
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    return path


def transcribe_via_daemon(audio_path: str, fast: bool) -> str | None:
    """Try daemon transcription. Returns None if daemon unavailable."""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(30)
        sock.connect(DAEMON_SOCKET)
    except (socket.error, FileNotFoundError):
        return None

    try:
        model_size = "tiny" if fast else "small"
        sock.sendall(f"{model_size}|{audio_path}\n".encode())
        data = b""
        while b"\n" not in data:
            data += sock.recv(4096)
        result = data.decode().strip()
        if result.startswith("ERROR:"):
            print(f"Daemon error: {result}", file=sys.stderr)
            return None
        return result
    except Exception as e:
        print(f"Daemon connection lost: {e}", file=sys.stderr)
        return None
    finally:
        sock.close()


def transcribe_direct(audio_path: str, fast: bool) -> str:
    """Direct transcription loading model from disk."""
    model_size = "tiny" if fast else "small"
    download_root = os.path.dirname(MODEL_DIR)

    if not os.path.isdir(MODEL_DIR):
        print(f"ERROR: No models at {MODEL_DIR}", file=sys.stderr)
        sys.exit(1)

    try:
        model = WhisperModel(model_size, device="cpu", compute_type="int8",
                             download_root=download_root)
        segments, info = model.transcribe(audio_path, language=None, vad_filter=True)
        return " ".join(seg.text.strip() for seg in segments)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def transcribe(audio_path: str, fast: bool) -> str:
    """Transcribe using daemon if available, else direct."""
    result = transcribe_via_daemon(audio_path, fast)
    if result is not None:
        return result
    # Fallback to direct
    return transcribe_direct(audio_path, fast)


def main():
    try:
        flags = parse_args()
        input_val = get_input(flags)

        if flags["local"]:
            audio_path = validate_local_file(input_val)
            cleanup = False
        else:
            print("Downloading audio...", file=sys.stderr)
            audio_path = download_voice(input_val)
            cleanup = True

        model = "tiny" if flags["fast"] else "small"
        print(f"Transcribing ({model})...", file=sys.stderr)
        text = transcribe(audio_path, fast=flags["fast"])
        print(text)

        if cleanup:
            try:
                os.unlink(audio_path)
            except OSError:
                pass
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
