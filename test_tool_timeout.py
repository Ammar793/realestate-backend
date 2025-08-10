#!/usr/bin/env python3
"""
Test script to identify which tool is causing hanging issues
"""

import asyncio
import logging
import sys
import os
import time

# Add the shared directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'shared'))

from strands_orchestrator import StrandsAgentOrchestrator

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_individual_tools():
    """Test individual tools to identify which one hangs"""
    print("=== TESTING INDIVIDUAL TOOLS ===")
    
    try:
        # Initialize the orchestrator
        print("Initializing StrandsAgentOrchestrator...")
        orchestrator = StrandsAgentOrchestrator()
        
        if not orchestrator.gateway_tools:
            print("No tools available to test")
            return
        
        print(f"Found {len(orchestrator.gateway_tools)} tools to test")
        
        # Test each tool individually with a timeout
        for i, tool in enumerate(orchestrator.gateway_tools):
            print(f"\n--- Testing Tool {i+1}/{len(orchestrator.gateway_tools)} ---")
            print(f"Tool name: {tool.tool_name}")
            print(f"Tool description: {getattr(tool, 'description', 'No description')}")
            
            # Test tool execution with timeout
            start_time = time.time()
            try:
                print(f"Executing tool {tool.tool_name}...")
                result = orchestrator.debug_tool_execution(tool.tool_name)
                execution_time = time.time() - start_time
                print(f"Tool execution completed in {execution_time:.2f} seconds")
                print(f"Result: {result}")
                
                if result.get("success"):
                    print(f"✅ Tool {tool.tool_name} executed successfully")
                else:
                    print(f"❌ Tool {tool.tool_name} failed: {result.get('error')}")
                    
            except Exception as e:
                execution_time = time.time() - start_time
                print(f"❌ Tool {tool.tool_name} crashed after {execution_time:.2f} seconds: {e}")
            
            # Add a small delay between tools
            time.sleep(1)
        
        print("\n=== TOOL TESTING COMPLETE ===")
        
    except Exception as e:
        print(f"Error during tool testing: {e}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return False
    
    return True

if __name__ == "__main__":
    print("Starting individual tool testing...")
    
    # Run the test
    success = test_individual_tools()
    
    if success:
        print("\n=== TEST COMPLETED SUCCESSFULLY ===")
    else:
        print("\n=== TEST FAILED ===")
        sys.exit(1) 