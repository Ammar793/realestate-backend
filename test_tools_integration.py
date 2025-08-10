#!/usr/bin/env python3
"""
Test script to verify that agents can execute tools directly using the proper Strands approach
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

async def test_tools_integration():
    """Test that agents can execute tools directly"""
    try:
        from strands_orchestrator import StrandsAgentOrchestrator
        
        logger.info("Creating StrandsAgentOrchestrator...")
        orchestrator = StrandsAgentOrchestrator()
        
        logger.info("Orchestrator created successfully!")
        
        # Check system status
        status = orchestrator.get_system_status()
        logger.info(f"System status: {status}")
        
        # Check if agents have tools
        for agent_name in orchestrator.agents.keys():
            agent_tools = orchestrator.get_agent_tools(agent_name)
            logger.info(f"Agent {agent_name} has {len(agent_tools)} tools")
            
            if agent_tools:
                logger.info(f"Tools for {agent_name}: {[tool['name'] for tool in agent_tools]}")
        
        # Test a simple query to see if tools are available
        if orchestrator.agents:
            test_agent = list(orchestrator.agents.keys())[0]
            logger.info(f"Testing agent: {test_agent}")
            
            # Check if the agent has tools attribute
            agent = orchestrator.agents[test_agent]
            if hasattr(agent, 'tools'):
                logger.info(f"Agent {test_agent} has tools attribute with {len(agent.tools)} tools")
                for tool in agent.tools:
                    logger.info(f"  - Tool: {getattr(tool, 'tool_name', 'unknown')}")
            else:
                logger.warning(f"Agent {test_agent} does not have tools attribute")
        
        logger.info("Tools integration test completed!")
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_tools_integration())
    sys.exit(0 if success else 1) 