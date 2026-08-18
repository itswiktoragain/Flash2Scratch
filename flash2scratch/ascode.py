from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Expr:
    kind: str
    value: Any = None
    left: "Expr | None" = None
    right: "Expr | None" = None
    args: list["Expr"] = field(default_factory=list)


@dataclass
class Stmt:
    kind: str
    expr: Expr | None = None
    target: Expr | None = None
    op: str | None = None
    body: list["Stmt"] = field(default_factory=list)
    else_body: list["Stmt"] = field(default_factory=list)
    init: list["Stmt"] = field(default_factory=list)
    update: list["Stmt"] = field(default_factory=list)


@dataclass(frozen=True)
class Token:
    kind: str
    value: str


_TOKEN_RE = re.compile(
    r"""
    (?P<WS>\s+)
  | (?P<NUMBER>(?:\d+\.\d*|\.\d+|\d+))
  | (?P<STRING>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
  | (?P<OP>===|!==|>>>|<<|>>|<=|>=|==|!=|&&|\|\||\+\+|--|\+=|-=|\*=|/=|%=|[+\-*/%<>=!?:.,;(){}\[\]])
  | (?P<IDENT>[A-Za-z_$][\w$]*)
  | (?P<OTHER>.)
    """,
    re.X | re.S,
)


def tokenize(text: str) -> list[Token]:
    out: list[Token] = []
    for match in _TOKEN_RE.finditer(text):
        kind = match.lastgroup or "OTHER"
        if kind == "WS":
            continue
        out.append(Token(kind, match.group()))
    return out


_PRECEDENCE = {
    "||": 1,
    "&&": 2,
    "==": 3,
    "===": 3,
    "!=": 3,
    "!==": 3,
    "<": 4,
    ">": 4,
    "<=": 4,
    ">=": 4,
    "+": 5,
    "-": 5,
    "*": 6,
    "/": 6,
    "%": 6,
}


class ExpressionParser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self, value: str | None = None) -> Token | None:
        if self.pos >= len(self.tokens):
            return None
        token = self.tokens[self.pos]
        if value is not None and token.value != value:
            return None
        return token

    def take(self, value: str | None = None) -> Token:
        token = self.peek(value)
        if token is None:
            expected = value or "token"
            got = self.peek().value if self.peek() else "<end>"
            raise ValueError(f"Expected {expected}, got {got}")
        self.pos += 1
        return token

    def parse(self) -> Expr:
        if not self.tokens:
            return Expr("literal", 0)
        expr = self._expr(0)
        if self.peek("?"):
            self.take("?")
            yes = self._expr(0)
            self.take(":")
            no = self._expr(0)
            expr = Expr("ternary", left=expr, args=[yes, no])
        return expr

    def _expr(self, min_precedence: int) -> Expr:
        left = self._unary()
        while True:
            token = self.peek()
            if token is None:
                break
            precedence = _PRECEDENCE.get(token.value)
            if precedence is None or precedence < min_precedence:
                break
            op = self.take().value
            right = self._expr(precedence + 1)
            left = Expr("binary", value=op, left=left, right=right)
        return left

    def _unary(self) -> Expr:
        token = self.peek()
        if token and token.value in ("!", "-", "+"):
            op = self.take().value
            return Expr("unary", value=op, left=self._unary())
        if token and token.value == "new":
            self.take("new")
            return Expr("new", left=self._primary())
        return self._primary()

    def _primary(self) -> Expr:
        token = self.take()
        if token.kind == "NUMBER":
            value: Any = float(token.value) if "." in token.value else int(token.value)
            return Expr("literal", value)
        if token.kind == "STRING":
            try:
                value = ast.literal_eval(token.value)
            except Exception:
                value = token.value[1:-1]
            return Expr("literal", value)
        if token.value == "(":
            expr = self._expr(0)
            self.take(")")
            return expr
        if token.value == "[":
            args: list[Expr] = []
            if not self.peek("]"):
                while True:
                    args.append(self._expr(0))
                    if not self.peek(","):
                        break
                    self.take(",")
            self.take("]")
            return Expr("array", args=args)
        if token.kind == "IDENT":
            if token.value in ("true", "false"):
                return Expr("literal", token.value == "true")
            if token.value in ("null", "undefined"):
                return Expr("literal", 0)

            parts = [token.value]
            while self.peek("."):
                save = self.pos
                self.take(".")
                nxt = self.peek()
                if nxt is None or nxt.kind != "IDENT":
                    self.pos = save
                    break
                parts.append(self.take().value)
            name = ".".join(parts)

            if self.peek("("):
                self.take("(")
                args: list[Expr] = []
                if not self.peek(")"):
                    while True:
                        args.append(self._expr(0))
                        if not self.peek(","):
                            break
                        self.take(",")
                self.take(")")
                expr = Expr("call", value=name, args=args)
            else:
                expr = Expr("name", name)

            while self.peek("["):
                self.take("[")
                index = self._expr(0)
                self.take("]")
                expr = Expr("index", left=expr, args=[index])
            return expr

        return Expr("name", token.value)


