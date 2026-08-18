from __future__ import annotations
import re
from .behavior_common import KEYS, PROPERTY_ALIASES
from .behavior_expr import ExpressionMixin
from .behavior_stmt import StatementMixin


class AS3Compiler(StatementMixin, ExpressionMixin):
    def __init__(self, project, program, report, fps=30, frame_map=None, stage_width=480, stage_height=360):
        self.p = project
        self.program = program
        self.report = report
        self.fps = max(1.0, float(fps or 30))
        self.frame_map = frame_map or {}
        self.stage_width = float(stage_width or 480)
        self.stage_height = float(stage_height or 360)
        self._y_by_builder: dict[int, int] = {}
        self._remote_handlers: set[tuple[str, str]] = set()
        self._reported_unsupported: set[str] = set()
        self._main_play_var = "__f2s_main_timeline_playing"
        self._list_names: set[str] = set(re.findall(r"\b(?:var\s+)?([A-Za-z_$][\w$]*)\s*=\s*(?:new\s+Array\s*\(|\[)", getattr(program, "text", "")))
        for name, value in program.variables.items():
            if name in self._list_names:
                self.p.global_list(name, [])
            else:
                self.p.global_var(name, self._initial_value(value))
        for name in sorted(program.display_objects):
            self.p.sprite(name)

    def _initial_value(self, text):
        text = str(text).strip()
        if text in ("true", "false"):
            return 1 if text == "true" else 0
        if len(text) >= 2 and text[0] in "'\"" and text[-1] == text[0]:
            return text[1:-1]
        try:
            return float(text) if "." in text else int(text)
        except (TypeError, ValueError):
            return 0

    def _top(self, builder, opcode, **kwargs):
        key = id(builder)
        y = self._y_by_builder.get(key, 20)
        block = builder.add(opcode, top=True, x=20, y=y, **kwargs)
        self._y_by_builder[key] = y + 150
        return block

    def _unsupported(self, text: str) -> None:
        text = " ".join(str(text).split())[:220]
        if text and text not in self._reported_unsupported:
            self._reported_unsupported.add(text)
            self.report.unsupported.append(text)

    def compile(self):
        self._install_main_timeline_controller()
        self._compile_callable_functions()
        self._compile_frame_scripts()
        for listener in self.program.listeners:
            handler = self.program.handlers.get(listener.handler)
            if handler:
                self._listener(listener, handler)
            else:
                self._unsupported(f"missing handler {listener.handler}")

    def _var_name(self, name: str, locals_map: dict[str, str] | None = None) -> str:
        name = name.strip()
        if name.startswith("_root."):
            name = name[6:]
        if locals_map and name in locals_map:
            return locals_map[name]
        return name

    def _var_reporter(self, builder, name: str, parent: str):
        vid = self.p.global_var(name)
        block = builder.add("data_variable", parent=parent, fields={"VARIABLE": [name, vid]})
        return [2, block]

    def _menu(self, builder, parent: str, opcode: str, field: str, value: str, item_id=None):
        block = builder.add(opcode, parent=parent, fields={field: [value, item_id]}, shadow=True)
        return [1, block]

    def _broadcast_input(self, builder, parent: str, name: str):
        broadcast_id = self.p.broadcast(name)
        return self._menu(builder, parent, "event_broadcast_menu", "BROADCAST_OPTION", name, broadcast_id)

    def _chain(self, builder, ids: list[str], parent: str | None = None):
        if not ids:
            return None
        builder.chain(ids)
        builder.blocks[ids[0]]["parent"] = parent
        return ids[0]

    def _install_main_timeline_controller(self) -> None:
        if len(self.p.stage.costumes) <= 1:
            return
        self.p.global_var(self._main_play_var, 1)
        builder = self.p.stage.blocks
        hat = self._top(builder, "event_whenflagclicked")
        forever = builder.add("control_forever", parent=hat)
        wait = builder.add("control_wait", parent=forever, inputs={"DURATION": builder.num(max(0.01, 1.0 / self.fps))})
        conditional = builder.add("control_if", parent=wait)
        condition = builder.add("operator_equals", parent=conditional)
        builder.blocks[condition]["inputs"]["OPERAND1"] = self._var_reporter(builder, self._main_play_var, condition)
        builder.blocks[condition]["inputs"]["OPERAND2"] = builder.num(1)
        next_backdrop = builder.add("looks_nextbackdrop", parent=conditional)
        builder.blocks[hat]["next"] = forever
        builder.blocks[forever]["inputs"]["SUBSTACK"] = [2, wait]
        builder.blocks[wait]["next"] = conditional
        builder.blocks[conditional]["inputs"]["CONDITION"] = [2, condition]
        builder.blocks[conditional]["inputs"]["SUBSTACK"] = [2, next_backdrop]

    def _compile_callable_functions(self) -> None:
        for name, handler in self.program.handlers.items():
            if name.startswith("__as2_"):
                continue
            builder = self.p.stage.blocks
            message = f"__f2s_function_{name}"
            bid = self.p.broadcast(message)
            hat = self._top(builder, "event_whenbroadcastreceived", fields={"BROADCAST_OPTION": [message, bid]})
            locals_map = {param: f"__f2s_arg_{name}_{param}" for param in getattr(handler, "params", [])}
            for mapped in locals_map.values():
                self.p.global_var(mapped, 0)
            first = self._compile_body(builder, handler.body, hat, "stage", locals_map)
            builder.blocks[hat]["next"] = first

    def _compile_frame_scripts(self) -> None:
        for script in getattr(self.program, "frame_scripts", []):
            builder = self.p.stage.blocks
            frame = script.frame
            if frame is None or frame <= 1:
                hat = self._top(builder, "event_whenflagclicked")
                description = "startup/timeline script"
            else:
                backdrop = self.frame_map.get(frame, f"frame {frame}")
                hat = self._top(builder, "event_whenbackdropswitchesto", fields={"BACKDROP": [backdrop, None]})
                description = f"frame {frame} timeline script"
            first = self._compile_body(builder, script.body, hat, "stage", {})
            builder.blocks[hat]["next"] = first
            if first:
                self.report.translated.append(description)

    @staticmethod
    def _key_from_expr_text(text: str) -> str | None:
        text = text.strip()
        if text in KEYS:
            return KEYS[text]
        try:
            value = int(float(text))
        except ValueError:
            value = None
        if value is not None:
            if 48 <= value <= 57:
                return chr(value)
            if 65 <= value <= 90:
                return chr(value).lower()
        if len(text) == 1 and text.isalnum():
            return text.lower()
        return None

    @staticmethod
    def _key_branches(body: str) -> list[tuple[str, str]]:
        patterns = [
            re.compile(r"if\s*\(\s*\w+\.keyCode\s*={2,3}\s*([^)]+)\)\s*\{([^{}]*)\}", re.S),
            re.compile(r"if\s*\(\s*Key\.getCode\s*\(\s*\)\s*={2,3}\s*([^)]+)\)\s*\{([^{}]*)\}", re.S),
        ]
        found: list[tuple[str, str]] = []
        for pattern in patterns:
            for match in pattern.finditer(body):
                key = AS3Compiler._key_from_expr_text(match.group(1))
                if key:
                    found.append((key, match.group(2)))
        return found

    def _listener(self, listener, handler):
        target_name = "stage" if listener.owner == "stage" else listener.owner.split(".")[0]
        target = self.p.stage if target_name == "stage" else self.p.sprite(target_name)
        builder = target.blocks
        if listener.event == "Event.GREEN_FLAG":
            hat = self._top(builder, "event_whenflagclicked")
            builder.blocks[hat]["next"] = self._compile_body(builder, handler.body, hat, target_name, {})
            self.report.translated.append(f"{listener.handler}: LOAD")
            return
        if listener.event == "Event.ENTER_FRAME":
            hat = self._top(builder, "event_whenflagclicked")
            forever = builder.add("control_forever", parent=hat)
            first = self._compile_body(builder, handler.body, forever, target_name, {})
            if first:
                current = first
                seen = set()
                while current not in seen and builder.blocks[current].get("next"):
                    seen.add(current)
                    current = builder.blocks[current]["next"]
                wait = builder.add("control_wait", parent=current, inputs={"DURATION": builder.num(max(0.01, 1.0 / self.fps))})
                builder.blocks[current]["next"] = wait
                body_first = first
            else:
                wait = builder.add("control_wait", parent=forever, inputs={"DURATION": builder.num(max(0.01, 1.0 / self.fps))})
                body_first = wait
            builder.blocks[hat]["next"] = forever
            builder.blocks[forever]["inputs"]["SUBSTACK"] = [2, body_first]
            self.report.translated.append(f"{listener.handler}: ENTER_FRAME")
            return
        if listener.event == "MouseEvent.CLICK":
            opcode = "event_whenstageclicked" if target_name == "stage" else "event_whenthisspriteclicked"
            hat = self._top(builder, opcode)
            builder.blocks[hat]["next"] = self._compile_body(builder, handler.body, hat, target_name, {})
            self.report.translated.append(f"{listener.handler}: CLICK")
            return
        if listener.event == "KeyboardEvent.KEY_DOWN":
            branches = self._key_branches(handler.body)
            if branches:
                for key, key_body in branches:
                    hat = self._top(builder, "event_whenkeypressed", fields={"KEY_OPTION": [key, None]})
                    builder.blocks[hat]["next"] = self._compile_body(builder, key_body, hat, target_name, {})
                self.report.translated.append(f"{listener.handler}: KEY_DOWN")
            else:
                self._unsupported(f"{listener.handler}: dynamic KEY_DOWN handler")
            return
        if listener.event in ("MouseEvent.MOUSE_OVER", "MouseEvent.MOUSE_OUT"):
            self._unsupported(f"{listener.handler}: {listener.event} edge event")
            return
        self._unsupported(f"event {listener.event}")

    @staticmethod
    def _split_property(name: str) -> tuple[str | None, str | None]:
        raw = name.strip()
        if raw.startswith("_root."):
            raw = raw[6:]
        parts = raw.split(".")
        if parts[-1] not in PROPERTY_ALIASES:
            return None, None
        prop = PROPERTY_ALIASES[parts[-1]]
        return ("this", prop) if len(parts) == 1 else (".".join(parts[:-1]), prop)

    def _is_current_owner(self, owner: str, target_name: str) -> bool:
        owner = owner.removeprefix("_root.")
        return owner in ("this", target_name) or (target_name == "stage" and owner in ("stage", "_root"))
