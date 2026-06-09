#!/usr/bin/env python3
"""
CLI tool para el Model Router.

Uso:
  model_router.py <mensaje>
  model_router.py --session <id> <mensaje>
  model_router.py --force-reasoning <mensaje>
  model_router.py --status
  model_router.py --reset [--session <id>]

Ejemplos:
  model_router.py "enciende la luz del salón"
  model_router.py --force-reasoning "analiza el consumo energético"
  model_router.py --status
"""

import argparse
import json
import sys
import urllib.request
import urllib.error

ROUTER_URL = "http://127.0.0.1:18790"


def _request(method: str, path: str, body: dict = None) -> dict:
    """Hace una petición HTTP al Model Router."""
    url = f"{ROUTER_URL}{path}"
    data = json.dumps(body).encode() if body else None

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"}
        if data else {},
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"Error {e.code}: {err}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error de conexión: ¿el Model Router está corriendo? "
              f"({e.reason})", file=sys.stderr)
        sys.exit(1)


def cmd_chat(args):
    """Envía un mensaje al router."""
    result = _request("POST", "/chat", {
        "message": args.message,
        "session_id": args.session,
        "force_model": "reasoning" if args.force_reasoning else "",
    })

    print(result["response"])
    if args.verbose:
        print(file=sys.stderr)
        print(f"[modelo: {result['model_label']}] "
              f"[intención: {result['intent']['intent']}] "
              f"[latencia: {result['latency_ms']}ms]",
              file=sys.stderr)


def cmd_status(_):
    """Muestra el estado del router."""
    result = _request("GET", "/status")
    print(f"Model Router: {result['status']}")
    print(f"Sesiones activas: {result['sessions_active']}")
    print(f"Uptime: {result['uptime_sec']}s")
    print()
    for key, model in result['models'].items():
        status = "✅" if model["loaded"] else "⬜"
        idle = f" (idle: {model.get('idle_sec', '-')}s)" if model.get("idle_sec") is not None else ""
        print(f"  {status} {key:12s} {model['name']}{idle}")
        print(f"     Rol: {model['role']}")


def cmd_reset(args):
    """Resetea el contexto de una sesión."""
    result = _request("POST", "/reset", {
        "session_id": args.session,
    })
    print(f"Sesión '{result['session_id']}' reseteada.")


def main():
    parser = argparse.ArgumentParser(
        description="Model Router — Interfaz CLI",
    )
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Muestra info de depuración")

    sub = parser.add_subparsers(dest="command")

    # chat
    chat_p = sub.add_parser("chat", help="Envía un mensaje")
    chat_p.add_argument("message", help="Texto del mensaje")
    chat_p.add_argument("--session", default="default",
                        help="ID de sesión")
    chat_p.add_argument("--force-reasoning", "-r", action="store_true",
                        help="Forzar uso del modelo de razonamiento")

    # status
    sub.add_parser("status", help="Estado del router")

    # reset
    reset_p = sub.add_parser("reset", help="Resetea contexto de sesión")
    reset_p.add_argument("--session", default="default",
                         help="ID de sesión")

    args = parser.parse_args()

    if args.command == "chat":
        cmd_chat(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "reset":
        cmd_reset(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
