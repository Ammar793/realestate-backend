#!/usr/bin/env python3
"""
Debug script to test tool execution and orchestrator state
"""

import asyncio
import json
import logging
from shared.strands_orchestrator import StrandsAgentOrchestrator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_orchestrator():
    """Test the orchestrator initialization and tool loading"""
    print("=== TESTING STRANDS ORCHESTRATOR ===")
    
    try:
        # Create orchestrator
        print("Creating orchestrator...")
        orchestrator = StrandsAgentOrchestrator()
        print("Orchestrator created successfully")
        
        # Get debug info
        print("\n=== ORCHESTRATOR STATUS ===")
        debug_info = orchestrator.get_debug_info()
        print(json.dumps(debug_info, indent=2))
        
        # List available tools
        print("\n=== AVAILABLE TOOLS ===")
        tools = orchestrator.get_available_tools()
        for tool in tools:
            print(f"- {tool['name']}: {tool['description']}")
        
        # Test agent tools
        print("\n=== AGENT TOOLS ===")
        for agent_name in ['supervisor', 'rag', 'property', 'market']:
            agent_tools = orchestrator.get_agent_tools(agent_name)
            print(f"{agent_name}: {len(agent_tools)} tools")
            for tool in agent_tools:
                print(f"  - {tool['name']}: {tool['description']}")
        
        # Test a simple query
        print("\n=== TESTING SIMPLE QUERY ===")
        result = await orchestrator.route_query(
            query="What are the zoning requirements for residential development?",
            context="Testing agent execution",
            query_type="rag_query"
        )
        print(f"Query result: {json.dumps(result, indent=2)}")
        
        # Test tool execution directly if tools are available
        if tools:
            print("\n=== TESTING TOOL EXECUTION ===")
            first_tool = tools[0]
            tool_name = first_tool['name']
            print(f"Testing tool: {tool_name}")
            
            # Test with empty parameters
            tool_result = orchestrator.debug_tool_execution(tool_name, {})
            print(f"Tool execution result: {json.dumps(tool_result, indent=2)}")
        
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()

def test_sync():
    """Test synchronous operations"""
    print("=== TESTING SYNCHRONOUS OPERATIONS ===")
    
    try:
        # Create orchestrator
        print("Creating orchestrator...")
        orchestrator = StrandsAgentOrchestrator()
        print("Orchestrator created successfully")
        
        # Get debug info
        print("\n=== ORCHESTRATOR STATUS ===")
        debug_info = orchestrator.get_debug_info()
        print(json.dumps(debug_info, indent=2))
        
        # List available tools
        print("\n=== AVAILABLE TOOLS ===")
        tools = orchestrator.get_available_tools()
        for tool in tools:
            print(f"- {tool['name']}: {tool['description']}")
        
        # Test agent tools
        print("\n=== AGENT TOOLS ===")
        for agent_name in ['supervisor', 'rag', 'property', 'market']:
            agent_tools = orchestrator.get_agent_tools(agent_name)
            print(f"{agent_name}: {len(agent_tools)} tools")
            for tool in agent_tools:
                print(f"  - {tool['name']}: {tool['description']}")
        
        # Test tool execution directly if tools are available
        if tools:
            print("\n=== TESTING TOOL EXECUTION ===")
            first_tool = tools[0]
            tool_name = first_tool['name']
            print(f"Testing tool: {tool_name}")
            
            # Test with empty parameters
            tool_result = orchestrator.debug_tool_execution(tool_name, {})
            print(f"Tool execution result: {json.dumps(tool_result, indent=2)}")
        
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Starting tools debug test...")
    
    # Test synchronous operations first
    test_sync()
    
    # Then test async operations
    print("\n" + "="*50)
    asyncio.run(test_orchestrator())
    
    print("\nDebug test completed!") 