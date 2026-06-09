#!/usr/bin/env python3
"""
Text-to-speech via Piper TTS (Spanish voice, sharvard-medium).
Reads text from stdin or argv, outputs WAV or OGG to stdout or file.

Usage:
  echo "Hola" | voice_synthesize.py                          → WAV to stdout
  voice_synthesize.py "texto"                                → WAV to stdout
  voice_synthesize.py -o /tmp/voz.wav "texto"                → WAV to file
  voice_synthesize.py --format ogg -o /tmp/voz.ogg "texto"   → OGG to file (direct)
"""

import os
import struct
import subprocess
import sys
import tempfile
import wave

MODEL_FILE = "es_ES-sharvard-medium.onnx"
MODEL = os.path.join(os.path.dirname(__file__), "..", "models", "piper", MODEL_FILE)
PIPER_BIN = os.path.join(os.path.dirname(__file__), "..", "venv", "bin", "piper")


def parse_args() -> dict:
    """Parse flags and positional text from argv."""
    flags = {"format": "wav", "output": None}
    positional = []
    skip_next = False
    for a in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if a in ("-o", "--format"):
            skip_next = True
            continue
        if not a.startswith("-"):
            positional.append(a)
    text = " ".join(positional) if positional else sys.stdin.read().strip()
    if not text:
        print("ERROR: No text provided", file=sys.stderr)
        sys.exit(1)

    # Re-parse for flags (separate from positional parsing)
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--format" and i + 1 < len(args):
            flags["format"] = args[i + 1]
        elif a == "-o" and i + 1 < len(args):
            flags["output"] = args[i + 1]

    flags["text"] = text
    return flags


def piper_synthesize(text: str) -> bytes:
    """Run Piper TTS, return raw PCM audio (16-bit, 22050Hz, mono)."""
    if not os.path.exists(PIPER_BIN):
        print("ERROR: piper not found at " + PIPER_BIN, file=sys.stderr)
        sys.exit(1)

    proc = subprocess.run(
        [PIPER_BIN, "--model", MODEL, "--output-raw"],
        input=text.encode("utf-8"),
        capture_output=True,
        timeout=60,
    )
    if proc.returncode != 0:
        print("Piper error: " + proc.stderr.decode(), file=sys.stderr)
        sys.exit(1)
    return proc.stdout


def raw_to_wav(raw_audio: bytes) -> bytes:
    """Wrap raw PCM in WAV header."""
    tmp_path = tempfile.mktemp(suffix=".wav")
    with wave.open(tmp_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(22050)
        wf.writeframes(raw_audio)
    with open(tmp_path, "rb") as f:
        wav_data = f.read()
    os.unlink(tmp_path)
    return wav_data


def raw_to_ogg(raw_audio: bytes) -> bytes:
    """Convert raw PCM (22050Hz, s16, mono) to OGG Opus via ffmpeg pipe."""
    proc = subprocess.run(
        ["ffmpeg", "-y",
         "-f", "s16le", "-ar", "22050", "-ac", "1",
         "-i", "pipe:0",
         "-c:a", "libopus", "-b:a", "16k", "-ar", "16000",
         "-f", "ogg", "pipe:1"],
        input=raw_audio,
        capture_output=True,
        timeout=30,
    )
    if proc.returncode != 0:
        print("ffmpeg error: " + proc.stderr.decode()[-200:], file=sys.stderr)
        sys.exit(1)
    return proc.stdout


def main():
    flags = parse_args()

    raw_audio = piper_synthesize(flags["text"])

    if flags["format"] == "ogg":
        output_data = raw_to_ogg(raw_audio)
    else:
        output_data = raw_to_wav(raw_audio)

    if flags["output"]:
        with open(flags["output"], "wb") as f:
            f.write(output_data)
    else:
        sys.stdout.buffer.write(output_data)


if __name__ == "__main__":
    main()
