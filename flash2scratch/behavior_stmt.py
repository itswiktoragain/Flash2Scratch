from __future__ import annotations
from .ascode import Expr, Stmt, parse_statements
from .behavior_common import PROPERTY_ALIASES


class StatementMixin:
    def _compile_body(self, builder, body: str, parent: str, target_name: str, locals_map: dict[str, str]):
        try:
            statements = parse_statements(body)
        except Exception as exc:
            self._unsupported(f"parser failed: {exc}: {body[:120]}")
            return None
        return self._compile_statements(builder, statements, parent, target_name, locals_map)

    def _compile_statements(self, builder, statements: list[Stmt], parent: str, target_name: str, locals_map: dict[str, str]):
        ids: list[str] = []
        for statement in statements:
            ids.extend(self._stmt_blocks(builder, statement, parent, target_name, locals_map))
        return self._chain(builder, ids, parent)

    def _stmt_blocks(self, builder, statement: Stmt, parent: str, target_name: str, locals_map: dict[str, str]) -> list[str]:
        if statement.kind == "assign":
            return self._assignment(builder, statement.target, statement.op or "=", statement.expr or Expr("literal", 0), parent, target_name, locals_map)
        if statement.kind == "update":
            return self._assignment(builder, statement.target, "+=", Expr("literal", 1 if statement.op == "++" else -1), parent, target_name, locals_map)
        if statement.kind == "expr":
            if statement.expr and statement.expr.kind == "call":
                return self._call_statement(builder, statement.expr, parent, target_name, locals_map)
            self._unsupported(f"unused expression {self._expr_text(statement.expr)}")
            return []
        if statement.kind == "if":
            opcode = "control_if_else" if statement.else_body else "control_if"
            block = builder.add(opcode, parent=parent)
            builder.blocks[block]["inputs"]["CONDITION"] = self._boolean_input(builder, statement.expr or Expr("literal", False), block, target_name, locals_map)
            first = self._compile_statements(builder, statement.body, block, target_name, locals_map)
            if first:
                builder.blocks[block]["inputs"]["SUBSTACK"] = [2, first]
            if statement.else_body:
                other = self._compile_statements(builder, statement.else_body, block, target_name, locals_map)
                if other:
                    builder.blocks[block]["inputs"]["SUBSTACK2"] = [2, other]
            self.report.translated.append("if/else")
            return [block]
        if statement.kind == "while":
            block = builder.add("control_repeat_until", parent=parent)
            builder.blocks[block]["inputs"]["CONDITION"] = self._boolean_input(builder, Expr("unary", value="!", left=statement.expr), block, target_name, locals_map)
            first = self._compile_statements(builder, statement.body, block, target_name, locals_map)
            if first:
                builder.blocks[block]["inputs"]["SUBSTACK"] = [2, first]
            self.report.translated.append("while loop")
            return [block]
        if statement.kind == "do_while":
            once = builder.add("control_repeat", parent=parent, inputs={"TIMES": builder.num(1)})
            first_once = self._compile_statements(builder, statement.body, once, target_name, locals_map)
            if first_once:
                builder.blocks[once]["inputs"]["SUBSTACK"] = [2, first_once]
            loop = builder.add("control_repeat_until", parent=parent)
            builder.blocks[loop]["inputs"]["CONDITION"] = self._boolean_input(builder, Expr("unary", value="!", left=statement.expr), loop, target_name, locals_map)
            repeat_first = self._compile_statements(builder, statement.body, loop, target_name, locals_map)
            if repeat_first:
                builder.blocks[loop]["inputs"]["SUBSTACK"] = [2, repeat_first]
            self.report.translated.append("do/while loop")
            return [once, loop]
        if statement.kind == "for":
            ids: list[str] = []
            for init in statement.init:
                ids.extend(self._stmt_blocks(builder, init, parent, target_name, locals_map))
            loop = builder.add("control_repeat_until", parent=parent)
            builder.blocks[loop]["inputs"]["CONDITION"] = self._boolean_input(builder, Expr("unary", value="!", left=statement.expr), loop, target_name, locals_map)
            first = self._compile_statements(builder, list(statement.body) + list(statement.update), loop, target_name, locals_map)
            if first:
                builder.blocks[loop]["inputs"]["SUBSTACK"] = [2, first]
            ids.append(loop)
            self.report.translated.append("for loop")
            return ids
        if statement.kind == "return":
            ids: list[str] = []
            if statement.expr is not None:
                name = "__f2s_last_return"
                vid = self.p.global_var(name, 0)
                block = builder.add("data_setvariableto", parent=parent, fields={"VARIABLE": [name, vid]})
                builder.blocks[block]["inputs"]["VALUE"] = self._expr_input(builder, statement.expr, block, target_name, locals_map)
                ids.append(block)
            ids.append(builder.add("control_stop", parent=parent, fields={"STOP_OPTION": ["this script", None]}))
            return ids
        if statement.kind in ("break", "continue"):
            self._unsupported(f"{statement.kind} inside loop")
            return []
        if statement.kind == "raw":
            self._unsupported(self._expr_text(statement.expr))
            return []
        self._unsupported(f"statement {statement.kind}")
        return []

    def _assignment(self, builder, target: Expr | None, op: str, value: Expr, parent: str, target_name: str, locals_map: dict[str, str]) -> list[str]:
        if target is None:
            self._unsupported("missing assignment target")
            return []
        if target.kind == "index":
            return self._list_index_assignment(builder, target, op, value, parent, target_name, locals_map)
        if target.kind != "name":
            self._unsupported(f"assignment target {self._expr_text(target)}")
            return []
        variable_target = self._var_name(str(target.value), locals_map)
        if self._is_list_initializer(value):
            return self._list_initialize(builder, variable_target, value, parent, target_name, locals_map)
        owner, prop = self._split_property(str(target.value))
        if prop:
            if op != "=":
                value = Expr("binary", value=op[0], left=Expr("name", str(target.value)), right=value)
            return self._property_write(builder, owner or "this", prop, value, parent, target_name, locals_map)
        name = self._var_name(str(target.value), locals_map)
        vid = self.p.global_var(name)
        if op == "+=":
            block = builder.add("data_changevariableby", parent=parent, fields={"VARIABLE": [name, vid]})
            builder.blocks[block]["inputs"]["VALUE"] = self._expr_input(builder, value, block, target_name, locals_map)
            self.report.translated.append(f"{name} +=")
            return [block]
        if op == "-=":
            block = builder.add("data_changevariableby", parent=parent, fields={"VARIABLE": [name, vid]})
            builder.blocks[block]["inputs"]["VALUE"] = self._expr_input(builder, Expr("unary", value="-", left=value), block, target_name, locals_map)
            self.report.translated.append(f"{name} -=")
            return [block]
        if op != "=":
            value = Expr("binary", value=op[0], left=Expr("name", name), right=value)
        block = builder.add("data_setvariableto", parent=parent, fields={"VARIABLE": [name, vid]})
        builder.blocks[block]["inputs"]["VALUE"] = self._expr_input(builder, value, block, target_name, locals_map)
        self.report.translated.append(f"{name} {op}")
        return [block]

    @staticmethod
    def _is_list_initializer(expr: Expr) -> bool:
        return expr.kind == "array" or (expr.kind == "new" and expr.left and expr.left.kind == "call" and str(expr.left.value) == "Array")

    def _list_initialize(self, builder, name: str, expr: Expr, parent: str, target_name: str, locals_map: dict[str, str]) -> list[str]:
        self._list_names.add(name)
        list_id = self.p.global_list(name, [])
        ids = [builder.add("data_deletealloflist", parent=parent, fields={"LIST": [name, list_id]})]
        items = expr.args if expr.kind == "array" else []
        if expr.kind == "new" and expr.left and expr.left.kind == "call" and len(expr.left.args) > 1:
            items = expr.left.args
        for item in items:
            add = builder.add("data_addtolist", parent=parent, fields={"LIST": [name, list_id]})
            builder.blocks[add]["inputs"]["ITEM"] = self._expr_input(builder, item, add, target_name, locals_map)
            ids.append(add)
        self.report.translated.append(f"array/list {name}")
        return ids

    def _list_index_assignment(self, builder, target: Expr, op: str, value: Expr, parent: str, target_name: str, locals_map: dict[str, str]) -> list[str]:
        if not target.left or target.left.kind != "name" or not target.args:
            self._unsupported(f"indexed assignment {self._expr_text(target)}")
            return []
        name = self._var_name(str(target.left.value), locals_map)
        self._list_names.add(name)
        list_id = self.p.global_list(name, [])
        if op != "=":
            value = Expr("binary", value=op[0], left=Expr("index", left=Expr("name", name), args=[target.args[0]]), right=value)
        index_expr = Expr("binary", value="+", left=target.args[0], right=Expr("literal", 1))
        block = builder.add("data_replaceitemoflist", parent=parent, fields={"LIST": [name, list_id]})
        builder.blocks[block]["inputs"]["INDEX"] = self._expr_input(builder, index_expr, block, target_name, locals_map)
        builder.blocks[block]["inputs"]["ITEM"] = self._expr_input(builder, value, block, target_name, locals_map)
        self.report.translated.append(f"{name}[index] {op}")
        return [block]

    def _property_write(self, builder, owner: str, prop: str, value: Expr, parent: str, target_name: str, locals_map: dict[str, str]) -> list[str]:
        owner = owner.removeprefix("_root.")
        if self._is_current_owner(owner, target_name):
            return self._current_property_write(builder, prop, value, parent, target_name, locals_map)
        obj = owner.split(".")[0]
        self.p.sprite(obj)
        command_var = f"__f2s_set_{obj}_{prop}"
        vid = self.p.global_var(command_var, 0)
        set_value = builder.add("data_setvariableto", parent=parent, fields={"VARIABLE": [command_var, vid]})
        builder.blocks[set_value]["inputs"]["VALUE"] = self._expr_input(builder, value, set_value, target_name, locals_map)
        message = self._ensure_remote_property_handler(obj, prop, command_var)
        broadcast = builder.add("event_broadcastandwait", parent=set_value)
        builder.blocks[broadcast]["inputs"]["BROADCAST_INPUT"] = self._broadcast_input(builder, broadcast, message)
        self.report.translated.append(f"{obj}.{prop} write")
        return [set_value, broadcast]

    def _current_property_write(self, builder, prop: str, value: Expr, parent: str, target_name: str, locals_map: dict[str, str]) -> list[str]:
        if target_name == "stage" and prop in ("x", "y", "rotation", "scale"):
            self._unsupported(f"stage.{prop} assignment")
            return []
        if prop == "x":
            block = builder.add("motion_setx", parent=parent)
            builder.blocks[block]["inputs"]["X"] = self._expr_input(builder, Expr("binary", value="-", left=value, right=Expr("literal", self.stage_width / 2)), block, target_name, locals_map)
            return [block]
        if prop == "y":
            block = builder.add("motion_sety", parent=parent)
            builder.blocks[block]["inputs"]["Y"] = self._expr_input(builder, Expr("binary", value="-", left=Expr("literal", self.stage_height / 2), right=value), block, target_name, locals_map)
            return [block]
        if prop == "rotation":
            block = builder.add("motion_pointindirection", parent=parent)
            builder.blocks[block]["inputs"]["DIRECTION"] = self._expr_input(builder, Expr("binary", value="+", left=value, right=Expr("literal", 90)), block, target_name, locals_map)
            return [block]
        if prop == "scale":
            block = builder.add("looks_setsizeto", parent=parent)
            builder.blocks[block]["inputs"]["SIZE"] = self._expr_input(builder, value, block, target_name, locals_map)
            return [block]
        if prop == "alpha":
            block = builder.add("looks_seteffectto", parent=parent, fields={"EFFECT": ["ghost", None]})
            builder.blocks[block]["inputs"]["VALUE"] = self._expr_input(builder, Expr("binary", value="-", left=Expr("literal", 100), right=value), block, target_name, locals_map)
            return [block]
        if prop == "visible":
            block = builder.add("control_if_else", parent=parent)
            builder.blocks[block]["inputs"]["CONDITION"] = self._boolean_input(builder, value, block, target_name, locals_map)
            show = builder.add("looks_show", parent=block)
            hide = builder.add("looks_hide", parent=block)
            builder.blocks[block]["inputs"]["SUBSTACK"] = [2, show]
            builder.blocks[block]["inputs"]["SUBSTACK2"] = [2, hide]
            return [block]
        self._unsupported(f"property assignment {prop}")
        return []

    def _ensure_remote_property_handler(self, obj: str, prop: str, command_var: str) -> str:
        key = (obj, prop)
        message = f"__f2s_set_{obj}_{prop}"
        if key in self._remote_handlers:
            return message
        self._remote_handlers.add(key)
        sprite = self.p.sprite(obj)
        builder = sprite.blocks
        broadcast_id = self.p.broadcast(message)
        hat = self._top(builder, "event_whenbroadcastreceived", fields={"BROADCAST_OPTION": [message, broadcast_id]})
        blocks = self._current_property_write(builder, prop, Expr("name", command_var), hat, obj, {})
        if blocks:
            builder.blocks[hat]["next"] = self._chain(builder, blocks, hat)
        return message

    def _backdrop_value(self, expr: Expr) -> str:
        if expr.kind == "literal" and isinstance(expr.value, (int, float)):
            value = int(expr.value)
            return self.frame_map.get(value, f"frame {value}")
        return str(expr.value) if expr.kind == "literal" else self._expr_text(expr)

    def _set_main_playing(self, builder, parent: str, value: int) -> str:
        vid = self.p.global_var(self._main_play_var, 1)
        return builder.add("data_setvariableto", parent=parent, fields={"VARIABLE": [self._main_play_var, vid]}, inputs={"VALUE": builder.num(value)})

    def _call_statement(self, builder, expr: Expr, parent: str, target_name: str, locals_map: dict[str, str]) -> list[str]:
        name = str(expr.value)
        short = name.removeprefix("_root.")
        args = expr.args
        method_owner = None
        method = short
        if "." in short:
            method_owner, method = short.rsplit(".", 1)
        if method_owner:
            list_name = self._var_name(method_owner, locals_map)
            if list_name in self._list_names and method in {"push", "pop", "shift", "unshift"}:
                list_id = self.p.global_list(list_name, [])
                if method == "push" and args:
                    block = builder.add("data_addtolist", parent=parent, fields={"LIST": [list_name, list_id]})
                    builder.blocks[block]["inputs"]["ITEM"] = self._expr_input(builder, args[0], block, target_name, locals_map)
                    return [block]
                if method == "pop":
                    return [builder.add("data_deleteoflist", parent=parent, fields={"LIST": [list_name, list_id]}, inputs={"INDEX": builder.text("last")})]
                if method == "shift":
                    return [builder.add("data_deleteoflist", parent=parent, fields={"LIST": [list_name, list_id]}, inputs={"INDEX": builder.num(1)})]
                if method == "unshift" and args:
                    block = builder.add("data_insertatlist", parent=parent, fields={"LIST": [list_name, list_id]}, inputs={"INDEX": builder.num(1)})
                    builder.blocks[block]["inputs"]["ITEM"] = self._expr_input(builder, args[0], block, target_name, locals_map)
                    return [block]
        if method in ("gotoAndStop", "gotoAndPlay") and args:
            owner = method_owner or ("stage" if target_name == "stage" else "this")
            if self._is_current_owner(owner, target_name):
                if target_name == "stage":
                    block = builder.add("looks_switchbackdropto", parent=parent)
                    builder.blocks[block]["inputs"]["BACKDROP"] = builder.text(self._backdrop_value(args[0])) if args[0].kind == "literal" else self._expr_input(builder, args[0], block, target_name, locals_map)
                    play = self._set_main_playing(builder, block, 1 if method == "gotoAndPlay" else 0)
                    self.report.translated.append(method)
                    return [block, play]
                block = builder.add("looks_switchcostumeto", parent=parent)
                builder.blocks[block]["inputs"]["COSTUME"] = self._expr_input(builder, args[0], block, target_name, locals_map)
                play_var = f"__f2s_symbol_play_{target_name}"
                play_id = self.p.global_var(play_var, 1)
                set_play = builder.add("data_setvariableto", parent=parent, fields={"VARIABLE": [play_var, play_id]}, inputs={"VALUE": builder.num(1 if method == "gotoAndPlay" else 0)})
                return [block, set_play]
            self._unsupported(f"remote {name}")
            return []
        if method in ("nextFrame", "prevFrame"):
            owner = method_owner or ("stage" if target_name == "stage" else "this")
            if self._is_current_owner(owner, target_name):
                if target_name == "stage":
                    if method == "nextFrame":
                        block = builder.add("looks_nextbackdrop", parent=parent)
                    else:
                        current = builder.add("looks_backdropnumbername", parent=parent, fields={"NUMBER_NAME": ["number", None]})
                        minus = builder.add("operator_subtract", parent=parent)
                        builder.blocks[current]["parent"] = minus
                        builder.blocks[minus]["inputs"]["NUM1"] = [2, current]
                        builder.blocks[minus]["inputs"]["NUM2"] = builder.num(1)
                        block = builder.add("looks_switchbackdropto", parent=parent)
                        builder.blocks[minus]["parent"] = block
                        builder.blocks[block]["inputs"]["BACKDROP"] = [2, minus]
                    return [block, self._set_main_playing(builder, block, 0)]
                if method == "nextFrame":
                    return [builder.add("looks_nextcostume", parent=parent)]
            self._unsupported(name)
            return []
        if method in ("stop", "play") and not args:
            owner = method_owner or ("stage" if target_name == "stage" else "this")
            if target_name == "stage" and self._is_current_owner(owner, target_name):
                return [self._set_main_playing(builder, parent, 0 if method == "stop" else 1)]
            obj = target_name if owner in ("this", target_name) else owner
            play_var = f"__f2s_symbol_play_{obj}"
            vid = self.p.global_var(play_var, 1)
            return [builder.add("data_setvariableto", parent=parent, fields={"VARIABLE": [play_var, vid]}, inputs={"VALUE": builder.num(0 if method == "stop" else 1)})]
        if short in ("trace", "console.log") and args:
            block = builder.add("looks_say", parent=parent)
            builder.blocks[block]["inputs"]["MESSAGE"] = self._expr_input(builder, args[0], block, target_name, locals_map)
            return [block]
        if short == "removeMovieClip" and args:
            target = self._expr_text(args[0]).removeprefix("_root.")
            return self._property_write(builder, target, "visible", Expr("literal", False), parent, target_name, locals_map)
        if short == "setProperty" and len(args) >= 3:
            target = self._expr_text(args[0]).strip("\"'")
            prop = PROPERTY_ALIASES.get(self._expr_text(args[1]).strip("\"'"))
            if prop:
                return self._property_write(builder, target, prop, args[2], parent, target_name, locals_map)
        function_name = method if method in self.program.handlers else short
        handler = self.program.handlers.get(function_name)
        if handler and not function_name.startswith("__as2_"):
            ids: list[str] = []
            for index, param in enumerate(getattr(handler, "params", [])):
                mapped = f"__f2s_arg_{function_name}_{param}"
                vid = self.p.global_var(mapped, 0)
                set_arg = builder.add("data_setvariableto", parent=parent, fields={"VARIABLE": [mapped, vid]})
                builder.blocks[set_arg]["inputs"]["VALUE"] = self._expr_input(builder, args[index] if index < len(args) else Expr("literal", 0), set_arg, target_name, locals_map)
                ids.append(set_arg)
            message = f"__f2s_function_{function_name}"
            broadcast = builder.add("event_broadcastandwait", parent=parent)
            builder.blocks[broadcast]["inputs"]["BROADCAST_INPUT"] = self._broadcast_input(builder, broadcast, message)
            ids.append(broadcast)
            self.report.translated.append(f"function call {function_name}()")
            return ids
        known_reporter = short.startswith("Math.") or short in {"random", "getTimer", "Key.isDown", "Number", "int", "String", "parseInt", "parseFloat"}
        if known_reporter:
            self._call_expr(builder, expr, parent, target_name, locals_map)
            return []
        self._unsupported(f"call {name}()")
        return []
