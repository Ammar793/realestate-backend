# Thinking Progress Streaming

This document describes the new thinking progress streaming functionality that allows users to see real-time updates about what the supervisor agent and orchestrator are doing while processing queries.

## Overview

The thinking progress system provides real-time visibility into the agent execution process, allowing users to understand:
- Which agent is being selected for a query
- What tools are available and being used
- The current status of execution (analyzing, executing, finalizing, etc.)
- Any errors or recovery attempts
- Step-by-step workflow execution progress

## How It Works

### 1. Progress Callback System

The `StrandsAgentOrchestrator` class now includes a progress callback mechanism:

```python
def set_progress_callback(self, callback: Callable[[str, str, Dict[str, Any]], None]):
    """Set a callback function to receive progress updates during agent execution"""
    self.progress_callback = callback

def _send_progress(self, message_type: str, message: str, metadata: Dict[str, Any] = None):
    """Send progress update through the callback if set"""
    if self.progress_callback:
        self.progress_callback(message_type, message, metadata)
```

### 2. WebSocket Integration

For WebSocket clients, thinking progress is streamed in real-time:

```typescript
// WebSocket message types for thinking progress
interface ThinkingUpdate {
  type: "thinking";
  message_type: string;  // "start", "thinking", "complete", "error", etc.
  message: string;       // Human-readable description
  metadata: object;      // Additional context data
  timestamp: number;     // Unix timestamp
}
```

### 3. HTTP Integration

For regular HTTP requests, thinking progress is included in the response:

```json
{
  "success": true,
  "content": "Agent response content...",
  "agent": "rag",
  "thinking_process": [
    {
      "type": "thinking",
      "message_type": "start",
      "message": "Starting analysis of your query...",
      "metadata": {"query": "user question", "query_type": "general"},
      "timestamp": 1234567890
    }
    // ... more thinking updates
  ]
}
```

## Message Types

### Query Processing
- `start` - Initial analysis started
- `thinking` - General thinking/processing updates
- `complete` - Analysis completed successfully
- `error` - Error occurred during processing

### Agent Execution
- `agent_selected` - Which agent was chosen
- `tools_available` - What tools the agent can use
- `executing` - Agent is actively processing
- `analyzing` - Agent is analyzing results
- `finalizing` - Preparing final response

### Workflow Execution
- `workflow_start` - Workflow execution started
- `step_executing` - Individual step being executed
- `step_complete` - Step completed
- `workflow_complete` - Entire workflow finished

### Error Handling
- `recovering` - System attempting to recover from error
- `reinitializing` - Reinitializing components
- `retrying` - Retrying failed operations

## Example Usage

### Setting up Progress Callback

```python
from strands_orchestrator import StrandsAgentOrchestrator

# Initialize orchestrator
orchestrator = StrandsAgentOrchestrator()

# Set progress callback
def my_progress_callback(message_type: str, message: str, metadata: dict):
    print(f"Progress: {message_type} - {message}")
    # Handle progress update (log, display, stream, etc.)

orchestrator.set_progress_callback(my_progress_callback)

# Execute query - progress will be sent to callback
result = await orchestrator.route_query("What are the zoning requirements?", "", "property")
```

### WebSocket Client Handling

```typescript
// WebSocket client handling thinking updates
websocket.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch (data.type) {
    case "thinking":
      // Display thinking progress to user
      displayThinkingProgress(data.message, data.metadata);
      break;
      
    case "result":
      // Display final result
      displayResult(data.data);
      // Show thinking process summary
      displayThinkingSummary(data.thinking_process);
      break;
      
    case "error":
      // Handle error
      displayError(data.error);
      break;
  }
};
```

## Benefits

1. **Transparency** - Users can see exactly what the system is doing
2. **Debugging** - Easier to identify where issues occur
3. **User Experience** - Users know the system is working, not frozen
4. **Monitoring** - Real-time visibility into system performance
5. **Trust** - Users can see the reasoning process

## Testing

Use the provided test script to verify the functionality:

```bash
cd backend
python test_thinking_progress.py
```

This will demonstrate the thinking progress system with both agent queries and workflow execution.

## Configuration

The thinking progress system is enabled by default and requires no additional configuration. Progress callbacks are optional - if no callback is set, progress updates are logged at debug level.

## Future Enhancements

Potential improvements could include:
- Progress percentage indicators
- Estimated completion times
- More granular step-by-step progress
- Progress persistence for long-running operations
- Progress analytics and metrics 