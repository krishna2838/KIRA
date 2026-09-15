"""macOS Accessibility API via pyobjc.

Reads the UI element tree of the frontmost app. This is the *primary* method
for understanding what's on screen — structured data, no vision model.

Requires the running Python process to hold Accessibility permission
(System Settings → Privacy → Accessibility). If it doesn't, every call
returns `{"available": False, "reason": ...}`. The setup script prompts.
"""
from __future__ import annotations

from kira.logger import get_logger

from kira.tools.computer.util import is_macos


logger = get_logger("tools.computer.a11y")


def _AX():
    """Lazy-load the AX stack — heavy Objective-C imports."""
    if not is_macos():
        raise RuntimeError("Accessibility API is macOS-only")
    try:
        # These are provided by pyobjc-framework-Cocoa /
        # pyobjc-framework-ApplicationServices.
        import ApplicationServices  # type: ignore
        import AppKit  # type: ignore
        return ApplicationServices, AppKit
    except Exception as e:
        raise RuntimeError(
            "pyobjc frameworks missing "
            "(pip install pyobjc-framework-Cocoa pyobjc-framework-ApplicationServices): "
            f"{e}"
        ) from e


async def a11y_available() -> dict:
    try:
        ApplicationServices, _ = _AX()
    except RuntimeError as e:
        return {"available": False, "reason": str(e)}
    try:
        trusted = ApplicationServices.AXIsProcessTrusted()
    except Exception as e:
        return {"available": False, "reason": f"AXIsProcessTrusted failed: {e}"}
    return {
        "available": bool(trusted),
        "reason": None
        if trusted
        else "Accessibility permission not granted. Grant it in System Settings → Privacy → Accessibility.",
    }


async def frontmost_app_tree(max_depth: int = 4) -> dict:
    """Return the UI element tree of the frontmost app."""
    try:
        ApplicationServices, AppKit = _AX()
    except RuntimeError as e:
        return {"available": False, "reason": str(e)}

    try:
        workspace = AppKit.NSWorkspace.sharedWorkspace()
        front_app = workspace.frontmostApplication()
        if front_app is None:
            return {"available": True, "app": None, "tree": None}
        pid = front_app.processIdentifier()
        ax_app = ApplicationServices.AXUIElementCreateApplication(pid)
        tree = _dump(ApplicationServices, ax_app, depth=0, max_depth=max_depth)
        return {
            "available": True,
            "app": {
                "name": str(front_app.localizedName()),
                "bundle": str(front_app.bundleIdentifier() or ""),
                "pid": int(pid),
            },
            "tree": tree,
        }
    except Exception as e:
        logger.debug(f"a11y tree failed: {e}")
        return {"available": False, "reason": str(e)}


def _copy_attr(ApplicationServices, elem, name: str):
    try:
        err, value = ApplicationServices.AXUIElementCopyAttributeValue(
            elem, name, None
        )
        return value if err == 0 else None
    except Exception:
        return None


def _dump(ApplicationServices, elem, depth: int, max_depth: int) -> dict:
    role = _copy_attr(ApplicationServices, elem, "AXRole")
    title = _copy_attr(ApplicationServices, elem, "AXTitle")
    value = _copy_attr(ApplicationServices, elem, "AXValue")
    label = _copy_attr(ApplicationServices, elem, "AXDescription")
    enabled = _copy_attr(ApplicationServices, elem, "AXEnabled")
    node: dict = {
        "role": str(role) if role else None,
        "title": str(title) if title else None,
        "value": str(value)[:200] if value is not None else None,
        "description": str(label) if label else None,
        "enabled": bool(enabled) if enabled is not None else None,
    }
    if depth >= max_depth:
        return node
    children = _copy_attr(ApplicationServices, elem, "AXChildren")
    if children:
        # `children` is an NSArray of AXUIElementRefs.
        node_children = []
        for i, ch in enumerate(children):
            if i >= 40:  # cap breadth
                break
            node_children.append(
                _dump(ApplicationServices, ch, depth + 1, max_depth)
            )
        if node_children:
            node["children"] = node_children
    return node
