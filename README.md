# MonKey Office Connect MCP Server

This is a Model Context Protocol (MCP) server that allows AI assistants (like Hermes Agent) to interact with **MonKey Office 2026** via the **MonKey Office Connect JSON-API**.

## Features

The server provides several tools to read and write accounting data:

- **Read Access**: List companies, retrieve bookings within a time range, get detailed booking info, and list available tax rates.
- **Write Access**: Create new bookings with multiple positions, attach PDF documents to bookings, and perform batch imports of bookings.
- **Validation**: Includes a check to ensure MonKey Office 2026 is installed on the host system.

## Requirements

- **MonKey Office 2026** installed and running.
- **MonKey Office Connect** configured and active (default endpoint: `http://127.0.0.1:8084/monkeyOfficeConnectJSON`).
- **Python 3.10+**
- Libraries: `mcp`, `requests`

## Setup

### 1. Install Dependencies
```bash
pip install mcp requests
```

### 2. Configuration
The server is configured entirely via environment variables. You must set the following:

| Variable | Description | Required | Default |
|---|---|---|---|
| `MONKEY_API_USER` | API username for MonKey Office Connect | Yes | - |
| `MONKEY_API_PASS` | API password for MonKey Office Connect | Yes | - |
| `MONKEY_FIRMA_NAME` | The exact name of the database/company to use | Yes | - |
| `MONKEY_API_URL` | Connect JSON-API endpoint | No | `http://127.0.0.1:8084/monkeyOfficeConnectJSON` |
| `MONKEY_APP_PATH` | Path to MonKey Office 2026.app | No | `/Applications/MonKey Office 2026.app` |
| `MONKEY_LOG_FILE` | Path to the log file | No | `/tmp/monkey_office_mcp.log` |

### 3. Integration with Hermes Agent
Add the server to your `config.yaml`:

```yaml
mcp_servers:
  monkey_office:
    command: "python" # or absolute path to your venv python
    args:
      - "/path/to/monkey_office_mcp_server.py"
    env:
      MONKEY_API_USER: "your_user"
      MONKEY_API_PASS: "your_password"
      MONKEY_FIRMA_NAME: "Your Company Name"
```

## Available Tools

- `list_firmen`: Returns the configured company.
- `list_buchungen`: Filters bookings by date, search text, account, etc.
- `get_buchung`: Gets all details for a specific booking ID.
- `add_buchung`: Creates a new booking entry.
- `add_attachment`: Uploads a PDF as an attachment to a booking.
- `import_buchungen`: Batch imports bookings via JSON.
- `list_steuersaetze`: Lists available tax rates.
- `get_buchung_template`: Provides a template for creating bookings.

## Security Note
Never hardcode your API credentials in the script. Always use environment variables or a secure secret manager.
