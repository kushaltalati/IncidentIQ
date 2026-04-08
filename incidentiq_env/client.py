from openenv.core.mcp_client import MCPToolClient


class IncidentIQEnv(MCPToolClient):
    """
    Client for the IncidentIQ SRE Incident Response Environment.

    Provides MCP tool-calling interface for interacting with the environment.
    Inherits all functionality from MCPToolClient:
    - list_tools(): Discover available tools
    - call_tool(name, **kwargs): Call a tool by name
    - reset(**kwargs): Reset the environment
    - step(action): Execute an action

    Example:
        >>> with IncidentIQEnv(base_url="http://localhost:8000").sync() as env:
        ...     env.reset(task_mode="alert_triage")
        ...     instructions = env.call_tool("get_instructions")
        ...     result = env.call_tool("classify_root_cause",
        ...                            root_cause="OOM", severity="P1")
    """

    pass
