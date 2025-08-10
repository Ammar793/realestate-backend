# AgentCore Gateway Testing Scripts

This directory contains enhanced test scripts for AWS AgentCore Gateway that allow you to test MCP tool calls locally.

## Scripts Overview

### 1. `test_agentcore_gateway.py` - Full-Featured Tester
A comprehensive testing script with:
- OAuth2 authentication
- Tool listing
- MCP tool execution
- Interactive testing mode
- Error handling and validation

### 2. `test_agentcore_simple.py` - Simple Tester
A streamlined version for quick testing:
- Basic authentication
- Tool listing
- Simple tool calls
- Interactive mode

## Setup Instructions

### 1. Update Configuration
Edit either script and update these values with your actual credentials:

```python
CLIENT_ID = "<YOUR_CLIENT_ID>"
CLIENT_SECRET = "<YOUR_CLIENT_SECRET>"
TOKEN_URL = "https://your-domain.auth.region.amazoncognito.com/oauth2/token"
GATEWAY_URL = "https://your-gateway-id.gateway.bedrock-agentcore.region.amazonaws.com/mcp"
```

### 2. Install Dependencies
```bash
pip install requests
```

### 3. Run the Scripts
```bash
# Full-featured version
python test_agentcore_gateway.py

# Simple version
python test_agentcore_simple.py
```

## Usage Examples

### List Available Tools
The scripts will automatically list available tools when run.

### Execute a Tool Call
```python
# Programmatic usage
result = call_tool(gateway_url, access_token, "tool_name", {"param": "value"})

# Interactive usage
# Run the script and follow the prompts
```

### Example Tool Call Payload
```json
{
  "jsonrpc": "2.0",
  "id": "tool-call-example",
  "method": "tools/call",
  "params": {
    "name": "your_tool_name",
    "arguments": {
      "key1": "value1",
      "key2": "value2"
    }
  }
}
```

## MCP Protocol Support

These scripts implement the MCP (Model Context Protocol) specification for:
- **tools/list** - List available tools
- **tools/call** - Execute tool calls with arguments

## Error Handling

The scripts include comprehensive error handling for:
- Authentication failures
- Network errors
- Invalid JSON responses
- Tool execution errors

## Testing Workflow

1. **Authentication**: Verify OAuth2 credentials work
2. **Tool Discovery**: List available tools from your gateway
3. **Tool Testing**: Execute individual tools with test parameters
4. **Validation**: Verify tool responses and error handling

## Troubleshooting

### Common Issues

1. **Invalid Credentials**: Double-check CLIENT_ID and CLIENT_SECRET
2. **Network Errors**: Verify TOKEN_URL and GATEWAY_URL are accessible
3. **Tool Not Found**: Ensure the tool name matches exactly what's available
4. **Invalid Arguments**: Check the tool's expected input schema

### Debug Mode
Both scripts include detailed logging and error messages to help diagnose issues.

## Security Notes

- Never commit credentials to version control
- Use environment variables for production deployments
- Rotate credentials regularly
- Monitor API usage and set appropriate rate limits

## Integration with Your Workflow

These scripts can be integrated into:
- CI/CD pipelines for testing
- Development workflows
- Automated testing suites
- Debugging and troubleshooting processes 