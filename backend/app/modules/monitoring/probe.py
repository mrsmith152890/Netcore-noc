import asyncio
import re
from dataclasses import dataclass

@dataclass
class ProbeResult:
    success: bool
    rtt_ms: float | None
    packet_loss: float

_LOSS = re.compile(r"(\d+(?:\.\d+)?)% packet loss", re.IGNORECASE)
_PACKETS = re.compile(r"(\d+)\s+packets transmitted,\s*(\d+)\s+(?:packets\s+)?received", re.IGNORECASE)
_REPLY = re.compile(r"\d+\s+bytes from\s+", re.IGNORECASE)
_REPLY_RTT = re.compile(r"\b(?:time|tiempo)[=<]\s*([\d.]+)\s*ms", re.IGNORECASE)
_RTT = re.compile(r"= [\d.]+/([\d.]+)/")

async def ping(ip: str, count: int = 3, timeout_s: int = 1) -> ProbeResult:
    proc = await asyncio.create_subprocess_exec(
        "ping", "-n", "-c", str(count), "-i", "0.3", "-W", str(timeout_s), ip,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=count * (timeout_s + 1) + 3)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return ProbeResult(False, None, 100.0)

    text = out.decode(errors="replace")
    error_text = err.decode(errors="replace")
    success = proc.returncode == 0 or bool(_REPLY.search(text))
    loss_m = _LOSS.search(text)
    packet_m = _PACKETS.search(text)
    if loss_m:
        loss = float(loss_m.group(1))
    elif packet_m and int(packet_m.group(1)) > 0:
        sent, received = int(packet_m.group(1)), int(packet_m.group(2))
        loss = max(0.0, (sent - received) * 100.0 / sent)
    else:
        loss = 0.0 if success else 100.0
    rtt_m = _REPLY_RTT.search(text) or _RTT.search(text)
    rtt = float(rtt_m.group(1)) if rtt_m else None
    if proc.returncode not in (0, 1) and not success and error_text.strip():
        return ProbeResult(success=False, rtt_ms=None, packet_loss=100.0)
    return ProbeResult(success=success, rtt_ms=rtt, packet_loss=loss)
