#!/usr/bin/env python3
"""
Send voice note via Telegram Bot API.

Usage:
  telegram_send_voice.py <chat_id> <audio_file>

Audio: OGG/Opus preferred. WAV/MP3 auto-converted via ffmpeg.
Errors printed to stderr. Exit code 1 on failure.
"""

import os
import subprocess
import sys
import tempfile
import requests

BOT_TOKEN = "8724852419:AAGripcUsuVXv7JXGcF92qrAwgwslW188u0"


def validate_file(path: str) -> str:
    if not os.path.exists(path):
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    size = os.path.getsize(path)
    if size == 0:
        print(f"ERROR: File is empty: {path}", file=sys.stderr)
        sys.exit(1)
    if size > 50 * 1024 * 1024:  # 50MB Telegram limit
        print(f"ERROR: File too large ({size/1024/1024:.1f}MB > 50MB limit)", file=sys.stderr)
        sys.exit(1)
    return path


def to_ogg_opus(input_path: str) -> str:
    """Convert audio to OGG Opus if needed. Returns path to OGG file."""
    if input_path.endswith(".ogg"):
        return input_path

    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    tmp.close()

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path,
             "-c:a", "libopus", "-b:a", "16k", "-ar", "16000",
             tmp.name],
            capture_output=True, timeout=15, check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"ERROR: ffmpeg conversion failed: {e.stderr.decode()[-300:]}", file=sys.stderr)
        os.unlink(tmp.name)
        sys.exit(1)
    except FileNotFoundError:
        print("ERROR: ffmpeg not found. Install with: sudo apt install ffmpeg", file=sys.stderr)
        sys.exit(1)

    return tmp.name


def send_voice(chat_id: str, audio_path: str) -> None:
    """Send voice note to Telegram chat. Prints result to stderr."""
    ogg_path = to_ogg_opus(audio_path)

    try:
        with open(ogg_path, "rb") as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendVoice",
                data={"chat_id": chat_id},
                files={"voice": ("voice.ogg", f, "audio/ogg")},
                timeout=30,
            )
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            print("Voice note sent.", file=sys.stderr)
        else:
            print(f"ERROR: Telegram API error: {data.get('description', data)}", file=sys.stderr)
            sys.exit(1)
    except requests.RequestException as e:
        print(f"ERROR: Telegram request failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if ogg_path != audio_path:
            try:
                os.unlink(ogg_path)
            except OSError:
                pass


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    if len(sys.argv) != 3:
        print(f"ERROR: Expected <chat_id> <audio_file>, got {len(sys.argv)-1} args", file=sys.stderr)
        print(__doc__)
        sys.exit(1)

    chat_id = sys.argv[1]
    audio_path = validate_file(sys.argv[2])

    try:
        send_voice(chat_id, audio_path)
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
