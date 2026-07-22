"""ReAct agent whose run loop is a generator of streaming events.

Events yielded by Agent.run_stream():
  {"type": "token",       "text": str}                      -- streamed assistant text
  {"type": "tool_call",   "id": str, "name": str, "args": dict}
  {"type": "tool_result", "id": str, "name": str, "result": str[, "image_base64": str]}
  {"type": "done",        "text": str}                      -- full final answer

Chart tools return {"summary", "image_base64"}: the image goes out in the
tool_result event only; the LLM conversation history gets just the summary.

Deferred feature: the notebook's plan_mode (draft a plan, pause on input() for
human approval) was dropped -- pausing a request mid-stream for approval needs
a two-request design that doesn't fit a stateless HTTP API yet.
"""

import json
from typing import Generator

DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."


class Agent:
    def __init__(self, client, model, max_turns=8, system_prompt=DEFAULT_SYSTEM_PROMPT):
        self.client = client
        self.model = model
        self.max_turns = max_turns      # safety net: max ReAct turns before forcing an answer
        self.system_prompt = system_prompt
        self.tools = []                 # list of JSON schemas, passed to the API's `tools=` arg
        self.dispatch = {}              # tool name -> callable
        self.notes = []                 # per-instance scratchpad
        self.messages = [{"role": "system", "content": self.system_prompt}]
        self._register_memory_tools()

    def register_tool(self, schema: dict, fn) -> None:
        self.tools.append(schema)
        self.dispatch[schema["function"]["name"]] = fn

    def _register_memory_tools(self) -> None:
        from ..tools import schema_for

        def take_notes(note: str) -> str:
            self.notes.append(note)
            return f"Saved note #{len(self.notes)}"

        def read_notes() -> str:
            if not self.notes:
                return "No notes yet."
            return "\n".join(f"{i + 1}. {n}" for i, n in enumerate(self.notes))

        self.register_tool(schema_for("take_notes"), take_notes)
        self.register_tool(schema_for("read_notes"), read_notes)

    # ------------------------------------------------------------------
    # Streaming LLM call: yields token events, returns the full message
    # ------------------------------------------------------------------

    def _stream_llm(self, messages, use_tools=True) -> Generator[dict, None, dict]:
        """Stream one completion. Yields token events as text arrives and
        returns the assembled assistant message dict (content + tool_calls)."""
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self.tools if use_tools else None,
            stream=True,
        )

        content_parts: list[str] = []
        tool_calls: dict[int, dict] = {}

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue
            if delta.content:
                content_parts.append(delta.content)
                yield {"type": "token", "text": delta.content}
            for tc in delta.tool_calls or []:
                slot = tool_calls.setdefault(
                    tc.index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                )
                if tc.id:
                    slot["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        slot["function"]["name"] += tc.function.name
                    if tc.function.arguments:
                        slot["function"]["arguments"] += tc.function.arguments

        message = {"role": "assistant", "content": "".join(content_parts) or None}
        if tool_calls:
            message["tool_calls"] = [tool_calls[i] for i in sorted(tool_calls)]
        return message

    # ------------------------------------------------------------------
    # The ReAct loop as an event generator
    # ------------------------------------------------------------------

    def run_stream(self, task: str, messages: list | None = None) -> Generator[dict, None, None]:
        """Loop Thought -> Action -> Observation, yielding events, until the
        model returns a final answer (no tool calls) or max_turns is reached.

        With no `messages` arg this is a one-off call. Passing a list (e.g.
        self.messages for a persistent session) continues that conversation;
        the list is mutated in place."""
        if messages is None:
            messages = [{"role": "system", "content": self.system_prompt}]
        messages.append({"role": "user", "content": task})

        for _turn in range(self.max_turns):
            message = yield from self._stream_llm(messages)
            messages.append(message)

            if not message.get("tool_calls"):
                yield {"type": "done", "text": message.get("content") or ""}
                return

            for tool_call in message["tool_calls"]:
                name = tool_call["function"]["name"]
                try:
                    args = json.loads(tool_call["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                yield {"type": "tool_call", "id": tool_call["id"], "name": name, "args": args}

                fn = self.dispatch.get(name)
                if fn is None:
                    result = f"Error: unknown tool {name!r}"
                else:
                    try:
                        result = fn(**args)
                    except Exception as e:
                        result = f"Error: could not run {name} ({e})"

                # Chart tools return {"summary", "image_base64"}. The image is
                # forwarded to the client only; the model's history gets the
                # summary, so base64 blobs never eat context on later turns.
                event = {"type": "tool_result", "id": tool_call["id"], "name": name}
                if isinstance(result, dict) and "image_base64" in result:
                    history_text = result.get("summary", "")
                    event["result"] = history_text
                    event["image_base64"] = result["image_base64"]
                else:
                    history_text = str(result)
                    event["result"] = history_text
                yield event

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": history_text,
                })

        # Ran out of turns while the model was still calling tools. Ask once
        # more with no tools offered, so it must summarize instead of acting.
        message = yield from self._stream_llm(messages, use_tools=False)
        messages.append(message)
        yield {"type": "done", "text": message.get("content") or ""}
