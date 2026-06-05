#!/usr/bin/env python3
"""
Whisper daemon — keeps models loaded in memory for fast transcription.
Listens on UNIX socket. Auto-terminates after inactivity.

Usage:
  whisper_daemon.py                     # default: /tmp/whisper_daemon.sock
  whisper_daemon.py --socket /path/sock  # custom socket path

Protocol (over UNIX socket, text-based):
  REQUEST:  "small|/path/to/audio.ogg\n"
  REQUEST:  "tiny|/path/to/audio.ogg\n"
  RESPONSE: "transcribed text\n"  or  "ERROR: message\n"
  SHUTDOWN: "EXIT\n"  → daemon terminates
  PING:     "PING\n"  → "PONG\n"

Idle timeout: 300s (5 min). Daemon exits automatically.
"""

import os
import signal
import socket
import sys
import time
from faster_whisper import WhisperModel

# --- Config ---
DEFAULT_SOCKET = "/tmp/whisper_daemon.sock"
MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models", "whisper")
IDLE_TIMEOUT = 300  # 5 minutes


class WhisperDaemon:
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self.models = {}
        self.last_activity = time.time()
        self.running = True

    def get_model(self, size: str) -> WhisperModel:
        if size not in self.models:
            download_root = os.path.dirname(MODEL_DIR)
            self.models[size] = WhisperModel(
                size, device="cpu", compute_type="int8",
                download_root=download_root,
            )
        return self.models[size]

    def transcribe(self, model_size: str, audio_path: str) -> str:
        if model_size not in ("small", "tiny"):
            return f"ERROR: Unknown model '{model_size}'. Use 'small' or 'tiny'."

        if not os.path.exists(audio_path):
            return f"ERROR: File not found: {audio_path}"

        try:
            model = self.get_model(model_size)
            segments, info = model.transcribe(audio_path, language=None, vad_filter=True)
            results = [seg.text.strip() for seg in segments]
            return " ".join(results)
        except Exception as e:
            return f"ERROR: {e}"

    def handle_client(self, conn: socket.socket) -> None:
        try:
            data = b""
            while b"\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                data += chunk
            msg = data.decode("utf-8").strip()

            if msg == "PING":
                conn.sendall(b"PONG\n")
            elif msg == "EXIT":
                conn.sendall(b"BYE\n")
                self.running = False
            elif "|" in msg:
                model_size, audio_path = msg.split("|", 1)
                result = self.transcribe(model_size, audio_path)
                conn.sendall((result + "\n").encode("utf-8"))
            else:
                conn.sendall(b"ERROR: Invalid request format. Use 'model|path' or 'PING' or 'EXIT'\n")
        except Exception as e:
            try:
                conn.sendall(f"ERROR: {e}\n".encode("utf-8"))
            except Exception:
                pass
        finally:
            self.last_activity = time.time()

    def run(self):
        # Remove stale socket
        try:
            os.unlink(self.socket_path)
        except OSError:
            pass

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self.socket_path)
        server.listen(1)
        server.settimeout(1.0)  # Check idle timeout every second
        os.chmod(self.socket_path, 0o600)

        print(f"Whisper daemon ready on {self.socket_path}", file=sys.stderr, flush=True)

        try:
            while self.running:
                # Check idle timeout
                if time.time() - self.last_activity > IDLE_TIMEOUT:
                    print("Idle timeout reached. Shutting down.", file=sys.stderr)
                    break

                try:
                    conn, _ = server.accept()
                    self.handle_client(conn)
                    conn.close()
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Connection error: {e}", file=sys.stderr)
        finally:
            server.close()
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass
            print("Daemon stopped.", file=sys.stderr)


def main():
    socket_path = DEFAULT_SOCKET
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--socket" and i + 1 < len(args):
            socket_path = args[i + 1]
            i += 2
        elif args[i] in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        else:
            i += 1

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    daemon = WhisperDaemon(socket_path)
    daemon.run()


if __name__ == "__main__":
    main()