def parse_expression_tokens(tokens: list[Token]) -> Expr:
    try:
        return ExpressionParser(tokens).parse()
    except Exception:
        return Expr("raw", " ".join(token.value for token in tokens))


def parse_expression(text: str) -> Expr:
    return parse_expression_tokens(tokenize(text))


def _split_top_level(tokens: list[Token], separator: str) -> list[list[Token]]:
    parts: list[list[Token]] = []
    current: list[Token] = []
    paren = bracket = brace = 0
    for token in tokens:
        if token.value == "(":
            paren += 1
        elif token.value == ")":
            paren = max(0, paren - 1)
        elif token.value == "[":
            bracket += 1
        elif token.value == "]":
            bracket = max(0, bracket - 1)
        elif token.value == "{":
            brace += 1
        elif token.value == "}":
            brace = max(0, brace - 1)
        if token.value == separator and paren == 0 and bracket == 0 and brace == 0:
            parts.append(current)
            current = []
        else:
            current.append(token)
    parts.append(current)
    return parts


def parse_simple_tokens(tokens: list[Token]) -> list[Stmt]:
    tokens = [token for token in tokens if token.value != ";"]
    if not tokens:
        return []

    if tokens[0].value in ("var", "const"):
        statements: list[Stmt] = []
        for declaration in _split_top_level(tokens[1:], ","):
            if not declaration:
                continue
            eq = next((i for i, token in enumerate(declaration) if token.value == "="), None)
            if eq is None:
                target = parse_expression_tokens(declaration)
                statements.append(Stmt("assign", target=target, op="=", expr=Expr("literal", 0)))
            else:
                target = parse_expression_tokens(declaration[:eq])
                value = parse_expression_tokens(declaration[eq + 1 :])
                statements.append(Stmt("assign", target=target, op="=", expr=value))
        return statements

    if len(tokens) >= 2 and tokens[-1].value in ("++", "--"):
        return [Stmt("update", target=parse_expression_tokens(tokens[:-1]), op=tokens[-1].value)]
    if len(tokens) >= 2 and tokens[0].value in ("++", "--"):
        return [Stmt("update", target=parse_expression_tokens(tokens[1:]), op=tokens[0].value)]

    paren = bracket = 0
    for index, token in enumerate(tokens):
        if token.value == "(":
            paren += 1
        elif token.value == ")":
            paren = max(0, paren - 1)
        elif token.value == "[":
            bracket += 1
        elif token.value == "]":
            bracket = max(0, bracket - 1)
        elif paren == 0 and bracket == 0 and token.value in ("=", "+=", "-=", "*=", "/=", "%="):
            target = parse_expression_tokens(tokens[:index])
            value = parse_expression_tokens(tokens[index + 1 :])
            return [Stmt("assign", target=target, op=token.value, expr=value)]

    return [Stmt("expr", expr=parse_expression_tokens(tokens))]


