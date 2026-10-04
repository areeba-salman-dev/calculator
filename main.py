import ast
import html
import math
import operator

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Scientific Calculator",
    page_icon="🧮",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ============================================================
# SAFE CALCULATOR ENGINE (all math is done here, in Python)
# ============================================================

BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

MAX_POWER = 10_000


def build_functions(angle_mode: str) -> dict:
    deg = angle_mode == "Deg"

    def trig(fn):
        return (lambda x: fn(math.radians(x))) if deg else fn

    def inv_trig(fn):
        return (lambda x: math.degrees(fn(x))) if deg else fn

    return {
        "sin": trig(math.sin),
        "cos": trig(math.cos),
        "tan": trig(math.tan),
        "asin": inv_trig(math.asin),
        "acos": inv_trig(math.acos),
        "atan": inv_trig(math.atan),
        "sqrt": math.sqrt,
        "ln": math.log,
        "log": math.log10,
        "abs": abs,
    }


CONSTANTS = {"pi": math.pi, "e": math.e}


def normalise(expression: str) -> str:
    expression = (
        expression.replace("×", "*")
        .replace("÷", "/")
        .replace("−", "-")
        .replace("π", "pi")
        .replace("^", "**")
    )
    # auto-close any parentheses the user left open
    missing = expression.count("(") - expression.count(")")
    if missing > 0:
        expression += ")" * missing
    return expression


