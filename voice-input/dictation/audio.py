"""音频采集：自动找到板子提供的 USB 麦克风（CherryUSB UAC），并输出 16 kHz 单声道 float32。"""

from __future__ import annotations

import math
import queue
import time

import numpy as np
import sounddevice as sd

TARGET_SR = 16000

# Windows 上同一个物理设备会在不同 host API 下重复出现，按这个顺序优先后者失败再换前者
_HOSTAPI_PRIORITY = ("Windows WASAPI", "MME", "Windows DirectSound", "Windows WDM-KS")


def list_hostapis() -> list[str]:
    return [str(h["name"]) for h in sd.query_hostapis()]


def list_input_devices(keyword: str = "") -> list[dict]:
    """返回可用的输入设备，附带 host API 名称与优先级。"""
    hostapis = list_hostapis()
    devices = []
    for index, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] <= 0:
            continue
        name = str(dev["name"])
        if keyword and keyword.lower() not in name.lower():
            continue
        api = hostapis[dev["hostapi"]] if dev["hostapi"] < len(hostapis) else ""
        devices.append(
            {
                "index": index,
                "name": name,
                "hostapi": api,
                "channels": int(dev["max_input_channels"]),
                "samplerate": int(dev["default_samplerate"]),
                "priority": _api_priority(api),
            }
        )
    devices.sort(key=lambda d: (d["priority"], -d["channels"], d["index"]))
    return devices


def _api_priority(api: str) -> int:
    for i, name in enumerate(_HOSTAPI_PRIORITY):
        if api == name:
            return i
    return len(_HOSTAPI_PRIORITY)


def _resample(samples: np.ndarray, sr_from: int, sr_to: int = TARGET_SR) -> np.ndarray:
    if sr_from == sr_to or samples.size == 0:
        return samples
    g = math.gcd(int(sr_from), int(sr_to))
    up, down = sr_to // g, sr_from // g
    try:
        from scipy.signal import resample_poly

        return resample_poly(samples, up, down).astype(np.float32)
    except Exception:  # noqa: BLE001 - scipy 不可用时退回线性插值
        n = int(round(len(samples) * sr_to / sr_from))
        if n <= 0:
            return np.zeros(0, dtype=np.float32)
        src = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
        dst = np.linspace(0.0, 1.0, num=n, endpoint=False)
        return np.interp(dst, src, samples).astype(np.float32)


