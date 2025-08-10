# WebSocket Streaming Support for Selador Real Estate Backend

This document explains how to use the new WebSocket streaming functionality that allows real-time streaming of agent responses.

## Overview

The backend now supports WebSocket connections for streaming responses from the Strands agent orchestrator. This enables:

- Real-time status updates during agent processing
- Streaming of agent responses as they're generated
- Better user experience with immediate feedback
- Support for long-running queries without timeouts

## API Gateway WebSocket Configuration

Your API Gateway WebSocket API should be configured with these routes:

- **$connect** - Handles new WebSocket connections
- **$disconnect** - Handles WebSocket disconnections  
- **$default** - Handles unrecognized actions
- **invoke** - Handles agent query requests

The route selection expression should be: `$request.body.action`

## WebSocket Message Format

### Client to Server (invoke action)

```json
{
  "action": "invoke",
  "question": "What are the zoning requirements for residential development?",
  "context": "Looking at a property in Capitol Hill area",
  "query_type": "zoning"
}
```

**Fields:**
- `action`: Must be "invoke"
- `question`: The query to send to the agent (required)
- `context`: Additional context for the query (optional)
- `query_type`: Type of query for agent routing (optional, defaults to "general")

### Server to Client Responses

The server sends multiple message types during processing:

#### 1. Status Updates
```json
{
  "type": "status",
  "message": "Processing your query...",
  "timestamp": 1234567890.123
}
```

**Note:** The `message` event now includes the actual message content from the agent, allowing clients to display the full message text in real-time.

#### 2. Final Result
```json
{
  "type": "result",
  "data": {
    "success": true,
    "content": "Agent response content...",
    "agent": "rag",
    "query_type": "zoning",
    "tools_available": 5,
    "tools_used": 2
  },
  "timestamp": 1234567890.123
}
```

#### 3. Message Events
```json
{
  "type": "message",
  "role": "assistant",
  "content": "The actual message content from the agent...",
  "timestamp": 1234567890.123
}
```

#### 4. Error Messages
```json
{
  "type": "error",
  "error": "Error description",
  "timestamp": 1234567890.123
}
```

## Usage Examples

### JavaScript/Node.js Client

```javascript
const WebSocket = require('ws');

const ws = new WebSocket('wss://your-api-id.execute-api.us-west-2.amazonaws.com/production');

ws.on('open', function open() {
  console.log('Connected to WebSocket');
  
  // Send a query
  const message = {
    action: 'invoke',
    question: 'What are the building codes for commercial properties?',
    context: 'Planning a restaurant in downtown Seattle',
    query_type: 'building_codes'
  };
  
  ws.send(JSON.stringify(message));
});

ws.on('message', function incoming(data) {
  const response = JSON.parse(data);
  
  switch(response.type) {
    case 'status':
      console.log('Status:', response.message);
      break;
    case 'result':
      console.log('Final result:', response.data);
      ws.close();
      break;
    case 'error':
      console.error('Error:', response.error);
      ws.close();
      break;
  }
});

ws.on('error', function error(err) {
  console.error('WebSocket error:', err);
});
```

### Python Client

```python
import asyncio
import websockets
import json

async def query_agent():
    uri = "wss://your-api-id.execute-api.us-west-2.amazonaws.com/production"
    
    async with websockets.connect(uri) as websocket:
        # Send query
        message = {
            "action": "invoke",
            "question": "What are the zoning requirements?",
            "context": "Property in Capitol Hill",
            "query_type": "zoning"
        }
        
        await websocket.send(json.dumps(message))
        
        # Listen for responses
        while True:
            response = await websocket.recv()
            data = json.loads(response)
            
            if data["type"] == "result":
                print("Final result:", data["data"])
                break
            elif data["type"] == "status":
                print("Status:", data["message"])
            elif data["type"] == "error":
                print("Error:", data["error"])
                break

asyncio.run(query_agent())
```

## Testing

Use the provided test client to verify WebSocket functionality:

```bash
# Install websockets library
pip install websockets

# Update the WebSocket URL in test_websocket_client.py
# Then run the test
python test_websocket_client.py
```

## Deployment Notes

1. **Lambda Function**: The existing main-lambda function now handles both HTTP and WebSocket events
2. **IAM Permissions**: Ensure the Lambda has permission to use `apigatewaymanagementapi:PostToConnection`
3. **Environment Variables**: Same environment variables as before (KNOWLEDGE_BASE_ID, MODEL_ARN, etc.)
4. **Timeout**: Consider increasing Lambda timeout for long-running agent queries

## Error Handling

The WebSocket implementation includes comprehensive error handling:

- Connection failures are logged and reported
- Agent execution errors are sent to the client
- Malformed messages are rejected with appropriate error messages
- Timeouts and disconnections are handled gracefully

## Performance Considerations

- WebSocket connections are maintained for the duration of the query
- Multiple concurrent WebSocket connections are supported
- Agent responses are streamed as soon as they're available
- Consider implementing connection pooling for high-traffic scenarios

## Troubleshooting

### Common Issues

1. **Connection Refused**: Check API Gateway WebSocket API configuration
2. **Authentication Errors**: Verify Lambda IAM permissions
3. **Timeout Errors**: Increase Lambda timeout or implement keep-alive
4. **Message Format Errors**: Ensure message follows the required JSON structure

### Debugging

Enable detailed logging by setting the Lambda log level to INFO or DEBUG. The function logs all WebSocket events and agent interactions.

## Future Enhancements

Potential improvements for future versions:

- Support for multiple concurrent queries per connection
- Real-time progress indicators for long-running operations
- Connection authentication and authorization
- Message queuing for offline clients
- Support for binary message formats 