#!/usr/bin/env python3
"""
Simple test script for AWS AgentCore Gateway MCP tool calls.
Quick and easy way to test tools locally.
"""

import requests
import json
import sys

# Configuration - Update these with your actual values
CLIENT_ID = "<YOUR_CLIENT_ID>"
CLIENT_SECRET = "<YOUR_CLIENT_SECRET>"
TOKEN_URL = "https://my-domain-wvtaryk8.auth.us-west-2.amazoncognito.com/oauth2/token"
GATEWAY_URL = "https://gateway-quick-start-5e1b20-wosalipwzd.gateway.bedrock-agentcore.us-west-2.amazonaws.com/mcp"

def fetch_access_token(client_id, client_secret, token_url):
    """Fetch OAuth2 access token using client credentials flow"""
    response = requests.post(
        token_url,
        data=f"grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}",
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )
    return response.json()['access_token']

def list_tools(gateway_url, access_token):
    """List available tools from the gateway"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    
    payload = {
        "jsonrpc": "2.0",
        "id": "list-tools-request",
        "method": "tools/list"
    }
    
    response = requests.post(gateway_url, headers=headers, json=payload)
    return response.json()

def call_tool(gateway_url, access_token, tool_name, arguments):
    """Execute an MCP tool call"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    
    payload = {
        "jsonrpc": "2.0",
        "id": f"tool-call-{tool_name}",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }
    
    response = requests.post(gateway_url, headers=headers, json=payload)
    return response.json()

def main():
    """Main function with example usage"""
    print("AWS AgentCore Gateway - Simple MCP Tool Tester")
    print("=" * 50)
    
    # Check configuration
    if CLIENT_ID == "<YOUR_CLIENT_ID>" or CLIENT_SECRET == "<YOUR_CLIENT_SECRET>":
        print("ERROR: Please update CLIENT_ID and CLIENT_SECRET in the script")
        sys.exit(1)
    
    try:
        # Get access token
        print("1. Fetching access token...")
        access_token = fetch_access_token(CLIENT_ID, CLIENT_SECRET, TOKEN_URL)
        print("✓ Access token obtained")
        
        # List tools
        print("\n2. Listing available tools...")
        tools = list_tools(GATEWAY_URL, access_token)
        print("Available tools:")
        print(json.dumps(tools, indent=2))
        
        # Example tool call (modify as needed)
        print("\n3. Example tool call...")
        # Replace 'example_tool' with an actual tool name from your gateway
        example_result = call_tool(GATEWAY_URL, access_token, "example_tool", {"param": "value"})
        print("Example tool call result:")
        print(json.dumps(example_result, indent=2))
        
        # Interactive tool testing
        print("\n4. Interactive tool testing...")
        while True:
            print("\nEnter tool name to test (or 'quit' to exit):")
            tool_name = input("Tool name: ").strip()
            
            if tool_name.lower() == 'quit':
                break
                
            if not tool_name:
                continue
                
            print("Enter tool arguments as JSON (e.g., {\"key\": \"value\"}):")
            args_input = input("Arguments: ").strip()
            
            try:
                arguments = json.loads(args_input) if args_input else {}
                result = call_tool(GATEWAY_URL, access_token, tool_name, arguments)
                print(f"\nResult for {tool_name}:")
                print(json.dumps(result, indent=2))
            except json.JSONDecodeError:
                print("Invalid JSON format for arguments")
            except Exception as e:
                print(f"Error calling tool: {e}")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 