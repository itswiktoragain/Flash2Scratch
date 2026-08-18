from __future__ import annotations

import re

from .as3 import split_statements


KEYS = {
    "Keyboard.LEFT": "left arrow",
    "Key.LEFT": "left arrow",
    "37": "left arrow",
    "Keyboard.UP": "up arrow",
    "Key.UP": "up arrow",
    "38": "up arrow",
    "Keyboard.RIGHT": "right arrow",
    "Key.RIGHT": "right arrow",
    "39": "right arrow",
    "Keyboard.DOWN": "down arrow",
    "Key.DOWN": "down arrow",
    "40": "down arrow",
    "Keyboard.SPACE": "space",
    "Key.SPACE": "space",
    "32": "space",
    "Keyboard.ENTER": "enter",
    "Key.ENTER": "enter",
    "13": "enter",
}


class AS3Compiler:
    """Compiler shared by normalized AVM2/AS3 and AVM1/AS2 source models."""

    def __init__(self, project, program, report, fps=30):
        self.p = project
        self.program = program
        self.report = report
        self.fps = fps
        self.y = 20
        for name, value in program.variables.items():
            self.p.global_var(name, self._literal(value))
        for name in sorted(program.display_objects):
            self.p.sprite(name)

    def _literal(self, text):
        text = str(text).strip()
        if text in ("true", "false"):
            return 1 if text == "true" else 0
        if len(text) >= 2 and text[0] in "'\"" and text[-1] == text[0]:
            return text[1:-1]
        try:
            return float(text) if "." in text else int(text)
        except (TypeError, ValueError):
            return text

    def _top(self, builder, opcode, **kwargs):
        block = builder.add(opcode, top=True, x=20, y=self.y, **kwargs)
        self.y += 120
        return block

    def compile(self):
        for listener in self.program.listeners:
            handler = self.program.handlers.get(listener.handler)
            if handler:
                self._listener(listener, handler)
            else:
                self.report.unsupported.append(f"missing handler {listener.handler}")

    @staticmethod
    def _key_branches(body: str) -> list[tuple[str, str, tuple[int, int]]]:
        patterns = [
            re.compile(
                r"if\s*\(\s*\w+\.keyCode\s*={2,3}\s*([^)]+)\)\s*\{([^{}]*)\}",
                re.S,
            ),
            re.compile(
                r"if\s*\(\s*Key\.getCode\s*\(\s*\)\s*={2,3}\s*([^)]+)\)\s*\{([^{}]*)\}",
                re.S,
            ),
            re.compile(
                r"if\s*\(\s*Key\.isDown\s*\(\s*([^)]+)\s*\)\s*\)\s*\{([^{}]*)\}",
                re.S,
            ),
        ]
        found = []
        for pattern in patterns:
            for match in pattern.finditer(body):
                key = KEYS.get(match.group(1).strip())
                if key:
                    found.append((key, match.group(2), match.span()))
        found.sort(key=lambda item: item[2][0])
        return found

    @staticmethod
    def _remove_spans(text: str, spans: list[tuple[int, int]]) -> str:
        if not spans:
            return text
        chars = list(text)
        for start, end in spans:
            chars[start:end] = " " * (end - start)
        return "".join(chars)

    def _listener(self, listener, handler):
        target_name = "stage" if listener.owner == "stage" else listener.owner.split(".")[0]
        target = self.p.stage if target_name == "stage" else self.p.sprite(target_name)
        builder = target.blocks

        if listener.event == "Event.ENTER_FRAME":
            key_branches = self._key_branches(handler.body)
            for key, key_body, _ in key_branches:
                hat = self._top(
                    builder,
                    "event_whenkeypressed",
                    fields={"KEY_OPTION": [key, None]},
                )
                builder.blocks[hat]["next"] = self._body(
                    builder, key_body, hat, target_name
                )

            remaining = self._remove_spans(
                handler.body, [span for _, _, span in key_branches]
            )
            if remaining.strip():
                hat = self._top(builder, "event_whenflagclicked")
                forever = builder.add("control_forever", parent=hat)
                builder.blocks[hat]["next"] = forever
                first = self._body(builder, remaining, forever, target_name)
                if first:
                    builder.blocks[forever]["inputs"]["SUBSTACK"] = [2, first]

            if key_branches or remaining.strip():
                self.report.translated.append(f"{listener.handler}: ENTER_FRAME")
            return

        if listener.event == "MouseEvent.CLICK":
            opcode = (
                "event_whenstageclicked"
                if target_name == "stage"
                else "event_whenthisspriteclicked"
            )
            hat = self._top(builder, opcode)
            builder.blocks[hat]["next"] = self._body(
                builder, handler.body, hat, target_name
            )
            self.report.translated.append(f"{listener.handler}: CLICK")
            return

        if listener.event == "KeyboardEvent.KEY_DOWN":
            found = False
            for key, key_body, _ in self._key_branches(handler.body):
                found = True
                hat = self._top(
                    builder,
                    "event_whenkeypressed",
                    fields={"KEY_OPTION": [key, None]},
                )
                builder.blocks[hat]["next"] = self._body(
                    builder, key_body, hat, target_name
                )
            if found:
                self.report.translated.append(f"{listener.handler}: KEY_DOWN")
            else:
                self.report.unsupported.append(
                    f"{listener.handler}: dynamic KEY_DOWN handler"
                )
            return

        self.report.unsupported.append(f"event {listener.event}")

    def _body(self, builder, body, parent, target_name="stage"):
        ids = []
        for statement in split_statements(body):
            block = self._stmt(
                builder, " ".join(statement.split()), parent, target_name
            )
            if block:
                ids.append(block)
        if ids:
            builder.chain(ids)
            builder.blocks[ids[0]]["parent"] = parent
        return ids[0] if ids else None

    @staticmethod
    def _canonical_property(prop: str) -> str:
        return {
            "_x": "x",
            "_y": "y",
            "_rotation": "rotation",
            "_visible": "visible",
            "_alpha": "alpha",
            "_xscale": "scaleX",
            "_yscale": "scaleY",
        }.get(prop, prop)

    def _stmt(self, builder, statement, parent, target_name="stage"):
        # AS3: player.x += 5
        # AS2: player._x += 5 / _x += 5
        match = re.fullmatch(
            r"(?:(?:_root\.)?([A-Za-z_$][\w$]*)\.)?"
            r"(x|y|rotation|_x|_y|_rotation)\s*([+\-])=\s*"
            r"([-+]?\d+(?:\.\d+)?)",
            statement,
        )
        if match:
            obj, prop, op, number = match.groups()
            obj = obj or target_name
            prop = self._canonical_property(prop)
            value = float(number) * (1 if op == "+" else -1)

            if obj == target_name and target_name != "stage":
                if prop == "x":
                    self.report.translated.append(statement)
                    return builder.add(
                        "motion_changexby",
                        parent=parent,
                        inputs={"DX": builder.num(value)},
                    )
                if prop == "y":
                    self.report.translated.append(statement)
                    return builder.add(
                        "motion_changeyby",
                        parent=parent,
                        inputs={"DY": builder.num(-value)},
                    )
                if prop == "rotation":
                    self.report.translated.append(statement)
                    opcode = "motion_turnright" if value >= 0 else "motion_turnleft"
                    return builder.add(
                        opcode,
                        parent=parent,
                        inputs={"DEGREES": builder.num(abs(value))},
                    )

            var_name = f"{obj}.{prop}"
            vid = self.p.global_var(var_name)
            self.report.translated.append(statement)
            return builder.add(
                "data_changevariableby",
                parent=parent,
                inputs={"VALUE": builder.num(value)},
                fields={"VARIABLE": [var_name, vid]},
            )

        match = re.fullmatch(
            r"(?:_root\.)?([A-Za-z_$][\w$]*)\s*([+\-])=\s*"
            r"([-+]?\d+(?:\.\d+)?)",
            statement,
        )
        if match:
            name, op, value = match.groups()
            vid = self.p.global_var(name)
            delta = float(value) * (1 if op == "+" else -1)
            self.report.translated.append(statement)
            return builder.add(
                "data_changevariableby",
                parent=parent,
                inputs={"VALUE": builder.num(delta)},
                fields={"VARIABLE": [name, vid]},
            )

        match = re.fullmatch(
            r"(?:_root\.)?([A-Za-z_$][\w$]*)\s*=\s*(.+)",
            statement,
        )
        if match:
            name, value = match.groups()
            vid = self.p.global_var(name)
            self.report.translated.append(statement)
            return builder.add(
                "data_setvariableto",
                parent=parent,
                inputs={"VALUE": builder.text(self._literal(value))},
                fields={"VARIABLE": [name, vid]},
            )

        match = re.fullmatch(
            r"(?:(?:this|_root)\.)?gotoAnd(?:Stop|Play)\s*\(([^)]+)\)",
            statement,
        )
        if match:
            self.report.translated.append(statement)
            return builder.add(
                "looks_switchbackdropto",
                parent=parent,
                inputs={"BACKDROP": builder.text(self._literal(match.group(1)))},
            )

        if re.fullmatch(r"(?:(?:this|_root)\.)?nextFrame\s*\(\s*\)", statement):
            self.report.translated.append(statement)
            return builder.add("looks_nextbackdrop", parent=parent)

        match = re.fullmatch(r"(?:trace|console\.log)\s*\((.*)\)", statement)
        if match:
            self.report.translated.append(statement)
            return builder.add(
                "looks_say",
                parent=parent,
                inputs={"MESSAGE": builder.text(self._literal(match.group(1)))},
            )

        if statement and not re.match(
            r"^(var |const |import |package |super\s*\(|stop\s*\(|play\s*\()",
            statement,
        ):
            self.report.unsupported.append(statement[:180])
        return None