def safe_eval(expression: str, angle_mode: str) -> float:
    expression = normalise(expression.strip())
    if not expression:
        return 0.0

    functions = build_functions(angle_mode)

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Name) and node.id in CONSTANTS:
            return CONSTANTS[node.id]
        if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPS:
            return UNARY_OPS[type(node.op)](visit(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in BINARY_OPS:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > MAX_POWER:
                raise ValueError("Exponent too large")
            return BINARY_OPS[type(node.op)](left, right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn = functions.get(node.func.id)
            if fn is None or len(node.args) != 1 or node.keywords:
                raise ValueError("Invalid function")
            return fn(visit(node.args[0]))
        raise ValueError("Invalid expression")

    result = visit(ast.parse(expression, mode="eval"))
    if isinstance(result, complex):
        raise ValueError("Complex result")
    result = float(result)
    if not math.isfinite(result):
        raise ValueError("Math error")
    return result


def format_number(value: float) -> str:
    value = float(value)
    if abs(value) < 1e-12:
        value = 0.0
    if value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.12g}"


# ============================================================
# SESSION STATE
# ============================================================

ss = st.session_state
ss.setdefault("expression", "")
ss.setdefault("history", "")  # the expression of the last "="
ss.setdefault("error", False)
ss.setdefault("angle_mode", "Rad")
ss.setdefault("inverse", False)
ss.setdefault("just_calculated", False)

OPERATORS = "+−×÷^%"


def _fresh_start(next_value: str):
    """After '=' or an error, typing a number starts over; an operator continues."""
    if ss.error:
        ss.expression = ""
        ss.error = False
    elif ss.just_calculated and next_value not in OPERATORS:
        ss.expression = ""
    ss.just_calculated = False


def append(value: str):
    _fresh_start(value)
    expr = ss.expression
    # replace a trailing operator instead of stacking two
    if value in "+×÷^" and expr and expr[-1] in "+−×÷^":
        expr = expr[:-1]
    ss.expression = expr + value


def calculate():
    if not ss.expression.strip():
        return
    try:
        result = format_number(safe_eval(ss.expression, ss.angle_mode))
        ss.history = ss.expression
        ss.expression = result
        ss.error = False
    except Exception:
        ss.history = ss.expression
        ss.error = True
    ss.just_calculated = True


def clear():
    ss.expression = ""
    ss.history = ""
    ss.error = False
    ss.just_calculated = False


def backspace():
    if ss.error:
        clear()
        return
    ss.expression = ss.expression[:-1]
    ss.just_calculated = False


def transform(fn):
    """Evaluate the current expression, apply fn to it, show the result."""
    if ss.error:
        clear()
    try:
        value = safe_eval(ss.expression or "0", ss.angle_mode)
        ss.history = f"{ss.expression or '0'}"
        ss.expression = format_number(fn(value))
        ss.just_calculated = True
    except Exception:
        ss.error = True


def percent():
    transform(lambda v: v / 100)


def reciprocal():
    transform(lambda v: 1 / v)


def square():
    transform(lambda v: v**2)


def change_sign():
    if ss.error:
        return
    expr = ss.expression
    if not expr:
        ss.expression = "−"
    elif expr.startswith("−(") and expr.endswith(")"):
        ss.expression = expr[2:-1]
    elif expr.startswith("−"):
        ss.expression = expr[1:]
    else:
        ss.expression = "−(" + expr + ")" if not _is_number(expr) else "−" + expr
    ss.just_calculated = False


def _is_number(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def function(name: str):
    """Insert `name(`; after '=' wrap the previous result like a phone calculator."""
    if ss.error:
        clear()
    if ss.just_calculated and ss.expression:
        ss.expression = f"{name}({ss.expression})"
        ss.just_calculated = False
    else:
        ss.just_calculated = False
        ss.expression += f"{name}("


def paren():
    _fresh_start("(")
    expr = ss.expression
    opened, closed = expr.count("("), expr.count(")")
    can_close = opened > closed and expr and expr[-1] not in "+−×÷^("
    ss.expression = expr + (")" if can_close else "(")


def toggle_angle():
    ss.angle_mode = "Deg" if ss.angle_mode == "Rad" else "Rad"


def toggle_inverse():
    ss.inverse = not ss.inverse


# ============================================================
# STYLE
# ============================================================

st.markdown(
    """
<style>
header, footer, #MainMenu { visibility: hidden; }
.stApp { background: #f8f8f8; }
.block-container { max-width: 400px !important; padding: 1.2rem 0.8rem 2rem !important; }

/* ---------- display (plain, like the reference) ---------- */
.screen {
    background: transparent; padding: 6px 10px 0; height: 190px; box-sizing: border-box;
    margin-bottom: 18px; display: flex; flex-direction: column; justify-content: flex-end;
}
.screen .mode { font-size: 12px; color: #a0a4ae; letter-spacing: .08em; margin-bottom: auto; text-align: left; }
.screen .hist { text-align: right; font-size: 20px; color: #9a9ea8; min-height: 28px;
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.screen .main { text-align: right; font-size: 46px; line-height: 1.2; color: #2b2b2b;
                white-space: nowrap; overflow-x: auto; scrollbar-width: none; }
.screen .main::-webkit-scrollbar { display: none; }
.screen .main.long { font-size: 30px; }
.screen .main.err { color: #c0564f; font-size: 34px; }

/* ---------- keypad: 4 columns of pills ---------- */
div[data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: nowrap !important; gap: 14px !important; }
div[data-testid="stColumn"], div[data-testid="column"] { min-width: 0 !important; flex: 1 1 0 !important; width: auto !important; }
div[data-testid="stVerticalBlock"] { gap: 14px !important; }
div[data-testid="stButton"] button {
    width: 100%; height: 42px; border: 0; border-radius: 22px; background: #e8ebf4;
    color: #2b2b2b; font-size: 15px; font-weight: 400;
    box-shadow: 0 4px 10px rgba(120,130,160,.12);
    transition: transform .06s ease, filter .06s ease;
}
div[data-testid="stButton"] button p { font-size: inherit; }
div[data-testid="stButton"] button:hover { filter: brightness(.97); border: 0; color: #2b2b2b; }
div[data-testid="stButton"] button:active { transform: scale(.95); }
/* white pills: C, backspace, %, digits, ( ), . */
div[class*="st-key-num-"] button, div[class*="st-key-back"] button,
div[class*="st-key-pct"] button, div[class*="st-key-paren"] button,
div[class*="st-key-clear"] button { background: #ffffff; font-size: 20px; }
div[class*="st-key-clear"] button { color: #d9706a; }
div[class*="st-key-back"] button { color: #d9706a; font-size: 18px; }
div[class*="st-key-paren"] button { font-size: 17px; }
/* grey operator pills */
div[class*="st-key-op-"] button { background: #dedede; color: #444; font-size: 24px; box-shadow: none; }
/* blue equals */
div[class*="st-key-equals"] button { background: #4c8df1; color: #fff; font-size: 24px; box-shadow: 0 4px 10px rgba(76,141,241,.3); }
div[class*="st-key-equals"] button:hover { color: #fff; }
/* helper buttons that only the laptop keyboard uses */
div[class*="st-key-hidden-"] { display: none !important; }

.hint { text-align: center; color: #9aa0ad; font-size: 12px; margin-top: 12px; line-height: 1.5; }
.hint b { color: #666; font-weight: 600; }
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# DISPLAY SCREEN (input + output)
# ============================================================

main_text = ss.expression or "0"
main_class = "main"
if ss.error:
    main_text, main_class = "Error", "main err"
elif len(main_text) > 12:
    main_class = "main long"

if ss.error or ss.just_calculated:
    hist = f"{html.escape(ss.history)} =" if ss.history else ""
else:  # live preview of the answer while typing
    hist = ""
    if ss.expression and not _is_number(ss.expression):
        try:
            hist = "= " + format_number(safe_eval(ss.expression, ss.angle_mode))
        except Exception:
            pass

st.markdown(
    f"""
    <div class="screen">
        <div class="mode">{ss.angle_mode.upper()}{' · INV' if ss.inverse else ''}</div>
        <div class="hist">{hist}</div>
        <div class="{main_class}">{html.escape(main_text)}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# KEYPAD
# ============================================================

inv = ss.inverse

keypad = [
    [
        ("inv", "⇄", toggle_inverse),
        ("mode", ss.angle_mode, toggle_angle),
        ("fn-sqrt", "√", lambda: function("sqrt")),
        ("fn-abs", "|x|", lambda: function("abs")),
    ],
    [
        ("fn-sin", "sin⁻¹" if inv else "sin", lambda: function("asin" if inv else "sin")),
        ("fn-cos", "cos⁻¹" if inv else "cos", lambda: function("acos" if inv else "cos")),
        ("fn-tan", "tan⁻¹" if inv else "tan", lambda: function("atan" if inv else "tan")),
        ("pi", "π", lambda: append("π")),
    ],
    [
        ("fn-ln", "ln", lambda: function("ln")),
        ("fn-log", "log", lambda: function("log")),
        ("recip", "1/x", reciprocal),
        ("e", "e", lambda: append("e")),
    ],
    [
        ("exp", "eˣ", lambda: append("e^")),
        ("sq", "x²", square),
        ("pow", "xʸ", lambda: append("^")),
        ("sign", "+/−", change_sign),
    ],
    [
        ("clear", "C", clear),
        ("back", "⌫", backspace),
        ("pct", "%", percent),
        ("op-div", "÷", lambda: append("÷")),
    ],
    [
        ("num-7", "7", lambda: append("7")),
        ("num-8", "8", lambda: append("8")),
        ("num-9", "9", lambda: append("9")),
        ("op-mul", "×", lambda: append("×")),
    ],
    [
        ("num-4", "4", lambda: append("4")),
        ("num-5", "5", lambda: append("5")),
        ("num-6", "6", lambda: append("6")),
        ("op-sub", "−", lambda: append("−")),
    ],
    [
        ("num-1", "1", lambda: append("1")),
        ("num-2", "2", lambda: append("2")),
        ("num-3", "3", lambda: append("3")),
        ("op-add", "+", lambda: append("+")),
    ],
    [
        ("paren", "( )", paren),
        ("num-0", "0", lambda: append("0")),
        ("num-dot", ".", lambda: append(".")),
        ("equals", "=", calculate),
    ],
]

for row in keypad:
    cols = st.columns(4)
    for col, (key, label, action) in zip(cols, row):
        with col:
            st.button(label, key=key, on_click=action, use_container_width=True)

# Explicit "(" and ")" for the laptop keyboard (hidden from the UI)
st.button("(", key="hidden-open", on_click=lambda: (_fresh_start("("), ss.update(expression=ss.expression + "(")))
st.button(")", key="hidden-close", on_click=lambda: (_fresh_start(")"), ss.update(expression=ss.expression + ")")))

st.markdown(
    '<div class="hint"><b>Keyboard works too:</b> 0–9 &nbsp;+ − * / ^ % ( ) .&nbsp; '
    "<b>Enter</b> = &nbsp;<b>Backspace</b> ⌫ &nbsp;<b>Esc</b> clear</div>",
    unsafe_allow_html=True,
)

# ============================================================
# LAPTOP KEYBOARD -> clicks the matching on-screen button
# (the calculation itself still runs in Python above)
# ============================================================

components.html(
    """
<script>
const doc = window.parent.document;
const MAP = {
  "0":"0","1":"1","2":"2","3":"3","4":"4","5":"5","6":"6","7":"7","8":"8","9":"9",
  ".":".", ",":".", "+":"+", "-":"−", "*":"×", "x":"×", "X":"×", "/":"÷",
  "^":"xʸ", "%":"%", "(":"(", ")":")", "p":"π",
  "Enter":"=", "=":"=", "Backspace":"⌫", "Escape":"C", "Delete":"C"
};
function press(label) {
  const btn = Array.from(doc.querySelectorAll('button'))
    .find(b => b.innerText.trim() === label);
  if (btn) btn.click();
}
if (window.parent.__calcKeyHandler) {
  doc.removeEventListener('keydown', window.parent.__calcKeyHandler, true);
}
window.parent.__calcKeyHandler = function (e) {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const label = MAP[e.key];
  if (!label) return;
  e.preventDefault();
  if (e.repeat && label === "=") return;
  press(label);
};
doc.addEventListener('keydown', window.parent.__calcKeyHandler, true);
</script>
""",
    height=0,
)
