#!/usr/bin/env python3
"""
Test script to debug MCP client context issues
"""

import asyncio
import logging
import sys
import os

# Add the shared directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'shared'))

from strands_orchestrator import StrandsAgentOrchestrator

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_mcp_context():
    """Test MCP client context and agent execution"""
    print("=== TESTING MCP CLIENT CONTEXT ===")
    
    try:
        # Initialize the orchestrator
        print("Initializing StrandsAgentOrchestrator...")
        orchestrator = StrandsAgentOrchestrator()
        
        # Get debug info
        print("\n=== DEBUG INFO ===")
        debug_info = orchestrator.get_debug_info()
        for key, value in debug_info.items():
            print(f"{key}: {value}")
        
        # Test MCP client connection
        print("\n=== TESTING MCP CLIENT CONNECTION ===")
        connection_test = orchestrator.test_mcp_client_connection()
        print(f"Connection test result: {connection_test}")
        
        # Test a simple query
        print("\n=== TESTING SIMPLE QUERY ===")
        test_query = "What is the current market trend in Seattle?"
        print(f"Test query: {test_query}")
        
        result = await orchestrator.route_query(test_query, query_type="market")
        print(f"Query result: {result}")
        
        # Test tool execution directly
        if orchestrator.gateway_tools:
            print("\n=== TESTING DIRECT TOOL EXECUTION ===")
            first_tool = orchestrator.gateway_tools[0]
            print(f"Testing tool: {first_tool.tool_name}")
            
            tool_result = orchestrator.debug_tool_execution(first_tool.tool_name)
            print(f"Tool execution result: {tool_result}")
        
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return False
    
    return True

if __name__ == "__main__":
    print("Starting MCP context test...")
    
    # Run the test
    success = asyncio.run(test_mcp_context())
    
    if success:
        print("\n=== TEST COMPLETED SUCCESSFULLY ===")
    else:
        print("\n=== TEST FAILED ===")
        sys.exit(1) 