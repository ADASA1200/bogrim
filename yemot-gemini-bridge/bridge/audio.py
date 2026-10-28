"""G.711 codecs and streaming resamplers (8 kHz telephone <-> Gemini 16/24 kHz)."""

from __future__ import annotations

import numpy as np
import soxr

TELEPHONE_RATE = 8000
GEMINI_IN_RATE = 16000
GEMINI_OUT_RATE = 24000
FRAME_SAMPLES = 160  # 20 ms at 8 kHz


def _ulaw_decode_table() -> np.ndarray:
    table = np.zeros(256, dtype=np.int16)
    for i in range(256):
        u = ~i & 0xFF
        exp = (u >> 4) & 0x07
        mant = u & 0x0F
        sample = (((mant << 3) + 0x84) << exp) - 0x84
        table[i] = -sample if u & 0x80 else sample
    return table


def _alaw_decode_table() -> np.ndarray:
    table = np.zeros(256, dtype=np.int16)
    for i in range(256):
        a = i ^ 0x55
        exp = (a >> 4) & 0x07
        mant = a & 0x0F
        if exp == 0:
            sample = (mant << 4) + 8
        else:
            sample = ((mant << 4) + 0x108) << (exp - 1)
        table[i] = sample if a & 0x80 else -sample
    return table


def _encode_table(decode: np.ndarray, silence_code: int) -> np.ndarray:
    """65536-entry linear->G.711 table: nearest decoded level, silence code wins ties."""
    level_to_code: dict[int, int] = {}
    for code in range(256):
        level = int(decode[code])
        if level not in level_to_code or code == silence_code:
            level_to_code[level] = code
    levels = np.array(sorted(level_to_code), dtype=np.int32)
    codes = np.array([level_to_code[v] for v in levels], dtype=np.uint8)
    midpoints = (levels[:-1] + levels[1:]) / 2.0
    pcm = np.arange(-32768, 32768, dtype=np.int32)
    idx = np.searchsorted(midpoints, pcm, side="right")
    return codes[idx]


_ULAW_DEC = _ulaw_decode_table()
_ALAW_DEC = _alaw_decode_table()
_ULAW_ENC = _encode_table(_ULAW_DEC, 0xFF)
_ALAW_ENC = _encode_table(_ALAW_DEC, 0xD5)

ULAW_SILENCE = 0xFF
ALAW_SILENCE = 0xD5


class G711:
    """One negotiated G.711 flavour: 'PCMA' (A-law, PT 8) or 'PCMU' (mu-law, PT 0)."""

    def __init__(self, name: str):
        if name == "PCMA":
            self.name, self.payload_type = "PCMA", 8
            self._dec, self._enc, self.silence_byte = _ALAW_DEC, _ALAW_ENC, ALAW_SILENCE
        elif name == "PCMU":
            self.name, self.payload_type = "PCMU", 0
            self._dec, self._enc, self.silence_byte = _ULAW_DEC, _ULAW_ENC, ULAW_SILENCE
        else:
            raise ValueError(f"unsupported codec {name}")

    def decode(self, payload: bytes) -> bytes:
        """G.711 bytes -> little-endian int16 PCM @ 8 kHz."""
        return self._dec[np.frombuffer(payload, dtype=np.uint8)].astype("<i2").tobytes()

    def encode(self, pcm: bytes) -> bytes:
        """little-endian int16 PCM @ 8 kHz -> G.711 bytes."""
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.int32)
        return self._enc[samples + 32768].tobytes()


class StreamResampler:
    """Stateful mono int16 resampler; safe to feed arbitrary chunk sizes."""

    def __init__(self, in_rate: int, out_rate: int, quality: str = "MQ"):
        # MQ/HQ add only ~15-26 ms of filter delay here; LQ is slower than MQ and HQ upsampling adds ~66 ms.
        self._stream = soxr.ResampleStream(in_rate, out_rate, 1, dtype="int16", quality=quality)
        self._carry = b""

    def process(self, pcm: bytes) -> bytes:
        data = self._carry + pcm
        usable = len(data) - (len(data) % 2)
        self._carry = data[usable:]
        if not usable:
            return b""
        out = self._stream.resample_chunk(np.frombuffer(data[:usable], dtype="<i2"))
        return np.asarray(out, dtype="<i2").tobytes()