class StatementParser:
    def __init__(self, text: str):
        self.tokens = tokenize(text)
        self.pos = 0

    def peek(self, value: str | None = None) -> Token | None:
        if self.pos >= len(self.tokens):
            return None
        token = self.tokens[self.pos]
        if value is not None and token.value != value:
            return None
        return token

    def take(self, value: str | None = None) -> Token:
        token = self.peek(value)
        if token is None:
            expected = value or "token"
            got = self.peek().value if self.peek() else "<end>"
            raise ValueError(f"Expected {expected}, got {got}")
        self.pos += 1
        return token

    def parse(self) -> list[Stmt]:
        out: list[Stmt] = []
        while self.peek() is not None:
            if self.peek(";"):
                self.take(";")
                continue
            try:
                out.extend(self._statement())
            except Exception:
                raw = self._collect_until({";", "}"})
                if self.peek(";"):
                    self.take(";")
                if raw:
                    out.append(Stmt("raw", expr=Expr("raw", " ".join(t.value for t in raw))))
                elif self.peek("}"):
                    break
        return out

    def _statement_or_block(self) -> list[Stmt]:
        if self.peek("{"):
            self.take("{")
            body: list[Stmt] = []
            while self.peek() is not None and not self.peek("}"):
                if self.peek(";"):
                    self.take(";")
                    continue
                body.extend(self._statement())
            if self.peek("}"):
                self.take("}")
            return body
        return self._statement()

    def _paren_tokens(self) -> list[Token]:
        self.take("(")
        depth = 1
        out: list[Token] = []
        while self.peek() is not None and depth:
            token = self.take()
            if token.value == "(":
                depth += 1
            elif token.value == ")":
                depth -= 1
                if depth == 0:
                    break
            if depth:
                out.append(token)
        return out

    def _collect_until(self, stops: set[str]) -> list[Token]:
        out: list[Token] = []
        paren = bracket = 0
        while self.peek() is not None:
            token = self.peek()
            if paren == 0 and bracket == 0 and token.value in stops:
                break
            token = self.take()
            if token.value == "(":
                paren += 1
            elif token.value == ")":
                paren = max(0, paren - 1)
            elif token.value == "[":
                bracket += 1
            elif token.value == "]":
                bracket = max(0, bracket - 1)
            out.append(token)
        return out

    def _statement(self) -> list[Stmt]:
        token = self.peek()
        if token is None:
            return []

        if token.value == "{":
            return self._statement_or_block()

        if token.value == "if":
            self.take()
            condition = parse_expression_tokens(self._paren_tokens())
            body = self._statement_or_block()
            else_body: list[Stmt] = []
            if self.peek("else"):
                self.take("else")
                else_body = self._statement_or_block()
            return [Stmt("if", expr=condition, body=body, else_body=else_body)]

        if token.value == "while":
            self.take()
            condition = parse_expression_tokens(self._paren_tokens())
            return [Stmt("while", expr=condition, body=self._statement_or_block())]

        if token.value == "do":
            self.take()
            body = self._statement_or_block()
            condition = Expr("literal", True)
            if self.peek("while"):
                self.take("while")
                condition = parse_expression_tokens(self._paren_tokens())
                if self.peek(";"):
                    self.take(";")
            return [Stmt("do_while", expr=condition, body=body)]

        if token.value == "for":
            self.take()
            inside = self._paren_tokens()
            parts = _split_top_level(inside, ";")
            while len(parts) < 3:
                parts.append([])
            init = parse_simple_tokens(parts[0])
            condition = parse_expression_tokens(parts[1]) if parts[1] else Expr("literal", True)
            update = parse_simple_tokens(parts[2])
            body = self._statement_or_block()
            return [Stmt("for", expr=condition, body=body, init=init, update=update)]

        if token.value == "return":
            self.take()
            values = self._collect_until({";", "}"})
            if self.peek(";"):
                self.take(";")
            return [Stmt("return", expr=parse_expression_tokens(values) if values else None)]

        if token.value in ("break", "continue"):
            kind = self.take().value
            if self.peek(";"):
                self.take(";")
            return [Stmt(kind)]

        raw = self._collect_until({";", "}"})
        if self.peek(";"):
            self.take(";")
        return parse_simple_tokens(raw)


def parse_statements(text: str) -> list[Stmt]:
    return StatementParser(text).parse()
