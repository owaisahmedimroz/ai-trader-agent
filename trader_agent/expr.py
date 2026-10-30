"""Safe, vectorised evaluator for KSoR rule conditions.

Conditions are small expressions over feature names, for example::

    rsi_14 < 30 and low <= pdl + 0.5 * atr_14
    m15_trend == 'up'
    20 < adx_14 < 40
    regime in ['range', 'mixed']
    abs(close - ema_50) < 0.3 * atr_14

They are parsed with `ast` and evaluated against a whole feature DataFrame at
once (fast backtests); the live loop evaluates the same code on its latest row.
Nothing is ever passed to `eval`.
"""

from __future__ import annotations

import ast
import difflib
import operator
from functools import reduce

import numpy as np
import pandas as pd


class ExprError(ValueError):
    """A condition that cannot be parsed or uses something not allowed."""


_BIN_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_CMP_OPS = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}
_FUNCTIONS = {"abs", "min", "max"}
_TRUE, _FALSE = {"True", "true"}, {"False", "false"}


def parse(expr: str) -> ast.Expression:
    if not isinstance(expr, str) or not expr.strip():
        raise ExprError("condition must be a non-empty string")
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExprError(f"cannot read condition {expr!r}: {exc.msg}") from None
    _check(tree.body, expr)
    return tree


def _check(node: ast.AST, expr: str) -> None:
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float, str, bool)):
            raise ExprError(f"unsupported value {node.value!r} in {expr!r}")
    elif isinstance(node, ast.Name):
        pass
    elif isinstance(node, ast.BinOp):
        if type(node.op) not in _BIN_OPS:
            raise ExprError(f"only + - * / are allowed in {expr!r}")
        _check(node.left, expr)
        _check(node.right, expr)
    elif isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.Not, ast.USub, ast.UAdd)):
            raise ExprError(f"unsupported operator in {expr!r}")
        _check(node.operand, expr)
    elif isinstance(node, ast.BoolOp):
        for value in node.values:
            _check(value, expr)
    elif isinstance(node, ast.Compare):
        _check(node.left, expr)
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, (ast.In, ast.NotIn)):
                if not isinstance(comparator, (ast.List, ast.Tuple)):
                    raise ExprError(f"'in' needs a list like ['a', 'b'] in {expr!r}")
            elif type(op) not in _CMP_OPS:
                raise ExprError(f"unsupported comparison in {expr!r}")
            _check(comparator, expr)
    elif isinstance(node, (ast.List, ast.Tuple)):
        for element in node.elts:
            if not isinstance(element, ast.Constant):
                raise ExprError(f"lists may only contain plain values in {expr!r}")
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS or node.keywords:
            raise ExprError(f"only abs(), min(), max() can be called in {expr!r}")
        if node.func.id == "abs" and len(node.args) != 1:
            raise ExprError(f"abs() takes one value in {expr!r}")
        if node.func.id in ("min", "max") and len(node.args) < 2:
            raise ExprError(f"{node.func.id}() needs at least two values in {expr!r}")
        for arg in node.args:
            _check(arg, expr)
    else:
        raise ExprError(f"{type(node).__name__} is not allowed in {expr!r}")


def names(expr: str | ast.Expression) -> set[str]:
    """Feature names a condition refers to."""
    tree = parse(expr) if isinstance(expr, str) else expr
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in _TRUE | _FALSE | _FUNCTIONS:
            found.add(node.id)
    return found


def _unknown_feature(name: str, known, expr: str | None = None) -> ExprError:
    hint = difflib.get_close_matches(name, [str(k) for k in known], n=3)
    where = f" in {expr!r}" if expr else ""
    suggestion = f" — did you mean {', '.join(hint)}?" if hint else ""
    return ExprError(f"unknown feature {name!r}{where}{suggestion}")


def check_names(expr: str, known: set[str] | list[str]) -> None:
    known = set(known)
    for name in sorted(names(expr)):
        if name not in known:
            raise _unknown_feature(name, known, expr)


def as_bool(value, index: pd.Index) -> pd.Series:
    if isinstance(value, pd.Series):
        if value.dtype == bool:
            return value
        return value.fillna(False).astype(bool)
    return pd.Series(bool(value), index=index)


def evaluate(expr: str | ast.Expression, df: pd.DataFrame):
    """Evaluate a condition on every row of `df`. Returns a Series (or a scalar)."""
    tree = parse(expr) if isinstance(expr, str) else expr
    return _eval(tree.body, df)


def evaluate_bool(expr: str | ast.Expression, df: pd.DataFrame) -> pd.Series:
    return as_bool(evaluate(expr, df), df.index)


def _eval(node: ast.AST, df: pd.DataFrame):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in _TRUE:
            return True
        if node.id in _FALSE:
            return False
        if node.id not in df.columns:
            raise _unknown_feature(node.id, df.columns)
        return df[node.id]
    if isinstance(node, ast.BinOp):
        return _BIN_OPS[type(node.op)](_eval(node.left, df), _eval(node.right, df))
    if isinstance(node, ast.UnaryOp):
        operand = _eval(node.operand, df)
        if isinstance(node.op, ast.Not):
            return ~as_bool(operand, df.index)
        return -operand if isinstance(node.op, ast.USub) else +operand
    if isinstance(node, ast.BoolOp):
        parts = [as_bool(_eval(v, df), df.index) for v in node.values]
        combine = operator.and_ if isinstance(node.op, ast.And) else operator.or_
        return reduce(combine, parts)
    if isinstance(node, ast.Compare):
        result = pd.Series(True, index=df.index)
        left = _eval(node.left, df)
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, (ast.In, ast.NotIn)):
                options = [element.value for element in comparator.elts]
                series = left if isinstance(left, pd.Series) else pd.Series(left, index=df.index)
                part = series.isin(options)
                if isinstance(op, ast.NotIn):
                    part = ~part
                right = options
            else:
                right = _eval(comparator, df)
                part = _CMP_OPS[type(op)](left, right)
            result = result & as_bool(part, df.index)
            left = right
        return result
    if isinstance(node, (ast.List, ast.Tuple)):
        return [element.value for element in node.elts]
    if isinstance(node, ast.Call):
        args = [_eval(arg, df) for arg in node.args]
        if node.func.id == "abs":
            return abs(args[0])
        pick = np.minimum if node.func.id == "min" else np.maximum
        return reduce(pick, args)
    raise ExprError(f"{type(node).__name__} is not allowed")
