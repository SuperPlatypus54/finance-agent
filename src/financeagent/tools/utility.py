"""General-purpose tools: sandboxed file access, safe arithmetic, web search, time, python exec."""

import ast
import contextlib
import io
import operator
from datetime import datetime
from pathlib import Path

from ..config import SANDBOX_DIR, get_tavily_client


def _resolve_safe_path(filename: str) -> Path:
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    candidate = (SANDBOX_DIR / filename).resolve()
    if not candidate.is_relative_to(SANDBOX_DIR):
        raise ValueError(f"Access denied: '{filename}' resolves outside the sandbox directory")
    return candidate


def read_file(filename: str) -> str:
    try:
        path = _resolve_safe_path(filename)
        if not path.exists():
            return f"Error: {filename} not found"
        if path.is_dir():
            return f"Error: {filename} is a directory, not a file"
        return path.read_text()
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: could not read {filename} ({e})"


def write_file(filename: str, content: str, overwrite: bool = False) -> str:
    try:
        path = _resolve_safe_path(filename)
        if path.exists() and not overwrite:
            return f"Error: {filename} already exists. Pass overwrite=true if you intend to replace it."
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return f"Wrote {len(content)} characters to {filename}"
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: could not write {filename} ({e})"


def list_files(directory: str = ".") -> str:
    try:
        path = _resolve_safe_path(directory)
        if not path.exists():
            return f"Error: {directory} not found"
        if not path.is_dir():
            return f"Error: {directory} is a file, not a directory"
        names = sorted(p.name for p in path.iterdir())
        return str(names) if names else "Directory is empty"
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: could not list {directory} ({e})"


_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}


def _safe_eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_safe_eval(node.operand)
    raise ValueError(f"Disallowed expression: {ast.dump(node)}")


def calculate(expression: str) -> str:
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree.body)
        return str(result)
    except ZeroDivisionError:
        return "Error: division by zero"
    except Exception as e:
        return f"Error: could not evaluate expression ({e})"


def web_search(query: str, max_results: int = 3) -> str:
    response = get_tavily_client().search(query, max_results=max_results, include_answer=True)

    lines = [f"Answer summary: {response['answer']}", ""]
    for result in response["results"]:
        lines.append(f"- {result['title']} ({result['url']}): {result['content'][:200]}")

    return "\n".join(lines)


def current_time() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def execute_python(code: str) -> str:
    # exec() with captured stdout is NOT a real sandbox -- this code can still
    # read/write the filesystem, use the network, etc. Run the API in a container
    # if this tool stays enabled in production.
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            exec(code, {"__builtins__": __builtins__})
    except Exception as e:
        return f"Error: {e}"
    return output.getvalue() or "(no output)"