class MicCapture:
    """持续采集麦克风，read() 返回 16 kHz 单声道 float32。"""

    def __init__(
        self,
        keyword: str = "CherryUSB",
        device_index: int = -1,
        channel: int = 0,
        gain: float = 1.0,
        fallback: bool = False,
    ) -> None:
        self.keyword = keyword
        self.device_index = device_index
        self.channel = channel
        self.gain = max(0.1, float(gain))
        self.fallback = bool(fallback)
        self._stream: sd.InputStream | None = None
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=400)
        self._native_sr = TARGET_SR
        self._channels = 1
        self._last_block_at = 0.0
        self.device_label = ""
        self.last_error = ""
        self._agc = 1.0

    # ---- 生命周期 -------------------------------------------------
    def start(self) -> str:
        self.stop()
        candidates = self._candidates()
        if not candidates:
            if self.keyword:
                hint = f"没有找到名字里带「{self.keyword}」的麦克风。"
            else:
                hint = "没有找到可用的麦克风。"
            raise RuntimeError(
                hint
                + "请确认板子已插好（设备管理器里应出现 CherryUSB UAC1 Audio）。"
                + ("" if self.fallback else "为了确保只使用板子，程序不会自动改用电脑自带麦克风。")
            )
        errors = []
        for dev_index, samplerate, channels in candidates:
            try:
                self._open(dev_index, samplerate, channels)
                return self.device_label
            except Exception as exc:  # noqa: BLE001
                errors.append(f"设备{dev_index} {samplerate}Hz {channels}ch: {exc}")
        raise RuntimeError("打开麦克风失败：\n" + "\n".join(errors[-4:]))

    def _candidates(self) -> list[tuple[int, int, int]]:
        if self.device_index >= 0:
            dev = sd.query_devices(self.device_index)
            ch = int(dev["max_input_channels"])
            sr = int(dev["default_samplerate"])
            return [(self.device_index, TARGET_SR, min(ch, 4)), (self.device_index, sr, min(ch, 4))]

        devices = list_input_devices(self.keyword)
        if not devices:
            if not self.fallback:
                return []
            default_index = sd.default.device[0]
            devices = [d for d in list_input_devices("") if d["index"] == default_index]
        out: list[tuple[int, int, int]] = []
        for dev in devices:
            ch = dev["channels"]
            usable = min(max(ch, 1), 4)
            out.append((dev["index"], TARGET_SR, usable))
            if dev["samplerate"] != TARGET_SR:
                out.append((dev["index"], dev["samplerate"], usable))
            if usable > 1:
                out.append((dev["index"], TARGET_SR, 1))
        return out

    def _open(self, dev_index: int, samplerate: int, channels: int) -> None:
        self._queue = queue.Queue(maxsize=400)
        stream = sd.InputStream(
            device=dev_index,
            samplerate=samplerate,
            channels=channels,
            dtype="int16",
            blocksize=int(samplerate * 0.05),
            callback=self._callback,
        )
        stream.start()
        # 等第一块数据，确认这个组合真的能出流
        deadline = time.time() + 1.2
        while time.time() < deadline and self._queue.empty():
            time.sleep(0.02)
        if self._queue.empty():
            stream.stop()
            stream.close()
            raise RuntimeError("打开后没有收到音频数据")
        self._stream = stream
        self._native_sr = int(samplerate)
        self._channels = int(channels)
        self._last_block_at = time.time()
        name = str(sd.query_devices(dev_index)["name"])
        api = list_hostapis()[sd.query_devices(dev_index)["hostapi"]]
        self.device_label = f"{name} [{api} {samplerate}Hz {channels}ch]"

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:  # noqa: BLE001
                pass
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    # ---- 数据 -----------------------------------------------------
    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            self.last_error = str(status)
        data = np.array(indata, dtype=np.int16, copy=True)
        self._last_block_at = time.time()
        try:
            self._queue.put_nowait(data)
        except queue.Full:
            pass

    def read(self, timeout: float = 0.5) -> np.ndarray | None:
        try:
            block = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
        if block.ndim > 1:
            ch = self.channel if self.channel < block.shape[1] else 0
            mono = block[:, ch]
        else:
            mono = block
        samples = mono.astype(np.float32) / 32768.0
        return _resample(self._auto_gain(samples), self._native_sr)

    def _auto_gain(self, samples: np.ndarray) -> np.ndarray:
        """板子空闲时送出的麦克风电平很低：做一个起音快、释放慢的自动增益。"""
        if samples.size == 0:
            return samples
        peak = float(np.max(np.abs(samples)))
        target = 0.25
        if peak < 1e-4:
            desired = self.gain
        else:
            desired = min(self.gain, max(1.0, target / peak))
        if desired > self._agc:
            self._agc = desired          # 立刻跟上，别把开头吞掉
        else:
            self._agc += (desired - self._agc) * 0.05
        if abs(self._agc - 1.0) < 0.01:
            return samples
        return np.clip(samples * self._agc, -1.0, 1.0)

    def seconds_since_data(self) -> float:
        return time.time() - self._last_block_at if self._last_block_at else 1e9

    def alive(self) -> bool:
        return self._stream is not None and self._stream.active

    def device_present(self) -> bool:
        """板子是否还插着（USB 音频端点是否还在系统里）。"""
        try:
            if self.device_index >= 0:
                sd.query_devices(self.device_index)
                return True
            if self.keyword:
                return bool(list_input_devices(self.keyword))
            return True
        except Exception:  # noqa: BLE001
            return False
