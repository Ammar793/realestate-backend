# Lambda Premature Exit Issue - Analysis and Fix

## Problem Description

The Lambda function was exiting prematurely during WebSocket streaming operations, causing the agent execution to be terminated before completion. This was evident in the logs showing:

```
2025-08-10T22:10:20.136Z - strands_orchestrator - INFO - MCP client context entered for agent execution
2025-08-10T22:10:20.576Z - END RequestId: cc43ca9b-e2f2-4a66-b37d-5bf8793509a2
```

The Lambda function started the agent execution but then terminated immediately without completing the streaming.

## Root Cause

The issue was in the WebSocket handler (`_handle_websocket_invoke`) which used:

```python
# Start streaming the response asynchronously
# Note: This runs in the background and doesn't block the response
asyncio.create_task(_stream_agent_response_websocket(connection_id, query, context, query_type, domain, stage))

return _format_websocket_response(200, "Query processing started")
```

**Problem**: `asyncio.create_task()` creates a background task but doesn't wait for it to complete. Lambda functions terminate when the handler returns, so any background tasks get killed before they can complete.

## Solution Implemented

### 1. Fixed WebSocket Handler

Changed the WebSocket handler to wait for streaming completion:

```python
# IMPORTANT: For Lambda, we need to wait for the streaming to complete
# Lambda functions terminate when the handler returns, so background tasks get killed
logger.info("Starting agent response streaming (will wait for completion)")
await _stream_agent_response_websocket(connection_id, query, context, query_type, domain, stage)

logger.info("Agent response streaming completed successfully")
return _format_websocket_response(200, "Query processing completed")
```

### 2. Enhanced Logging and Error Handling

Added comprehensive logging throughout the streaming process to help debug any remaining issues:

- Event counting and timing
- Detailed error logging with full tracebacks
- Orchestrator validation
- Lambda context information

### 3. Timeout Protection

Added timeout protection to prevent Lambda from running too long:

```python
# Check if we're approaching Lambda timeout (leave 30 seconds buffer)
if elapsed_time > 870:  # 15 minutes - 30 seconds buffer
    logger.warning("Approaching Lambda timeout, sending timeout message and stopping")
    _send_websocket_message(connection_id, {
        "type": "error",
        "error": "Query timeout - Lambda execution time limit reached",
        "timestamp": current_time
    }, domain, stage)
    break
```

### 4. Orchestrator Validation

Added validation to ensure the orchestrator is working correctly:

```python
# Validate the orchestrator is working
try:
    status = _orchestrator.get_system_status()
    logger.info(f"Orchestrator status: {status}")
except Exception as e:
    logger.error(f"Orchestrator validation failed: {e}")
    # Reset the orchestrator if it's not working
    _orchestrator = None
    raise Exception(f"Orchestrator validation failed: {e}")
```

## Why This Happens in Lambda

Lambda functions have a fundamental limitation for real-time streaming:

1. **Execution Model**: Lambda functions are designed for request-response patterns, not long-running operations
2. **Task Lifecycle**: When the handler function returns, the Lambda execution environment terminates
3. **Background Tasks**: `asyncio.create_task()` creates tasks that run in the background, but these get killed when Lambda terminates

## Alternative Solutions for Production

For production use with real-time streaming, consider these alternatives:

### Option 1: API Gateway WebSocket + Lambda Integration
- Use API Gateway WebSocket API with Lambda integration
- Lambda handles connection management and routing
- Streaming happens in a separate long-running service

### Option 2: Long-Running Service
- Use ECS, EC2, or App Runner for the streaming service
- Lambda handles initial request and delegates to the service
- Use EventBridge for coordination

### Option 3: Step Functions
- Use Step Functions for orchestration
- Lambda initiates the workflow
- Step Functions manages the long-running agent execution

## Testing the Fix

After deploying the fix:

1. **Check Logs**: Look for the new detailed logging messages
2. **Verify Completion**: Ensure the Lambda function completes the full streaming before terminating
3. **Monitor Timeouts**: Watch for any timeout-related messages
4. **Test WebSocket**: Use the test client to verify end-to-end functionality

## Files Modified

- `backend/main-lambda/lambda_function.py` - Main fixes and enhancements
- `backend/LAMBDA_PREMATURE_EXIT_FIX.md` - This documentation

## Deployment

Deploy the updated Lambda function using:

```bash
cd backend
./deploy-websocket-lambda.sh
```

The deployment script will:
- Package the updated code
- Update the Lambda function
- Set appropriate timeout (900 seconds) and memory (1024 MB) 