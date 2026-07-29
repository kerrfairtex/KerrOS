"""
tools/safe_math.py
==================
AST-based safe math expression evaluator.

Rejects attribute access, names (except allowlisted math constants/functions),
comprehensions, calls outside the whitelist, and any other non-arithmetic nodes.
"""

from __future__ import annotations

import ast
import math
import operator
from typing import Any, Callable

_BIN_OPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_ALLOWED_NAMES: dict[str, Any] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
    "nan": math.nan,
}

_ALLOWED_FUNCS: dict[str, Callable[..., Any]] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
    "pow": math.pow,
    "radians": math.radians,
    "degrees": math.degrees,
    "hypot": math.hypot,
    "factorial": math.factorial,
}


class SafeMathError(ValueError):
    pass


def _eval_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, complex)):
            return node.value
        raise SafeMathError(f"unsupported constant: {node.value!r}")

    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise SafeMathError(f"unsupported unary operator: {type(node.op).__name__}")
        return op(_eval_node(node.operand))

    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise SafeMathError(f"unsupported binary operator: {type(node.op).__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return op(left, right)

    if isinstance(node, ast.Name):
        if node.id in _ALLOWED_NAMES:
            return _ALLOWED_NAMES[node.id]
        if node.id in _ALLOWED_FUNCS:
            return _ALLOWED_FUNCS[node.id]
        raise SafeMathError(f"unknown name: {node.id}")

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise SafeMathError("only simple function calls are allowed")
        fn = _ALLOWED_FUNCS.get(node.func.id)
        if fn is None:
            raise SafeMathError(f"function not allowed: {node.func.id}")
        if node.keywords:
            raise SafeMathError("keyword arguments are not allowed")
        args = [_eval_node(a) for a in node.args]
        return fn(*args)

    raise SafeMathError(f"unsupported expression node: {type(node).__name__}")


def safe_eval(expression: str) -> Any:
    """Evaluate a math expression safely. Raises SafeMathError on rejection."""
    text = str(expression or "").strip()
    if not text:
        raise SafeMathError("empty expression")
    if len(text) > 500:
        raise SafeMathError("expression too long")

    # Support caret exponentiation used in chat ("2^8").
    text = text.replace("^", "**")

    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise SafeMathError(f"syntax error: {exc.msg}") from exc

    return _eval_node(tree)
