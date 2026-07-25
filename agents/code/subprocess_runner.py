"""
agents/code/subprocess_runner.py
================================
Isolated code-execution worker (KOS-012).

Reads JSON-line requests from stdin, runs code verification in this
process, writes JSON-line responses to stdout. A crash here does not
take down the parent Code Agent or chat session.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from runtime.ipc import decode_message, encode_response


def _handle(method: str, params: dict) -> object:
    if method == "ping":
        return {"pong": True}

    if method == "run_file":
        from tools.code_saver import run_and_verify

        path = params.get("path", "")
        if not path:
            raise ValueError("path is required")
        return run_and_verify(path)

    if method == "crash":
        # Test-only: simulate worker crash
        os._exit(1)

    raise ValueError(f"unknown method: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg_id = "unknown"
        try:
            msg = decode_message(line)
            msg_id = str(msg.get("id", "unknown"))
            method = str(msg.get("method", ""))
            params = msg.get("params") or {}
            if not isinstance(params, dict):
                raise ValueError("params must be an object")
            result = _handle(method, params)
            sys.stdout.write(encode_response(msg_id, True, result=result))
            sys.stdout.flush()
        except Exception as exc:
            sys.stdout.write(encode_response(msg_id, False, error=str(exc)))
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
