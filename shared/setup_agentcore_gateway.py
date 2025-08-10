#!/usr/bin/env python3
"""
Setup script for Amazon Bedrock AgentCore Gateway with Cognito Authentication
Based on AWS documentation: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-quick-start.html
"""
import json
import logging
import os
from dotenv import load_dotenv
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_agentcore_gateway():
    """Set up the AgentCore Gateway with Lambda targets and Cognito authentication"""
    
    # Get configuration from environment
    region = os.getenv("AWS_REGION", "us-west-2")
    gateway_name = os.getenv("GATEWAY_NAME", "JLSRealEstateGateway")
    
    logger.info(f"Setting up AgentCore Gateway in region: {region}")
    
    try:
        # Setup the client
        client = GatewayClient(region_name=region)
        client.logger.setLevel(logging.DEBUG)
        
        # Create the gateway with Cognito authentication
        logger.info("Creating MCP Gateway with Cognito authentication...")
        gateway = client.create_mcp_gateway(
            name=gateway_name,
            enable_semantic_search=True,
            # Add authentication configuration
            authentication_configuration={
                "type": "oauth2",
                "oauth2_configuration": {
                    "authorization_server": "cognito",
                    "client_id": os.getenv("COGNITO_CLIENT_ID"),
                    "client_secret": os.getenv("COGNITO_CLIENT_SECRET"),
                    "token_endpoint": os.getenv("COGNITO_TOKEN_URL")
                }
            }
        )
        logger.info(f"Gateway created successfully: {gateway['gatewayId']}")
        
        # Create Lambda target with RAG tools
        logger.info("Creating Lambda target with RAG tools...")
        lambda_target = client.create_mcp_gateway_target(
            gateway=gateway,
            target_type="lambda",
            target_payload={
                "lambdaArn": os.getenv("LAMBDA_ARN"),  # Your existing Lambda ARN
                "toolSchema": {
                    "inlinePayload": [
                        {
                            "name": "rag_query",
                            "description": "Query the knowledge base for real estate information",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "The query to search for in the knowledge base"
                                    },
                                    "context": {
                                        "type": "string",
                                        "description": "Additional context for the query"
                                    }
                                },
                                "required": ["query"]
                            }
                        },
                        {
                            "name": "property_analysis",
                            "description": "Analyze a specific property for development potential",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "address": {
                                        "type": "string",
                                        "description": "Property address"
                                    },
                                    "property_type": {
                                        "type": "string",
                                        "description": "Type of property (residential, commercial, etc.)"
                                    },
                                    "analysis_type": {
                                        "type": "string",
                                        "enum": ["zoning", "permits", "development", "comprehensive"],
                                        "description": "Type of analysis to perform"
                                    }
                                },
                                "required": ["address", "analysis_type"]
                            }
                        },
                        {
                            "name": "market_analysis",
                            "description": "Analyze market conditions and trends",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "location": {
                                        "type": "string",
                                        "description": "Location for market analysis (city, neighborhood, etc.)"
                                    },
                                    "property_type": {
                                        "type": "string",
                                        "description": "Type of property to analyze"
                                    },
                                    "timeframe": {
                                        "type": "string",
                                        "enum": ["3months", "6months", "1year", "2years"],
                                        "description": "Timeframe for market analysis"
                                    }
                                },
                                "required": ["location", "property_type"]
                            }
                        }
                    ]
                }
            }
        )
        logger.info(f"Lambda target created successfully: {lambda_target['targetId']}")
        
        # Save configuration with Cognito info
        config = {
            "gateway_id": gateway["gatewayId"],
            "gateway_url": gateway["gatewayUrl"],
            "target_id": lambda_target["targetId"],
            "region": region,
            "cognito_client_info": {
                "client_id": os.getenv("COGNITO_CLIENT_ID"),
                "client_secret": os.getenv("COGNITO_CLIENT_SECRET"),
                "token_url": os.getenv("COGNITO_TOKEN_URL"),
                "user_pool_id": os.getenv("COGNITO_USER_POOL_ID"),
                "identity_pool_id": os.getenv("COGNITO_IDENTITY_POOL_ID")
            }
        }
        
        with open("agentcore_config.json", "w") as f:
            json.dump(config, f, indent=2)
        
        logger.info("Configuration saved to agentcore_config.json")
        logger.info(f"Gateway URL: {gateway['gatewayUrl']}")
        logger.info(f"Gateway ID: {gateway['gatewayId']}")
        logger.info("Gateway configured with Cognito authentication")
        
        return config
        
    except Exception as e:
        logger.error(f"Error setting up AgentCore Gateway: {e}")
        raise

def list_gateway_tools(gateway_url: str, access_token: str = None):
    """List all available tools in the gateway with optional authentication"""
    try:
        from strands.tools.mcp.mcp_client import MCPClient
        from mcp.client.streamable_http import streamablehttp_client
        
        def create_streamable_http_transport(mcp_url: str, auth_token: str = None):
            if auth_token:
                return streamablehttp_client(mcp_url, headers={"Authorization": f"Bearer {auth_token}"})
            else:
                return streamablehttp_client(mcp_url)  # No auth headers
        
        def get_full_tools_list(client):
            more_tools = True
            tools = []
            pagination_token = None
            while more_tools:
                tmp_tools = client.list_tools_sync(pagination_token=pagination_token)
                tools.extend(tmp_tools)
                if tmp_tools.pagination_token is None:
                    more_tools = False
                else:
                    more_tools = True 
                    pagination_token = tmp_tools.pagination_token
            return tools
        
        mcp_client = MCPClient(lambda: create_streamable_http_transport(gateway_url, access_token))
        
        with mcp_client:
            tools = get_full_tools_list(mcp_client)
            logger.info(f"Found {len(tools)} tools in gateway:")
            for tool in tools:
                description = getattr(tool, 'description', 'No description available')
                logger.info(f"  - {tool.tool_name}: {description}")
            return tools
            
    except Exception as e:
        logger.error(f"Error listing gateway tools: {e}")
        return []

def test_cognito_connection():
    """Test the Cognito connection and get a test token"""
    try:
        from shared.cognito_auth import create_cognito_authenticator_from_env
        
        auth = create_cognito_authenticator_from_env()
        if auth:
            logger.info("Testing Cognito connection...")
            token = auth.get_valid_token()
            logger.info(f"Successfully obtained test token: {token[:20]}...")
            return token
        else:
            logger.warning("Cognito authenticator not available")
            return None
            
    except Exception as e:
        logger.error(f"Cognito connection test failed: {e}")
        return None

if __name__ == "__main__":
    try:
        config = setup_agentcore_gateway()
        
        # Test Cognito connection
        logger.info("Testing Cognito connection...")
        test_token = test_cognito_connection()
        
        if test_token:
            # Test listing tools with authentication
            logger.info("Testing tool listing with authentication...")
            list_gateway_tools(config["gateway_url"], test_token)
        else:
            # Test listing tools without authentication
            logger.info("Testing tool listing without authentication...")
            list_gateway_tools(config["gateway_url"])
        
        logger.info("AgentCore Gateway setup completed successfully!")
        logger.info("You can now use this gateway with your Strands agents.")
        
    except Exception as e:
        logger.error(f"Setup failed: {e}")
        exit(1) 