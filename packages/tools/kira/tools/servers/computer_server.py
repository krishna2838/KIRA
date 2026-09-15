"""Computer control MCP server (in-process, macOS-first).

Consolidates app control, files, system introspection, screenshots, the
accessibility tree, and the clipboard into one server. Each tool wraps a
tiny primitive in `kira.tools.computer.*`.

Every tool routes through the executor; the permissions.py classifier maps
each qualified name to a risk level. Anything that mutates state is at
least L2, and permanent-delete is L4.
"""
from __future__ import annotations

from typing import Any

from kira.tools.computer import apps, clipboard, files, screen, system
from kira.tools.computer.accessibility import a11y_available, frontmost_app_tree
from kira.tools.servers.base import InternalServer, InternalTool


# ---- app control --------------------------------------------------------


async def _tool_list_running_apps(args: dict) -> Any:
    return {"apps": await apps.list_running_apps()}


async def _tool_open_app(args: dict) -> Any:
    return await apps.open_app(args["name"])


async def _tool_close_app(args: dict) -> Any:
    return await apps.close_app(args["name"])


async def _tool_switch_to_app(args: dict) -> Any:
    return await apps.switch_to_app(args["name"])


async def _tool_window_titles(args: dict) -> Any:
    return {"app": args["app"], "windows": await apps.window_titles(args["app"])}


# ---- files --------------------------------------------------------------


async def _tool_open_file(args: dict) -> Any:
    return await files.open_file(args["path"])


async def _tool_reveal_in_finder(args: dict) -> Any:
    return await files.reveal_in_finder(args["path"])


async def _tool_move_file(args: dict) -> Any:
    return await files.move_file(args["src"], args["dst"])


async def _tool_copy_file(args: dict) -> Any:
    return await files.copy_file(args["src"], args["dst"])


async def _tool_delete_file(args: dict) -> Any:
    if bool(args.get("permanent", False)):
        return await files.permanent_delete(args["path"])
    return await files.trash_file(args["path"])


async def _tool_search_files(args: dict) -> Any:
    return await files.search_files(
        args["query"],
        directory=args.get("directory"),
        max_results=int(args.get("max_results", 20)),
    )


# ---- system -------------------------------------------------------------


async def _tool_get_battery(args: dict) -> Any:
    return await system.get_battery()


async def _tool_get_disk_space(args: dict) -> Any:
    return await system.get_disk_space(args.get("path", "/"))


async def _tool_get_wifi_network(args: dict) -> Any:
    return await system.get_wifi_network()


async def _tool_get_volume(args: dict) -> Any:
    return await system.get_volume()


async def _tool_set_volume(args: dict) -> Any:
    return await system.set_volume(int(args["level"]))


async def _tool_get_brightness(args: dict) -> Any:
    return await system.get_brightness()


async def _tool_toggle_dark_mode(args: dict) -> Any:
    return await system.toggle_dark_mode()


async def _tool_system_status(args: dict) -> Any:
    """Convenience roll-up for the frontend Computer panel."""
    battery = await system.get_battery()
    disk = await system.get_disk_space("/")
    wifi = await system.get_wifi_network()
    vol = await system.get_volume()
    return {"battery": battery, "disk": disk, "wifi": wifi, "volume": vol}


# ---- clipboard ----------------------------------------------------------


async def _tool_get_clipboard(args: dict) -> Any:
    return await clipboard.get_clipboard()


async def _tool_set_clipboard(args: dict) -> Any:
    return await clipboard.set_clipboard(args["text"])


# ---- accessibility + screen -------------------------------------------


async def _tool_a11y_status(args: dict) -> Any:
    return await a11y_available()


async def _tool_ui_tree(args: dict) -> Any:
    return await frontmost_app_tree(max_depth=int(args.get("max_depth", 4)))


async def _tool_take_screenshot(args: dict) -> Any:
    return await screen.take_screenshot()


async def _tool_analyze_screenshot(args: dict) -> Any:
    return await screen.analyze_screenshot(args.get("question", "Describe what is on screen."))


# ---- server -------------------------------------------------------------


