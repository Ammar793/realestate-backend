# Debugging Tools for Strands Orchestrator

This document provides comprehensive debugging tools and techniques to troubleshoot tool invocation issues in your Strands agent orchestrator.

## Overview

The logs show that your Lambda function is starting up and beginning to process requests, but it appears to stop after entering the Strands orchestrator. This suggests the issue is likely in the `StrandsAgentOrchestrator.route_query()` method or the agent execution itself.

## Enhanced Logging

I've added comprehensive logging throughout the orchestrator to help debug the execution flow:

### 1. Constructor Logging
- Tracks initialization of each component
- Shows agent creation process
- Displays gateway setup progress

### 2. Gateway Setup Logging
- Shows AgentCore Gateway connection attempts
- Tracks Cognito authentication process
- Displays MCP client creation

### 3. Tool Loading Logging
- Shows tool discovery from gateway
- Displays pagination process
- Lists all available tools

### 4. Tool Distribution Logging
- Shows which tools are assigned to which agents
- Tracks agent recreation with tools
- Displays final tool assignments

### 5. Query Execution Logging
- Shows agent selection process
- Tracks tool availability for each agent
- Displays agent execution details
- Shows response processing

## Debug Endpoints

I've added debug endpoints to your Lambda function to help troubleshoot:

### Debug Status
```bash
curl -X POST "YOUR_LAMBDA_URL" \
  -H "Content-Type: application/json" \
  -d '{"debug_type": "status"}'
```

### List Available Tools
```bash
curl -X POST "YOUR_LAMBDA_URL" \
  -H "Content-Type: application/json" \
  -d '{"debug_type": "list_tools"}'
```

### Test Tool Execution
```bash
curl -X POST "YOUR_LAMBDA_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "debug_type": "test_tool",
    "tool_name": "rag_query",
    "parameters": {}
  }'
```

## Local Testing

### 1. Run the Debug Script
```bash
cd backend
python test_tools_debug.py
```

This script will:
- Test orchestrator initialization
- Show tool loading process
- Test agent creation
- Test tool execution directly
- Display comprehensive debug information

### 2. Test Debug Endpoints
```bash
cd backend
# Edit test_debug_endpoints.sh to set your Lambda URL
./test_debug_endpoints.sh
```

## Common Issues and Solutions

### 1. Tools Not Loading
**Symptoms**: `gateway_tools_count: 0` in logs
**Possible Causes**:
- AgentCore Gateway URL incorrect
- Authentication failed (Cognito or access token)
- MCP client connection issues
- Network connectivity problems

**Debug Steps**:
- Check `agentcore_config.json` or environment variables
- Verify Cognito setup in `COGNITO_SETUP.md`
- Check CloudWatch logs for authentication errors
- Test gateway connectivity

### 2. Agents Not Getting Tools
**Symptoms**: `Agent X has 0 tools available` in logs
**Possible Causes**:
- Tool mapping incorrect
- Tool names don't match expected patterns
- Agent recreation failed

**Debug Steps**:
- Check tool mapping in `_distribute_tools_to_agents()`
- Verify tool names from gateway match expected names
- Check agent creation logs

### 3. Agent Execution Failing
**Symptoms**: Agent execution errors in logs
**Possible Causes**:
- Strands Agent initialization issues
- Bedrock model configuration problems
- Tool integration issues

**Debug Steps**:
- Check Bedrock model configuration
- Verify Strands Agent creation
- Test tool execution directly

### 4. MCP Client Issues
**Symptoms**: MCP client creation failures
**Possible Causes**:
- Transport creation issues
- Authentication header problems
- Gateway URL format issues

**Debug Steps**:
- Check authentication headers
- Verify gateway URL format
- Test transport creation

## Debug Information Available

### Orchestrator Status
- Number of agents
- Gateway connection status
- Available tools count
- Tool assignments per agent

### Tool Information
- Tool names and descriptions
- Input schemas
- Tool availability per agent

### Execution Details
- Agent selection process
- Tool usage during execution
- Response processing
- Error details with full tracebacks

## Next Steps

1. **Deploy the updated code** with enhanced logging
2. **Run a test request** to see the detailed logs
3. **Use debug endpoints** to check orchestrator state
4. **Run local tests** to isolate issues
5. **Check CloudWatch logs** for the detailed execution flow

## Expected Log Flow

After deployment, you should see logs like:
```
=== STRANDS ORCHESTRATOR: Starting route_query ===
=== SELECTED AGENT: rag ===
=== AGENT rag HAS 2 TOOLS AVAILABLE ===
=== AVAILABLE TOOLS FOR rag: ['rag_query', 'property_analysis'] ===
=== EXECUTING AGENT rag ===
=== CALLING agent.invoke() with query... ===
=== AGENT EXECUTION COMPLETED SUCCESSFULLY ===
=== TOOLS USED IN EXECUTION: 1 ===
```

If you don't see these logs, the issue is likely in the orchestrator initialization or agent setup phase.

## Contact

If you continue to have issues after using these debugging tools, please share:
1. The complete CloudWatch logs
2. Output from debug endpoints
3. Results from local testing
4. Any error messages or exceptions 