"""One Gemini Live session per phone call: audio in/out, tool calls, resumption."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from google import genai
from google.genai import types

from .config import Config
from .tools import ToolContext, ToolRegistry

log = logging.getLogger("bridge.gemini")
transcript_log = logging.getLogger("bridge.transcript")

CONNECT_TIMEOUT = 10
TOOL_TIMEOUT = 20
UPLINK_QUEUE_FRAMES = 150  # ~3 s of 20 ms chunks; older audio is dropped when the model is unreachable


def build_live_config(cfg: Config, registry: ToolRegistry, handle: str | None = None) -> types.LiveConnectConfig:
    tools: list[types.Tool] = []
    if cfg.enable_google_search:
        tools.append(types.Tool(google_search=types.GoogleSearch()))
    decls = registry.declarations()
    if decls:
        tools.append(types.Tool(function_declarations=decls))
    # Note: gemini-3.8-live rejects thinking_level and proactive_audio=False; neither is set here.
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=cfg.system_prompt,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=cfg.voice))),
        tools=tools,
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                silence_duration_ms=cfg.vad_silence_ms,
                start_of_speech_sensitivity=types.StartSensitivity(f"START_SENSITIVITY_{cfg.vad_start_sensitivity}"),
                end_of_speech_sensitivity=types.EndSensitivity(f"END_SENSITIVITY_{cfg.vad_end_sensitivity}"))),
        input_audio_transcription=types.AudioTranscriptionConfig() if cfg.log_transcripts else None,
        output_audio_transcription=types.AudioTranscriptionConfig() if cfg.log_transcripts else None,
        # Without compression an audio session ends after ~15 min; with it the call can run for as long as needed.
        context_window_compression=types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow()),
        session_resumption=types.SessionResumptionConfig(handle=handle),
    )


class GeminiLive:
    def __init__(self, cfg: Config, registry: ToolRegistry, ctx: ToolContext, *,
                 on_audio: Callable[[bytes], None], on_interrupt: Callable[[], None],
                 on_turn_complete: Callable[[], None], on_closed: Callable[[str], None],
                 client: Any = None):
        self._cfg = cfg
        self._registry = registry
        self._ctx = ctx
        self._on_audio = on_audio
        self._on_interrupt = on_interrupt
        self._on_turn_complete = on_turn_complete
        self._on_closed = on_closed
        self._client = client or genai.Client(api_key=cfg.gemini_api_key)
        self._cm: Any = None
        self._session: Any = None
        self._handle: str | None = None
        self._closing = False
        self._uplink: asyncio.Queue[bytes] = asyncio.Queue(maxsize=UPLINK_QUEUE_FRAMES)
        self._tasks: list[asyncio.Task] = []
        self._tool_tasks: dict[str, asyncio.Task] = {}
        self.tool_calls = 0
        self.reconnects = 0

    # ---- lifecycle -----------------------------------------------------
    async def start(self) -> None:
        await self._connect()
        self._tasks = [asyncio.create_task(self._recv_loop(), name="gemini-recv"),
                       asyncio.create_task(self._send_loop(), name="gemini-send")]

    async def say_greeting(self) -> None:
        if self._session and self._cfg.greeting_prompt:
            await self._session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=self._cfg.greeting_prompt)]),
                turn_complete=True)

    async def close(self) -> None:
        self._closing = True
        for t in [*self._tasks, *self._tool_tasks.values()]:
            t.cancel()
        await self._close_session()

    async def _connect(self) -> None:
        cm = self._client.aio.live.connect(model=self._cfg.gemini_model,
                                           config=build_live_config(self._cfg, self._registry, self._handle))
        session = await asyncio.wait_for(cm.__aenter__(), CONNECT_TIMEOUT)
        self._cm, self._session = cm, session

    async def _close_session(self) -> None:
        cm, self._cm, self._session = self._cm, None, None
        if cm is not None:
            try:
                await asyncio.wait_for(cm.__aexit__(None, None, None), 3)
            except Exception:
                pass

    async def _reconnect(self) -> bool:
        await self._close_session()
        for attempt in range(3):
            if self._closing:
                return False
            await asyncio.sleep(0.5 * (2 ** attempt))
            try:
                await self._connect()
                self.reconnects += 1
                log.info("Gemini session re-established (resumed=%s)", bool(self._handle))
                if not self._handle:  # no context to resume: tell the model what happened
                    await self._session.send_client_content(
                        turns=types.Content(role="user", parts=[types.Part(
                            text="[החיבור נותק לרגע וחודש. התנצלו בקצרה והמשיכו את השיחה.]")]),
                        turn_complete=True)
                return True
            except Exception as exc:
                log.warning("Gemini reconnect %d failed: %s", attempt + 1, exc)
        return False

    # ---- input ---------------------------------------------------------
    def send_audio(self, pcm16k: bytes) -> None:
        if self._uplink.full():
            try:
                self._uplink.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self._uplink.put_nowait(pcm16k)

    async def send_text(self, text: str) -> None:
        if self._session:
            await self._session.send_realtime_input(text=text)

    async def _send_loop(self) -> None:
        while True:
            chunk = await self._uplink.get()
            session = self._session
            if session is None:
                continue  # reconnecting: drop stale audio
            try:
                await session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))
            except Exception:
                pass  # the receive loop notices a dead connection and reconnects

    # ---- output --------------------------------------------------------
    async def _recv_loop(self) -> None:
        empty_passes = 0
        while not self._closing:
            try:
                got = 0
                async for msg in self._session.receive():
                    got += 1
                    await self._handle_message(msg)
                empty_passes = empty_passes + 1 if got == 0 else 0
                if empty_passes >= 3:
                    raise ConnectionError("receive() returned no messages")
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._closing:
                    return
                log.warning("Gemini connection lost: %s", exc)
                empty_passes = 0
                if not await self._reconnect():
                    break
        if not self._closing:
            self._on_closed("gemini connection lost")

    async def _handle_message(self, msg: Any) -> None:
        upd = getattr(msg, "session_resumption_update", None)
        if upd and upd.resumable and upd.new_handle:
            self._handle = upd.new_handle
        if getattr(msg, "go_away", None) is not None:
            log.info("Gemini GoAway (time_left=%s); will resume on disconnect", msg.go_away.time_left)
        sc = msg.server_content
        if sc is not None:
            if sc.interrupted:
                self._on_interrupt()
            if sc.model_turn and sc.model_turn.parts:
                for part in sc.model_turn.parts:
                    blob = part.inline_data
                    if blob and blob.data and (blob.mime_type or "").startswith("audio/"):
                        self._on_audio(blob.data)
            if self._cfg.log_transcripts:
                if sc.input_transcription and sc.input_transcription.text:
                    transcript_log.info("caller: %s", sc.input_transcription.text)
                if sc.output_transcription and sc.output_transcription.text:
                    transcript_log.info("model: %s", sc.output_transcription.text)
            if sc.turn_complete:
                self._on_turn_complete()
        if msg.tool_call and msg.tool_call.function_calls:
            task = asyncio.create_task(self._run_tools(msg.tool_call.function_calls))
            for fc in msg.tool_call.function_calls:
                self._tool_tasks[fc.id or fc.name] = task
            task.add_done_callback(lambda t: [self._tool_tasks.pop(k, None) for k, v in list(self._tool_tasks.items()) if v is t])
        if msg.tool_call_cancellation and msg.tool_call_cancellation.ids:
            for fid in msg.tool_call_cancellation.ids:
                task = self._tool_tasks.pop(fid, None)
                if task:
                    task.cancel()

    async def _run_tools(self, calls: list[Any]) -> None:
        async def one(fc: Any) -> types.FunctionResponse:
            self.tool_calls += 1
            log.info("tool call: %s", fc.name)
            try:
                result = await asyncio.wait_for(
                    self._registry.call(fc.name, dict(fc.args or {}), self._ctx), TOOL_TIMEOUT)
            except asyncio.TimeoutError:
                result = {"error": "tool timed out"}
            return types.FunctionResponse(id=fc.id, name=fc.name, response=result)

        responses = await asyncio.gather(*(one(fc) for fc in calls))
        if self._session is not None:
            await self._session.send_tool_response(function_responses=list(responses))
