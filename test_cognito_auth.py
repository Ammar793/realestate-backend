#!/usr/bin/env python3
"""
Test script for Cognito authentication with AgentCore Gateway
This script demonstrates the complete flow from authentication to using the gateway
"""
import asyncio
import json
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_cognito_agentcore_integration():
    """Test the complete Cognito + AgentCore integration"""
    
    try:
        # Import the Cognito authenticator
        from shared.cognito_auth import create_cognito_authenticator_from_env
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        
        # Get configuration
        gateway_url = os.getenv("AGENTCORE_GATEWAY_URL")
        if not gateway_url:
            logger.error("AGENTCORE_GATEWAY_URL not set")
            return False
        
        # Create Cognito authenticator
        logger.info("Creating Cognito authenticator...")
        cognito_auth = create_cognito_authenticator_from_env()
        
        if not cognito_auth:
            logger.error("Failed to create Cognito authenticator. Check your environment variables.")
            return False
        
        # Test authentication
        logger.info("Testing Cognito authentication...")
        access_token = cognito_auth.get_valid_token()
        logger.info(f"✅ Successfully obtained access token: {access_token[:20]}...")
        
        # Test MCP connection with authentication
        logger.info("Testing MCP connection with Cognito authentication...")
        
        async def execute_mcp_with_cognito():
            """Execute MCP operations with Cognito authentication"""
            headers = cognito_auth.get_auth_headers()
            
            async with streamablehttp_client(
                url=gateway_url,
                headers=headers,
            ) as (
                read_stream,
                write_stream,
                callA,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    # 1. Perform initialization handshake
                    logger.info("Initializing MCP...")
                    init_response = await session.initialize()
                    logger.info(f"✅ MCP Server Initialize successful! - {init_response}")
                    
                    # 2. List available tools
                    logger.info("Listing tools...")
                    cursor = True
                    tools = []
                    while cursor:
                        next_cursor = cursor
                        if type(cursor) == bool:
                            next_cursor = None
                        list_tools_response = await session.list_tools(next_cursor)
                        tools.extend(list_tools_response.tools)
                        cursor = list_tools_response.nextCursor
                    
                    tool_names = []
                    if tools:
                        for tool in tools:
                            tool_names.append(tool.name)
                    
                    tool_names_string = "\n".join(tool_names)
                    logger.info(
                        f"✅ List MCP tools. # of tools - {len(tools)}\n"
                        f"List of tools - \n{tool_names_string}\n"
                    )
                    
                    return tools
        
        # Run the MCP test
        tools = await execute_mcp_with_cognito()
        
        if tools:
            logger.info("🎉 Complete integration test successful!")
            logger.info(f"Found {len(tools)} tools in the gateway")
            return True
        else:
            logger.warning("No tools found, but authentication was successful")
            return True
            
    except ImportError as e:
        logger.error(f"Import error: {e}")
        logger.error("Make sure you have installed all required dependencies")
        return False
    except Exception as e:
        logger.error(f"Integration test failed: {e}")
        return False

def test_standalone_cognito():
    """Test just the Cognito authentication without MCP"""
    try:
        from shared.cognito_auth import create_cognito_authenticator_from_env
        
        logger.info("Testing standalone Cognito authentication...")
        
        auth = create_cognito_authenticator_from_env()
        if not auth:
            logger.error("Failed to create Cognito authenticator")
            return False
        
        # Test token fetch
        token = auth.get_valid_token()
        logger.info(f"✅ Successfully obtained token: {token[:20]}...")
        
        # Test headers
        headers = auth.get_auth_headers()
        logger.info(f"✅ Auth headers: {headers}")
        
        # Test token validation
        is_valid = auth.is_token_valid()
        logger.info(f"✅ Token is valid: {is_valid}")
        
        return True
        
    except Exception as e:
        logger.error(f"Standalone Cognito test failed: {e}")
        return False

def main():
    """Main test function"""
    logger.info("🚀 Starting Cognito + AgentCore integration tests...")
    
    # Test 1: Standalone Cognito authentication
    logger.info("\n" + "="*50)
    logger.info("TEST 1: Standalone Cognito Authentication")
    logger.info("="*50)
    
    cognito_success = test_standalone_cognito()
    
    if not cognito_success:
        logger.error("❌ Cognito authentication test failed. Stopping here.")
        return
    
    # Test 2: Full integration with AgentCore
    logger.info("\n" + "="*50)
    logger.info("TEST 2: Full AgentCore + Cognito Integration")
    logger.info("="*50)
    
    integration_success = asyncio.run(test_cognito_agentcore_integration())
    
    # Summary
    logger.info("\n" + "="*50)
    logger.info("TEST SUMMARY")
    logger.info("="*50)
    
    if cognito_success and integration_success:
        logger.info("🎉 ALL TESTS PASSED!")
        logger.info("✅ Cognito authentication is working")
        logger.info("✅ AgentCore gateway integration is working")
        logger.info("✅ Your setup is ready for production use")
    elif cognito_success:
        logger.info("⚠️  PARTIAL SUCCESS")
        logger.info("✅ Cognito authentication is working")
        logger.error("❌ AgentCore gateway integration failed")
        logger.info("Check your gateway URL and configuration")
    else:
        logger.error("❌ ALL TESTS FAILED")
        logger.error("Check your Cognito configuration and environment variables")

if __name__ == "__main__":
    main() 