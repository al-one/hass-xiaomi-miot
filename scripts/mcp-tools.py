import yaml
import requests
from fastmcp import FastMCP
from pydantic import Field

mcp = FastMCP(name="mcp-tools")


@mcp.tool(
    description="Get the miot specifications of the specified device, including all services and properties",
)
def device_specs(
    model: str = Field(description="Device model. e.g. xiaomi.light.color1"),
):
    res = requests.get(f"https://home.miot-spec.com/spec/{model}", params={"ajax": 1})
    try:
        return yaml.dump(res.json())
    except Exception:
        return res.text


mcp.run()