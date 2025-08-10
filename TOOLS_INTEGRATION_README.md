# Tools Integration with Strands Agents

This document explains how tools are integrated with agents in the `StrandsAgentOrchestrator` using the proper Strands framework approach.

## Overview

The orchestrator now follows the correct Strands pattern where tools are passed to agents during initialization, allowing agents to execute tools directly without manual intervention.

## How It Works

### 1. Agent Creation
Agents are initially created without tools in the `_setup_agents()` method:

```python
self.agents["supervisor"] = Agent(
    name="supervisor",
    description="Coordinates and routes queries to appropriate agents",
    system_prompt="...",
    model=bedrock_model
)
```

### 2. Tool Distribution
After connecting to the AgentCore Gateway, tools are distributed to agents in the `_distribute_tools_to_agents()` method:

```python
# Create new agents with tools for each agent
for agent_name in self.agents:
    # Get tools for this agent
    agent_tools = []
    for tool in self.gateway_tools:
        if agent_name in target_agents:
            agent_tools.append(tool)
    
    if agent_tools:
        # Create a new agent with tools
        new_agent = Agent(
            name=original_agent.name,
            description=original_agent.description,
            system_prompt=original_agent.system_prompt,
            model=original_agent.model,
            tools=agent_tools  # Pass tools during initialization
        )
        
        # Replace the original agent with the new one that has tools
        self.agents[agent_name] = new_agent
```

### 3. Direct Tool Execution
Once agents have tools, they can execute them directly when called:

```python
# Execute the agent - it now has tools and can execute them directly
response = target_agent(full_query)
```

## Key Benefits

1. **Proper Integration**: Follows the official Strands framework pattern
2. **Direct Execution**: Agents can execute tools without manual intervention
3. **Automatic Tool Selection**: Agents choose which tools to use based on the query
4. **Simplified Code**: No need for complex tool execution logic

## Tool Mapping

Tools are mapped to agents based on functionality:

- **rag_query**: `["rag", "supervisor"]`
- **property_analysis**: `["property", "supervisor"]`
- **market_analysis**: `["market", "supervisor"]`

## System Prompts

Agents are configured with system prompts that encourage proactive tool usage:

```
You have access to powerful tools that you can use directly to perform analysis and provide comprehensive insights.
When you have access to tools, use them proactively to gather information and provide data-driven insights.
```

## Testing

Use the test script to verify tool integration:

```bash
cd backend
python test_tools_integration.py
```

## Example Usage

```python
# Create orchestrator
orchestrator = StrandsAgentOrchestrator()

# Query an agent - it will automatically use available tools
response = await orchestrator.route_query(
    query="Analyze the market trends in downtown Seattle",
    query_type="market_analysis"
)

# The agent will automatically use relevant tools to gather data
# and provide insights based on the tool results
```

## Troubleshooting

If tools are not working:

1. Check that AgentCore Gateway is connected
2. Verify tools are loaded from the gateway
3. Ensure agents are recreated with tools after gateway setup
4. Check system status: `orchestrator.get_system_status()`

## Architecture

```
AgentCore Gateway → MCP Client → Tools → Agent Recreation → Direct Tool Execution
```

The orchestrator creates a clean separation between tool loading and agent execution, ensuring that agents have all necessary tools available when they need them. 