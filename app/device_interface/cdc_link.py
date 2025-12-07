"""
Common USB CDC link helpers for STM32 device.

Exposes:
- DEFAULT_BAUD, DEFAULT_TIMEOUT
- auto_detect_port(): robust port selection using product/manufacturer or VID/PID
- list_serial_ports(): enumerate available ports with metadata
- CdcLink: minimal serial wrapper with jwrb()
"""
from __future__ import annotations

import time
from typing import Optional, List, Dict, Any

DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 1.0


def auto_detect_port(
    prefer_product: str = "Shabrang",
    prefer_manufacturer: str = "Black Horse Audio",
    fallback_vid: int = 0x0483,
    fallback_pid: int = 0x5740,
) -> str:
    """Pick the first serial port matching our device identity.

    Priority:
      1) product contains prefer_product OR manufacturer contains prefer_manufacturer
      2) vid/pid match fallback_vid/fallback_pid
      3) description hints: CDC/ACM/STM32
    Returns empty string if none found.
    """
    try:
        from serial.tools import list_ports
    except Exception:
        return ""

    ports = list(list_ports.comports())
    if not ports:
        return ""

    pp = (prefer_product or "").lower()
    pm = (prefer_manufacturer or "").lower()

    # Primary match by strings
    for p in ports:
        prod = (p.product or "").lower()
        manf = (p.manufacturer or "").lower()
        if (pp and pp in prod) or (pm and pm in manf):
            return p.device

    # Fallback match by VID/PID
    for p in ports:
        try:
            if (p.vid == fallback_vid) and (p.pid == fallback_pid):
                return p.device
        except Exception:
            pass

    # Heuristic fallback by description keywords
    for p in ports:
        desc = ((p.description or "") + " " + (p.manufacturer or "") + " " + (p.product or "")).lower()
        if any(tag in desc for tag in ["cdc", "acm", "stm32", "usb serial", "ux_device_cdc_acm"]):
            return p.device

    return ""


def list_serial_ports() -> List[Dict[str, Any]]:
    """List serial ports with metadata typical to pyserial list_ports.

    Returns a list of dicts with keys: device, description, manufacturer, product, vid, pid.
    """
    try:
        from serial.tools import list_ports
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for p in list_ports.comports():
        out.append({
            "device": getattr(p, "device", ""),
            "description": getattr(p, "description", ""),
            "manufacturer": getattr(p, "manufacturer", ""),
            "product": getattr(p, "product", ""),
            "vid": getattr(p, "vid", None),
            "pid": getattr(p, "pid", None),
        })
    return out


