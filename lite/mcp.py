"""A read-only MCP window onto what Titan knows, for a TiinyOS custom connector.

SPEC.md step 6 offers this second form: register Lite as a custom MCP connector so the
device's own chat can reach Titan's memory and skills. docs/tiiny-platform.md section 8
names the one documented bridge, a custom MCP connector run on the computer rather than
on the device, and section 2 records that connector actions run inside TiinyOS Task Mode.

It answers JSON-RPC 2.0 over one HTTP POST, which is the plain half of MCP's streamable
HTTP transport. Nothing here writes: a memory or a skill can be read, never changed, so
the worst a stranger who reaches the port can do is read what the console already shows.
"""
import json

from . import __version__

PROTOCOL = "2025-06-18"
SERVER_NAME = "titanium-tiiny-bot"

TOOLS = [
    {
        "name": "titan_memories",
        "description": "List the facts Titan has saved about its owner. Optionally filter by a word.",
        "inputSchema": {
            "type": "object",
            "properties": {"search": {"type": "string", "description": "Only facts containing this text."}},
            "required": [],
        },
    },
    {
        "name": "titan_skills",
        "description": "List Titan's skills, each with the name and description from its SKILL.md.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "titan_skill",
        "description": "Read one of Titan's skills in full. Use the id from titan_skills.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "The skill's folder name."}},
            "required": ["id"],
        },
    },
]


def descriptor(origin, enabled=True):
    """What a person copies into TiinyOS Settings > Connectors to add this connector.

    The field names their import expects are not published, so the address is the part
    that matters; docs/tiiny-platform.md D6 is the only source and it has no schema.
    """
    return {
        "name": "Titan",
        "description": "Titan's memory and skills, from Titanium Tiiny Bot on this computer.",
        "enabled": bool(enabled),
        "transport": "http",
        "runEnvironment": "Computer",
        "url": origin.rstrip("/") + "/mcp" if origin else "/mcp",
        "protocolVersion": PROTOCOL,
        "tools": [tool["name"] for tool in TOOLS],
    }


def text_result(text, is_error=False):
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def call_tool(app, name, arguments):
    library = app.library()
    if name == "titan_memories":
        search = str(arguments.get("search") or "").strip().lower()
        facts = [m["name"] for m in library["memories"] if search in m["name"].lower()]
        if not facts:
            return text_result("Titan has not saved anything matching that yet.")
        return text_result("\n".join("- " + fact for fact in facts))
    if name == "titan_skills":
        skills = library["skills"]
        if not skills:
            return text_result("Titan has no skills yet.")
        return text_result("\n".join(
            f'{skill["id"]}: {skill["name"]} - {skill["description"]}' for skill in skills))
    if name == "titan_skill":
        ident = str(arguments.get("id") or "")
        skill = app.skill_markdown(ident)
        if skill is None:
            return text_result(f"There is no skill called {ident}.", True)
        return text_result(skill["body"])
    return text_result(f"There is no tool called {name}.", True)


def handle(app, body):
    """One JSON-RPC message in, one response out, or None for a notification."""
    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "Send a JSON-RPC 2.0 message."}}
    method = body.get("method")
    ident = body.get("id")
    if ident is None:
        return None  # A notification, such as notifications/initialized. Nothing to answer.
    if not isinstance(method, str):
        return {"jsonrpc": "2.0", "id": ident,
                "error": {"code": -32600, "message": "Send a method name."}}
    parameters = body.get("params") if isinstance(body.get("params"), dict) else {}
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": ident, "result": {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": __version__},
            "instructions": "Titan's saved facts and skills, read only.",
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": ident, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": ident, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = parameters.get("name")
        arguments = parameters.get("arguments") if isinstance(parameters.get("arguments"), dict) else {}
        if not isinstance(name, str):
            return {"jsonrpc": "2.0", "id": ident,
                    "error": {"code": -32602, "message": "Name the tool to call."}}
        return {"jsonrpc": "2.0", "id": ident, "result": call_tool(app, name, arguments)}
    return {"jsonrpc": "2.0", "id": ident,
            "error": {"code": -32601, "message": f"This connector has no {method} method."}}


def response_bytes(message):
    return json.dumps(message).encode("utf-8")
