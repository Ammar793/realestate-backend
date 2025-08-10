#!/usr/bin/env python3
"""
Test script to demonstrate the new thinking progress functionality
"""

import asyncio
import json
import sys
import os

# Add the shared directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'shared'))

from strands_orchestrator import StrandsAgentOrchestrator

def progress_callback(message_type: str, message: str, metadata: dict):
    """Example progress callback function"""
    print(f"\n🤔 THINKING UPDATE [{message_type.upper()}]: {message}")
    if metadata:
        print(f"   📊 Metadata: {json.dumps(metadata, indent=2, default=str)}")
    print("-" * 80)

async def test_thinking_progress():
    """Test the thinking progress functionality"""
    print("🧪 Testing Thinking Progress Functionality")
    print("=" * 80)
    
    try:
        # Initialize the orchestrator
        print("🔧 Initializing Strands Agent Orchestrator...")
        orchestrator = StrandsAgentOrchestrator()
        
        # Set the progress callback
        print("📡 Setting progress callback...")
        orchestrator.set_progress_callback(progress_callback)
        
        # Test a simple query
        print("\n🚀 Testing agent query with thinking progress...")
        query = "What are the zoning requirements for residential development in Seattle?"
        context = "User is a developer looking to build residential units in Seattle."
        
        print(f"📝 Query: {query}")
        print(f"📋 Context: {context}")
        
        # Execute the query
        result = await orchestrator.route_query(query, context, "property")
        
        print(f"\n✅ Query completed!")
        print(f"📊 Success: {result.get('success')}")
        print(f"🤖 Agent used: {result.get('agent')}")
        print(f"🛠️  Tools available: {result.get('tools_available')}")
        print(f"🔧 Tools used: {result.get('tools_used')}")
        
        if 'thinking_process' in result:
            print(f"\n🧠 Thinking Process Summary:")
            print(f"   Total thinking updates: {len(result['thinking_process'])}")
            for i, update in enumerate(result['thinking_process']):
                print(f"   {i+1}. {update['message_type']}: {update['message']}")
        
        # Test workflow execution
        print("\n🚀 Testing workflow execution with thinking progress...")
        workflow_name = "property_analysis"
        parameters = {"address": "123 Main St, Seattle, WA"}
        
        print(f"📋 Workflow: {workflow_name}")
        print(f"🔧 Parameters: {parameters}")
        
        # Execute the workflow
        workflow_result = await orchestrator.execute_workflow(workflow_name, parameters)
        
        print(f"\n✅ Workflow completed!")
        print(f"📊 Success: {workflow_result.get('success')}")
        
        if 'thinking_process' in workflow_result:
            print(f"\n🧠 Workflow Thinking Process Summary:")
            print(f"   Total thinking updates: {len(workflow_result['thinking_process'])}")
            for i, update in enumerate(workflow_result['thinking_process']):
                print(f"   {i+1}. {update['message_type']}: {update['message']}")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🧪 Starting Thinking Progress Test...")
    asyncio.run(test_thinking_progress())
    print("\n✅ Test completed!") 