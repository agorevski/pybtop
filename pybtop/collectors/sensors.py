"""Temperatures from hwmon and GPUs via NVML."""

from __future__ import annotations

import ctypes
import glob
import os
from dataclasses import dataclass, field

HWMON_DIR = "/sys/class/hwmon"


@dataclass
class Temperature:
    label: str
    celsius: float


@dataclass
class SensorChip:
    name: str
    temps: list[Temperature] = field(default_factory=list)


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return None


def read_hwmon_chips(root: str = HWMON_DIR) -> list[SensorChip]:
    chips: list[SensorChip] = []
    for hwmon in sorted(glob.glob(os.path.join(root, "hwmon*"))):
        name = _read_text(os.path.join(hwmon, "name")) or os.path.basename(hwmon)
        chip = SensorChip(name=name)
        for input_path in sorted(glob.glob(os.path.join(hwmon, "temp*_input"))):
            raw = _read_text(input_path)
            if raw is None:
                continue
            try:
                celsius = int(raw) / 1000.0
            except ValueError:
                continue
            label_path = input_path[: -len("_input")] + "_label"
            label = _read_text(label_path) or os.path.basename(input_path)[: -len("_input")]
            chip.temps.append(Temperature(label=label, celsius=celsius))
        if chip.temps:
            chips.append(chip)
    return chips


CPU_CHIP_NAMES = ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz")


def cpu_package_temp(chips: list[SensorChip]) -> float | None:
    """Package/Tctl style CPU temperature, preferring the first known CPU sensor chip."""
    for wanted in CPU_CHIP_NAMES:
        for chip in chips:
            if chip.name != wanted:
                continue
            for temp in chip.temps:
                label = temp.label.lower()
                if label.startswith("package") or label in ("tctl", "tdie", "cpu"):
                    return temp.celsius
            return chip.temps[0].celsius
    return None


def core_temps(chips: list[SensorChip]) -> dict[int, float]:
    """Per-core temperatures from coretemp-style 'Core N' labels."""
    result: dict[int, float] = {}
    for chip in chips:
        if chip.name != "coretemp":
            continue
        for temp in chip.temps:
            if temp.label.lower().startswith("core "):
                try:
                    result[int(temp.label.split()[1])] = temp.celsius
                except (IndexError, ValueError):
                    continue
    return result


def read_core_ids(path: str = "/proc/cpuinfo") -> dict[int, int]:
    """Processor id -> physical core id, from /proc/cpuinfo ('processor' and 'core id' lines)."""
    mapping: dict[int, int] = {}
    processor = None
    try:
        with open(path, encoding="ascii", errors="replace") as fh:
            for line in fh:
                key, _, value = line.partition(":")
                key = key.strip()
                if key == "processor":
                    processor = int(value)
                elif key == "core id" and processor is not None:
                    mapping[processor] = int(value)
    except (OSError, ValueError):
        pass
    return mapping


# NVML binding (libnvidia-ml), loaded lazily like btop does with dlopen.

NVML_SUCCESS = 0
NVML_TEMPERATURE_GPU = 0
NVML_CLOCK_GRAPHICS = 0
NVML_CLOCK_MEM = 2


class _Utilization(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class _MemoryInfo(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]


@dataclass
class GpuInfo:
    index: int
    name: str
    util_percent: float | None
    mem_util_percent: float | None
    mem_used: int | None
    mem_total: int | None
    temp_c: float | None
    power_watts: float | None
    clock_mhz: float | None
    mem_clock_mhz: float | None


class NvidiaGpus:
    """Snapshot reader for NVIDIA GPUs through NVML. Missing libraries yield an empty list."""

    LIB_NAMES = ("libnvidia-ml.so.1", "libnvidia-ml.so")

    def __init__(self) -> None:
        self._lib = None
        self._handles: list[ctypes.c_void_p] = []
        self._names: list[str] = []
        self._load()

    def _load(self) -> None:
        for name in self.LIB_NAMES:
            try:
                lib = ctypes.CDLL(name)
            except OSError:
                continue
            try:
                if lib.nvmlInit_v2() != NVML_SUCCESS:
                    return
                count = ctypes.c_uint(0)
                if lib.nvmlDeviceGetCount_v2(ctypes.byref(count)) != NVML_SUCCESS:
                    return
                for i in range(count.value):
                    handle = ctypes.c_void_p()
                    if lib.nvmlDeviceGetHandleByIndex_v2(ctypes.c_uint(i), ctypes.byref(handle)) == NVML_SUCCESS:
                        self._handles.append(handle)
                self._lib = lib
            except AttributeError:
                return
            return

    @property
    def available(self) -> bool:
        return self._lib is not None and bool(self._handles)

    def read(self) -> list[GpuInfo]:
        if not self.available:
            return []
        lib = self._lib
        gpus: list[GpuInfo] = []
        for index, handle in enumerate(self._handles):
            name_buf = ctypes.create_string_buffer(96)
            name = name_buf.value.decode() if lib.nvmlDeviceGetName(handle, name_buf, 96) == NVML_SUCCESS else f"GPU {index}"

            util = _Utilization()
            util_ok = lib.nvmlDeviceGetUtilizationRates(handle, ctypes.byref(util)) == NVML_SUCCESS

            mem = _MemoryInfo()
            mem_ok = lib.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(mem)) == NVML_SUCCESS

            temp = ctypes.c_uint(0)
            temp_ok = lib.nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU, ctypes.byref(temp)) == NVML_SUCCESS

            power = ctypes.c_uint(0)
            power_ok = lib.nvmlDeviceGetPowerUsage(handle, ctypes.byref(power)) == NVML_SUCCESS

            clock = ctypes.c_uint(0)
            clock_ok = lib.nvmlDeviceGetClockInfo(handle, NVML_CLOCK_GRAPHICS, ctypes.byref(clock)) == NVML_SUCCESS

            mem_clock = ctypes.c_uint(0)
            mem_clock_ok = lib.nvmlDeviceGetClockInfo(handle, NVML_CLOCK_MEM, ctypes.byref(mem_clock)) == NVML_SUCCESS

            gpus.append(
                GpuInfo(
                    index=index,
                    name=name,
                    util_percent=float(util.gpu) if util_ok else None,
                    mem_util_percent=float(util.memory) if util_ok else None,
                    mem_used=int(mem.used) if mem_ok else None,
                    mem_total=int(mem.total) if mem_ok else None,
                    temp_c=float(temp.value) if temp_ok else None,
                    power_watts=power.value / 1000.0 if power_ok else None,
                    clock_mhz=float(clock.value) if clock_ok else None,
                    mem_clock_mhz=float(mem_clock.value) if mem_clock_ok else None,
                )
            )
        return gpus

    def close(self) -> None:
        if self._lib is not None:
            try:
                self._lib.nvmlShutdown()
            except AttributeError:
                pass
            self._lib = None
