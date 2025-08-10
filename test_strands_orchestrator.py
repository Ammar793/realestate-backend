#!/usr/bin/env python3
"""
Test script for StrandsAgentOrchestrator to verify the fix for the add_tool error
"""

import asyncio
import logging
import sys
import os

# Add the shared directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'shared'))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_orchestrator():
    """Test the orchestrator initialization and basic functionality"""
    try:
        from strands_orchestrator import StrandsAgentOrchestrator
        
        logger.info("Creating StrandsAgentOrchestrator...")
        orchestrator = StrandsAgentOrchestrator()
        
        logger.info("Orchestrator created successfully!")
        
        # Test system status
        status = orchestrator.get_system_status()
        logger.info(f"System status: {status}")
        
        # Test available tools
        tools = orchestrator.get_available_tools()
        logger.info(f"Available tools: {len(tools)}")
        
        # Test agent tools
        for agent_name in orchestrator.agents.keys():
            agent_tools = orchestrator.get_agent_tools(agent_name)
            logger.info(f"Agent {agent_name} has {len(agent_tools)} tools")
        
        logger.info("All tests passed! The add_tool error has been fixed.")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_orchestrator())
    sys.exit(0 if success else 1) 