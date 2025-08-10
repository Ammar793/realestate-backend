#!/usr/bin/env python3
"""
Test script to verify that the updated tool lambda function can handle the new schema structure
with tool_name included in the parameters.
"""

import json
import sys
import os

# Add the tool-lambda directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'tool-lambda'))

def test_tool_lambda_schema():
    """Test the tool lambda function with the new schema structure"""
    try:
        # Import the lambda function
        from tool_lambda_function import handler
        
        print("✅ Successfully imported tool_lambda_function")
        
        # Test event with the new schema structure (tool_name in parameters)
        test_event = {
            "tool_name": "rag_query",
            "query": "regulation pricing inventory buyer demand real estate market",
            "context": "Looking for insights on pricing, inventory, and buyer demand"
        }
        
        # Mock context
        class MockContext:
            def __init__(self):
                self.function_name = "test-tool-lambda"
        
        context = MockContext()
        
        print(f"Testing event: {json.dumps(test_event, indent=2)}")
        
        # Call the handler
        response = handler(test_event, context)
        
        print(f"Response: {json.dumps(response, indent=2)}")
        
        # Verify the response
        if response.get("statusCode") == 200:
            print("✅ Tool lambda executed successfully with new schema")
            return True
        else:
            print(f"❌ Tool lambda failed with status code: {response.get('statusCode')}")
            print(f"Error: {response.get('body', 'No error body')}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_tool_lambda_parameter_filtering():
    """Test that tool_name is properly filtered out from parameters"""
    try:
        from tool_lambda_function import _handle_tool_execution
        import asyncio
        
        print("\nTesting parameter filtering...")
        
        # Test body with tool_name and parameters
        test_body = {
            "tool_name": "rag_query",
            "query": "test query",
            "context": "test context"
        }
        
        # Mock the tool execution functions to avoid actual calls
        async def mock_execute_rag_tool(parameters):
            print(f"Mock RAG tool called with parameters: {parameters}")
            # Verify tool_name is not in parameters
            if "tool_name" in parameters:
                raise ValueError("tool_name should not be in parameters")
            return {"answer": "test answer", "citations": [], "confidence": 0.8}
        
        # Temporarily replace the function
        import tool_lambda_function
        original_rag_tool = tool_lambda_function._execute_rag_tool
        tool_lambda_function._execute_rag_tool = mock_execute_rag_tool
        
        try:
            # Call the handler
            response = asyncio.run(_handle_tool_execution(test_body))
            print(f"Parameter filtering test response: {response}")
            
            if response.get("statusCode") == 200:
                print("✅ Parameter filtering works correctly")
                return True
            else:
                print(f"❌ Parameter filtering failed: {response}")
                return False
                
        finally:
            # Restore original function
            tool_lambda_function._execute_rag_tool = original_rag_tool
            
    except Exception as e:
        print(f"❌ Parameter filtering test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=== Testing Tool Lambda Schema Updates ===")
    
    # Test 1: Basic functionality with new schema
    success1 = test_tool_lambda_schema()
    
    # Test 2: Parameter filtering
    success2 = test_tool_lambda_parameter_filtering()
    
    if success1 and success2:
        print("\n🎉 All tests passed! Tool lambda is ready for the new schema.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Please check the errors above.")
        sys.exit(1) 