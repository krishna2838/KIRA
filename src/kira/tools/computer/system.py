"""System introspection + toggles: battery, disk, wifi, volume, brightness, dark mode."""
from __future__ import annotations

import re
import shutil

from kira.tools.computer.util import is_macos, osascript, run


# ---- battery / disk / wifi ----------------------------------------------


async def get_battery() -> dict:
    if not is_macos():
        return {"available": False}
    rc, out, _ = await run(["pmset", "-g", "batt"])
    if rc != 0:
        return {"available": False}
    percent_match = re.search(r"(\d+)%", out)
    charging = "AC Power" in out or "charging" in out.lower()
    return {
        "available": True,
        "percent": int(percent_match.group(1)) if percent_match else None,
        "charging": charging,
    }


async def get_disk_space(path: str = "/") -> dict:
    total, used, free = shutil.disk_usage(path)
    return {
        "path": path,
        "total_gb": round(total / 1e9, 1),
        "used_gb": round(used / 1e9, 1),
        "free_gb": round(free / 1e9, 1),
        "percent_used": round(100 * used / total, 1),
    }


async def get_wifi_network() -> dict:
    if not is_macos():
        return {"ssid": None}
    # `networksetup -getairportnetwork <iface>` — try common Wi-Fi ifaces.
    for iface in ("en0", "en1"):
        rc, out, _ = await run(
            ["networksetup", "-getairportnetwork", iface], timeout=5.0
        )
        if rc == 0 and ":" in out:
            ssid = out.split(":", 1)[1].strip()
            if ssid and "not associated" not in ssid.lower():
                return {"ssid": ssid, "interface": iface}
    return {"ssid": None}


# ---- volume -------------------------------------------------------------


async def get_volume() -> dict:
    rc, out, _ = await osascript("output volume of (get volume settings)")
    if rc != 0:
        return {"volume": None}
    try:
        return {"volume": int(out.strip())}
    except ValueError:
        return {"volume": None}


async def set_volume(level: int) -> dict:
    level = max(0, min(100, int(level)))
    rc, _, err = await osascript(f"set volume output volume {level}")
    if rc != 0:
        return {"set": False, "error": err.strip() or f"exit {rc}"}
    return {"set": True, "volume": level}


# ---- brightness ---------------------------------------------------------


async def get_brightness() -> dict:
    if not is_macos():
        return {"brightness": None}
    # Uses the `brightness` third-party CLI if available; otherwise unknown.
    rc, out, _ = await run(["brightness", "-l"], timeout=3.0)
    if rc != 0:
        return {"brightness": None, "note": "brew install brightness for reads"}
    m = re.search(r"brightness\s+([0-9.]+)", out)
    if m:
        return {"brightness": float(m.group(1))}
    return {"brightness": None}


# ---- dark mode ----------------------------------------------------------


async def toggle_dark_mode() -> dict:
    rc, _, err = await osascript(
        'tell app "System Events" to tell appearance preferences to '
        'set dark mode to not dark mode'
    )
    if rc != 0:
        return {"toggled": False, "error": err.strip() or f"exit {rc}"}
    is_dark_rc, out, _ = await osascript(
        'tell app "System Events" to tell appearance preferences to get dark mode'
    )
    return {
        "toggled": True,
        "dark_mode": out.strip() == "true" if is_dark_rc == 0 else None,
    }
