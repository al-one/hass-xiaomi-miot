---
name: miot-docs
description: Xiaomi Miot documentation and helper. Recommended to use when users submit an issue/PR.
---

# Xiaomi Miot

## Ask deepwiki
```bash
npx -y mcporter call mcp.deepwiki.com/mcp.ask_question --timeout 120000 --args '{
  "repoName": "al-one/hass-xiaomi-miot",
  "question": "How to adding entities to a device ?"
}'
```

## MCP Tools
```bash
# List MCP servers
npx -y mcporter --config .mcp.json list

# List MCP tools
npx -y mcporter --config .mcp.json list <server_name>
npx -y mcporter --config .mcp.json list tools

# Call MCP tool
npx -y mcporter --config .mcp.json call <server>.<tool> --args '{"key":"val"}'
npx -y mcporter --config .mcp.json call tools.device_specs --args '{"model":"brand.type.model"}'
```

## About `mcporter`
To improve compatibility, use `npx -y mcporter` instead of `mcporter` when executing commands.


## Adding entities to a Device
To adding entities to a device in the Xiaomi MIoT integration, you'll need to modify the `DEVICE_CUSTOMIZES` dictionary in the `device_customizes.py` file.

### Add Your Device Configuration
Add your device model to the `DEVICE_CUSTOMIZES` dictionary following the existing pattern:
```python
DEVICE_CUSTOMIZES = {
    # ... existing devices ...
    'your.device.model': {
        'sensor_properties': 'temperature,relative_humidity',
        'switch_properties': 'uv,switch',
        'select_properties': 'mode',
        # Add more entity mappings as needed
    },
}
```

### Available Entity Mapping Options
> More customization options can be found at https://github.com/al-one/hass-xiaomi-miot/issues/600

| Option | Description | Example |
|--------|-------------|---------|
| `sensor_properties` | Properties to expose as sensors | `temperature,humidity` |
| `binary_sensor_properties` | Properties to expose as binary sensors | `motion_detected,door_state` |
| `switch_properties` | Properties to expose as switches | `on,night_light` |
| `select_properties` | Properties to expose as selects | `mode,fan_level` |
| `number_properties` | Properties to expose as numbers | `target_temperature,volume` |
| `button_actions` | Actions to expose as buttons | `reset_filter_life` |

### Finding Property Names
To find the correct property names for your device:
1. Use `tools.device_specs` MCP tool to get device specifications
2. Look at the available services and properties
3. Replace hyphens (`-`) with underscores (`_`) in service/property/action names

## Notes
- Consider using `exclude_miot_properties` to improve performance by excluding unused properties
- For complex devices, you can use `chunk_coordinators` to optimize polling intervals
- Pattern matching is supported (e.g., `*.aircondition.*` for all air conditioners)
