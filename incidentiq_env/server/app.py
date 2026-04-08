from fastapi.responses import RedirectResponse
from openenv.core.env_server.http_server import create_app
from openenv.core.env_server.mcp_types import CallToolAction, CallToolObservation

from .incidentiq_environment import IncidentIQEnvironment

app = create_app(
    IncidentIQEnvironment,
    CallToolAction,
    CallToolObservation,
    env_name="incidentiq_env",
)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


def main():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7860)


if __name__ == "__main__":
    main()
