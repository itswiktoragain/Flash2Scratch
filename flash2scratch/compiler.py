from .behavior_compiler import AS3Compiler as _BehaviorCompiler


class AS3Compiler(_BehaviorCompiler):
    """Public compiler with owner-aware ActionScript helper functions."""

    def _compile_callable_functions(self) -> None:
        for name, handler in self.program.handlers.items():
            if name.startswith("__as2_"):
                continue

            owner = getattr(handler, "owner", "stage") or "stage"
            if owner in {"_root", "this"}:
                owner = "stage"
            target_name = "stage" if owner == "stage" else owner.split(".")[0]
            target = self.p.stage if target_name == "stage" else self.p.sprite(target_name)
            builder = target.blocks

            message = f"__f2s_function_{name}"
            broadcast_id = self.p.broadcast(message)
            hat = self._top(
                builder,
                "event_whenbroadcastreceived",
                fields={"BROADCAST_OPTION": [message, broadcast_id]},
            )
            locals_map = {
                param: f"__f2s_arg_{name}_{param}"
                for param in getattr(handler, "params", [])
            }
            for mapped in locals_map.values():
                self.p.global_var(mapped, 0)

            first = self._compile_body(
                builder,
                handler.body,
                hat,
                target_name,
                locals_map,
            )
            builder.blocks[hat]["next"] = first

    def _call_statement(self, builder, expr, parent, target_name, locals_map):
        """Discard side-effect-free reporters when their value is unused."""
        name = str(expr.value).removeprefix("_root.")
        reporter_only = (
            name.startswith("Math.")
            or name
            in {
                "random",
                "getTimer",
                "Key.isDown",
                "Number",
                "int",
                "String",
                "parseInt",
                "parseFloat",
            }
        )
        if reporter_only:
            return []
        return super()._call_statement(
            builder,
            expr,
            parent,
            target_name,
            locals_map,
        )


__all__ = ["AS3Compiler"]
