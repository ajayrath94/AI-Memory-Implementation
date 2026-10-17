"""The list-close handler from engine/tools.py, loaded on its own so the
offline tests do not import the whole tool module and its dependencies."""
import ast
import os

_src = open(os.path.join(os.path.dirname(__file__), "..", "engine", "tools.py")).read()
_fn = next(n for n in ast.parse(_src).body
           if isinstance(n, ast.FunctionDef) and n.name == "_handle_list_close")
_ns = {}
exec(compile(ast.Module(body=[_fn], type_ignores=[]), "tools", "exec"), _ns)


def close_tool(args, user_id="u"):
    return _ns["_handle_list_close"](args, user_id)