class CdcLink:
    def __init__(self, port: str, baud: int = DEFAULT_BAUD, timeout: float = DEFAULT_TIMEOUT):
        try:
            import serial  # lazy import
        except Exception as e:
            raise RuntimeError("pyserial is required; install with 'pip install pyserial'") from e
        self._serial_mod = serial
        self.ser = serial.Serial(
            port=port,
            baudrate=baud,
            timeout=timeout,
            write_timeout=timeout,
            xonxoff=False,
        )
        try:
            self.ser.exclusive = True  # type: ignore[attr-defined]
        except Exception:
            pass
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        time.sleep(0.05)

    def close(self):
        try:
            self.ser.reset_output_buffer()
            self.ser.reset_input_buffer()
        except Exception:
            pass
        try:
            if hasattr(self.ser, "cancel_read"):
                self.ser.cancel_read()
            if hasattr(self.ser, "cancel_write"):
                self.ser.cancel_write()
        except Exception:
            pass
        try:
            self.ser.close()
        except Exception:
            pass

    def _write_line(self, s: str):
        data = (s + "\r\n").encode("ascii")
        self.ser.write(data)
        self.ser.flush()
        time.sleep(0.005)

    def _read_line(self) -> str:
        ln = self.ser.readline()
        if not ln:
            return ""
        try:
            return ln.decode("utf-8", errors="ignore").strip()
        except Exception:
            return ""

    def jwrb(self, typ: int, _id: int, payload: bytes, ready_timeout: float = DEFAULT_TIMEOUT) -> bool:
        if not payload:
            return False
        self.ser.reset_input_buffer()
        self._write_line(f"!jwrb {typ:#x} {_id:#x} {len(payload)}")
        # Wait for READY
        t0 = time.time(); ready = False
        while time.time() - t0 < ready_timeout:
            ln = self._read_line()
            if not ln:
                continue
            if ln.startswith("OK JWRB READY"):
                ready = True; break
            if ln.startswith("ERR"):
                return False
        if not ready:
            return False
        # Send payload and wait for final status
        self.ser.write(payload)
        self.ser.flush()
        t0 = time.time(); status = ""
        while time.time() - t0 < (DEFAULT_TIMEOUT * 5):
            ln = self._read_line()
            if not ln:
                continue
            if ln in ("OK JWR", "ERR JWR"):
                status = ln; break
        return status == "OK JWR"

    def jwrb_with_log(self, typ: int, _id: int, payload: bytes, ready_timeout: float = DEFAULT_TIMEOUT) -> tuple[bool, list[str]]:
        """Like jwrb(), but returns any lines seen while waiting (including APPLY)."""
        lines: list[str] = []
        if not payload:
            return False, lines
        self.ser.reset_input_buffer()
        self._write_line(f"!jwrb {typ:#x} {_id:#x} {len(payload)}")
        # Wait for READY
        t0 = time.time(); ready = False
        while time.time() - t0 < ready_timeout:
            ln = self._read_line()
            if not ln:
                continue
            lines.append(ln)
            if ln.startswith("OK JWRB READY"):
                ready = True; break
            if ln.startswith("ERR"):
                return False, lines
        if not ready:
            return False, lines
        # Send payload and wait for final status
        self.ser.write(payload)
        self.ser.flush()
        t0 = time.time(); status = ""
        while time.time() - t0 < (DEFAULT_TIMEOUT * 5):
            ln = self._read_line()
            if not ln:
                continue
            lines.append(ln)
            if ln in ("OK JWR", "ERR JWR"):
                status = ln; break
        return status == "OK JWR", lines

    # ------------ Optional helpers mirrored from host tester ------------
    def init(self) -> bool:
        self._write_line("!ei")
        # Read lines until a final OK/ERR appears
        t0 = time.time(); status = ""
        while time.time() - t0 < DEFAULT_TIMEOUT * 3:
            ln = self._read_line()
            if not ln:
                continue
            if ln.startswith("OK ") or ln.startswith("ERR "):
                status = ln
        return status.startswith("OK")

    def jrd(self, typ: int, _id: int, collect_timeout: float = DEFAULT_TIMEOUT) -> bytes | None:
        self._write_line(f"!jrd {typ:#x} {_id:#x}")
        # Step 1: read header
        old_timeout = self.ser.timeout
        try:
            self.ser.timeout = 0.05
            expected = None
            t0 = time.time()
            while (time.time() - t0) < (collect_timeout * 3):
                ln = self._read_line()
                if not ln:
                    continue
                if ln.startswith("ERR JNF"):
                    return None
                if ln.startswith("OK JRD"):
                    parts = ln.split()
                    try:
                        expected = int(parts[-1], 0)
                        break
                    except Exception:
                        return b""
            if expected is None or expected <= 0:
                return b""
            # Step 2: hex tokens until expected
            tokens: List[str] = []
            self.ser.timeout = 0.02
            t_last = time.time()
            while len(tokens) < expected and (time.time() - t_last) < (collect_timeout * 3):
                ln = self._read_line()
                if not ln:
                    continue
                t_last = time.time()
                if ln.startswith('!') or ln.startswith('OK ') or ln.startswith('ERR '):
                    continue
                parts = [p for p in ln.strip().split(' ') if p]
                for p in parts:
                    if len(p) <= 2 and all(c in "0123456789ABCDEFabcdef" for c in p):
                        tokens.append(p)
                        if len(tokens) >= expected:
                            break
            if len(tokens) < expected:
                return b""
            return bytes(int(t, 16) for t in tokens[:expected])
        finally:
            self.ser.timeout = old_timeout

    def jrdb(self, typ: int, _id: int, timeout: float = DEFAULT_TIMEOUT) -> bytes | None:
        self._write_line(f"!jrdb {typ:#x} {_id:#x}")
        old_timeout = self.ser.timeout
        try:
            self.ser.timeout = 0.05
            expected = None
            t0 = time.time()
            while (time.time() - t0) < (timeout * 3):
                ln = self._read_line()
                if not ln:
                    continue
                if ln.startswith("ERR JNF"):
                    return None
                if ln.startswith("OK JRDB"):
                    parts = ln.split()
                    try:
                        expected = int(parts[-1], 0)
                        break
                    except Exception:
                        pass
            if expected is None or expected <= 0:
                return b""
            # Read exactly expected raw bytes
            self.ser.timeout = 0.2
            remaining = expected
            chunks: list[bytes] = []
            t_last = time.time()
            while remaining > 0 and (time.time() - t_last) < (timeout * 5):
                b = self.ser.read(remaining)
                if not b:
                    continue
                chunks.append(b)
                remaining -= len(b)
                t_last = time.time()
            if remaining != 0:
                return b""
            return b"".join(chunks)
        finally:
            self.ser.timeout = old_timeout

    def read_lines(self, duration: float = 0.5) -> list[str]:
        """Read and return lines for up to 'duration' seconds (non-blocky)."""
        end_time = time.time() + max(0.0, duration)
        old_timeout = self.ser.timeout
        lines: list[str] = []
        try:
            self.ser.timeout = 0.05
            while time.time() < end_time:
                ln = self._read_line()
                if not ln:
                    continue
                lines.append(ln)
        finally:
            self.ser.timeout = old_timeout
        return lines

    def i2c_write(self, addr7: int, reg: int, val: int) -> bool:
        """Single I2C register write via !i2cw <addr7> <reg> <val>."""
        if not (0 <= addr7 <= 0x7F and 0 <= reg <= 0xFF and 0 <= val <= 0xFF):
            raise ValueError("addr7 0..0x7F, reg/val 0..0xFF")
        self._write_line(f"!i2cw {addr7:#x} {reg:#x} {val:#x}")
        end_time = time.time() + DEFAULT_TIMEOUT
        while time.time() < end_time:
            ln = self._read_line()
            if not ln:
                continue
            if ln == "OK I2CW":
                return True
            if ln.startswith("ERR"):
                return False
        return False

    def esr(self, addr: int) -> int | None:
        """Read one ES9821 register via !esr <addr>. Returns byte value or None on error."""
        if addr < 0 or addr > 0xFF:
            raise ValueError("ES9821 register must be 0..255")
        self._write_line(f"!esr {addr:#x}")
        # look for OK ESR 0xAA 0xVV
        end_time = time.time() + DEFAULT_TIMEOUT
        while time.time() < end_time:
            ln = self._read_line()
            if not ln:
                continue
            if ln.startswith("OK ESR"):
                parts = ln.split()
                if len(parts) >= 4:
                    try:
                        val = int(parts[3], 0)
                        return val
                    except Exception:
                        break
            if ln.startswith("ERR"):
                return None
        return None