SERVER = InternalServer(
    name="computer",
    description="Control the Mac: apps, files, system settings, clipboard, screenshots, accessibility.",
    tools=[
        # apps
        InternalTool(
            name="list_running_apps",
            description="List names of all running non-background applications.",
            input_schema={"type": "object", "properties": {}},
            handler=_tool_list_running_apps,
        ),
        InternalTool(
            name="open_app",
            description="Open an application by name (e.g. 'Safari', 'VS Code').",
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            handler=_tool_open_app,
        ),
        InternalTool(
            name="close_app",
            description="Quit an application by name.",
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            handler=_tool_close_app,
        ),
        InternalTool(
            name="switch_to_app",
            description="Bring an application to the front.",
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            handler=_tool_switch_to_app,
        ),
        InternalTool(
            name="window_titles",
            description="Get the window titles of a running app.",
            input_schema={
                "type": "object",
                "properties": {"app": {"type": "string"}},
                "required": ["app"],
            },
            handler=_tool_window_titles,
        ),
        # files
        InternalTool(
            name="open_file",
            description="Open a file in its default macOS application.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            handler=_tool_open_file,
        ),
        InternalTool(
            name="reveal_in_finder",
            description="Show a file or folder in Finder.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            handler=_tool_reveal_in_finder,
        ),
        InternalTool(
            name="move_file",
            description="Move or rename a file/folder.",
            input_schema={
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "dst": {"type": "string"},
                },
                "required": ["src", "dst"],
            },
            handler=_tool_move_file,
        ),
        InternalTool(
            name="copy_file",
            description="Copy a file or folder.",
            input_schema={
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "dst": {"type": "string"},
                },
                "required": ["src", "dst"],
            },
            handler=_tool_copy_file,
        ),
        InternalTool(
            name="delete_file",
            description=(
                "Delete a file. By default moves to the Trash (recoverable). "
                "Set `permanent: true` for irrecoverable delete (CRITICAL — "
                "always confirm)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "permanent": {"type": "boolean", "default": False},
                },
                "required": ["path"],
            },
            handler=_tool_delete_file,
        ),
        InternalTool(
            name="search_files",
            description="Spotlight file search under an optional directory.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "directory": {"type": "string"},
                    "max_results": {"type": "integer", "default": 20},
                },
                "required": ["query"],
            },
            handler=_tool_search_files,
        ),
        # system
        InternalTool(
            name="get_battery",
            description="Read battery percentage and charging state.",
            input_schema={"type": "object", "properties": {}},
            handler=_tool_get_battery,
        ),
        InternalTool(
            name="get_disk_space",
            description="Get disk usage for a mount point (default /).",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "default": "/"}},
            },
            handler=_tool_get_disk_space,
        ),
        InternalTool(
            name="get_wifi_network",
            description="Get the current Wi-Fi SSID.",
            input_schema={"type": "object", "properties": {}},
            handler=_tool_get_wifi_network,
        ),
        InternalTool(
            name="get_volume",
            description="Get output volume (0–100).",
            input_schema={"type": "object", "properties": {}},
            handler=_tool_get_volume,
        ),
        InternalTool(
            name="set_volume",
            description="Set output volume (0–100).",
            input_schema={
                "type": "object",
                "properties": {"level": {"type": "integer", "minimum": 0, "maximum": 100}},
                "required": ["level"],
            },
            handler=_tool_set_volume,
        ),
        InternalTool(
            name="get_brightness",
            description="Get screen brightness (needs the `brightness` CLI).",
            input_schema={"type": "object", "properties": {}},
            handler=_tool_get_brightness,
        ),
        InternalTool(
            name="toggle_dark_mode",
            description="Toggle macOS dark mode.",
            input_schema={"type": "object", "properties": {}},
            handler=_tool_toggle_dark_mode,
        ),
        InternalTool(
            name="system_status",
            description="Roll-up: battery + disk + wifi + volume in one call.",
            input_schema={"type": "object", "properties": {}},
            handler=_tool_system_status,
        ),
        # clipboard
        InternalTool(
            name="get_clipboard",
            description="Read the current clipboard as text.",
            input_schema={"type": "object", "properties": {}},
            handler=_tool_get_clipboard,
        ),
        InternalTool(
            name="set_clipboard",
            description="Set the clipboard text.",
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            handler=_tool_set_clipboard,
        ),
        # accessibility + screen
        InternalTool(
            name="a11y_status",
            description="Report whether macOS Accessibility permission is granted.",
            input_schema={"type": "object", "properties": {}},
            handler=_tool_a11y_status,
        ),
        InternalTool(
            name="ui_tree",
            description=(
                "Return the structured UI element tree of the frontmost app "
                "via the macOS Accessibility API — preferred over screenshots."
            ),
            input_schema={
                "type": "object",
                "properties": {"max_depth": {"type": "integer", "default": 4}},
            },
            handler=_tool_ui_tree,
        ),
        InternalTool(
            name="take_screenshot",
            description="Capture the current screen and return it as base64 PNG.",
            input_schema={"type": "object", "properties": {}},
            handler=_tool_take_screenshot,
        ),
        InternalTool(
            name="analyze_screenshot",
            description=(
                "Take a screenshot and ask the vision model to answer a "
                "question about what's on screen. Fallback when the UI tree "
                "isn't enough."
            ),
            input_schema={
                "type": "object",
                "properties": {"question": {"type": "string"}},
            },
            handler=_tool_analyze_screenshot,
        ),
    ],
)
