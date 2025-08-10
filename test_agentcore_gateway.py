#!/usr/bin/env python3
"""
Enhanced test script for AWS AgentCore Gateway with MCP tool call capabilities.
This script allows you to test both listing tools and executing tool calls locally.
"""

import requests
import json
import sys
from typing import Dict, Any, Optional

# Configuration - Update these with your actual values
CLIENT_ID = "4fqcbpb71jbm0lqda7f717jomr"
CLIENT_SECRET = "n304t2h9bs2eci6qsmbp2ct8563lhrdd36qn8kmra6nolal2r4f"
TOKEN_URL = "https://my-domain-wvtaryk8.auth.us-west-2.amazoncognito.com/oauth2/token"
GATEWAY_URL = "https://gateway-quick-start-5e1b20-wosalipwzd.gateway.bedrock-agentcore.us-west-2.amazonaws.com/mcp"

class AgentCoreGatewayTester:
    def __init__(self, client_id: str, client_secret: str, token_url: str, gateway_url: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self.gateway_url = gateway_url
        self.access_token = None
    
    def fetch_access_token(self) -> str:
        """Fetch OAuth2 access token using client credentials flow"""
        try:
            response = requests.post(
                self.token_url,
                data=f"grant_type=client_credentials&client_id={self.client_id}&client_secret={self.client_secret}",
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            response.raise_for_status()
            self.access_token = response.json()['access_token']
            return self.access_token
        except requests.exceptions.RequestException as e:
            print(f"Error fetching access token: {e}")
            sys.exit(1)
    
    def get_headers(self) -> Dict[str, str]:
        """Get headers with authorization token"""
        if not self.access_token:
            self.fetch_access_token()
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        }
    
    def list_tools(self) -> Dict[str, Any]:
        """List available tools from the gateway"""
        headers = self.get_headers()
        payload = {
            "jsonrpc": "2.0",
            "id": "list-tools-request",
            "method": "tools/list"
        }
        
        try:
            response = requests.post(self.gateway_url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error listing tools: {e}")
            return {"error": str(e)}
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any], tool_call_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute an MCP tool call
        
        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool
            tool_call_id: Optional tool call ID for tracking
        """
        headers = self.get_headers()
        
        if not tool_call_id:
            tool_call_id = f"tool-call-{tool_name}-{hash(str(arguments))}"
        
        payload = {
            "jsonrpc": "2.0",
            "id": tool_call_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        try:
            response = requests.post(self.gateway_url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error calling tool {tool_name}: {e}")
            return {"error": str(e)}
    
    def test_tool_execution(self, tool_name: str, test_arguments: Dict[str, Any]) -> None:
        """Test a specific tool with given arguments"""
        print(f"\n{'='*60}")
        print(f"Testing tool: {tool_name}")
        print(f"Arguments: {json.dumps(test_arguments, indent=2)}")
        print(f"{'='*60}")
        
        result = self.call_tool(tool_name, test_arguments)
        print(f"Result: {json.dumps(result, indent=2)}")
    
    def interactive_tool_testing(self) -> None:
        """Interactive mode for testing tools"""
        print("\n=== Interactive Tool Testing Mode ===")
        
        while True:
            print("\nOptions:")
            print("1. List available tools")
            print("2. Test a specific tool")
            print("3. Exit")
            
            choice = input("\nEnter your choice (1-3): ").strip()
            
            if choice == "1":
                tools = self.list_tools()
                print("\nAvailable tools:")
                print(json.dumps(tools, indent=2))
                
            elif choice == "2":
                tool_name = input("Enter tool name: ").strip()
                if not tool_name:
                    print("Tool name cannot be empty")
                    continue
                
                print("Enter tool arguments as JSON (e.g., {\"key\": \"value\"}):")
                args_input = input("Arguments: ").strip()
                
                try:
                    arguments = json.loads(args_input) if args_input else {}
                    self.test_tool_execution(tool_name, arguments)
                except json.JSONDecodeError:
                    print("Invalid JSON format for arguments")
                    
            elif choice == "3":
                print("Exiting...")
                break
            else:
                print("Invalid choice. Please enter 1, 2, or 3.")

def main():
    """Main function to run the tester"""
    print("AWS AgentCore Gateway Tester")
    print("=" * 40)
    
    # Check if configuration is set
    if CLIENT_ID == "<YOUR_CLIENT_ID>" or CLIENT_SECRET == "<YOUR_CLIENT_SECRET>":
        print("ERROR: Please update CLIENT_ID and CLIENT_SECRET in the script")
        print("Also update TOKEN_URL and GATEWAY_URL if needed")
        sys.exit(1)
    
    # Initialize tester
    tester = AgentCoreGatewayTester(CLIENT_ID, CLIENT_SECRET, TOKEN_URL, GATEWAY_URL)
    
    # Test basic functionality
    print("\n1. Testing access token fetch...")
    try:
        token = tester.fetch_access_token()
        print(f"✓ Access token obtained successfully")
    except Exception as e:
        print(f"✗ Failed to get access token: {e}")
        sys.exit(1)
    
    print("\n2. Testing tool listing...")
    tools = tester.list_tools()
    if "error" not in tools:
        print("✓ Tools listed successfully")
        print(f"Found {len(tools.get('result', {}).get('tools', []))} tools")
    else:
        print(f"✗ Failed to list tools: {tools['error']}")
    
    # Example tool call (uncomment and modify as needed)
    # print("\n3. Testing example tool call...")
    # example_result = tester.call_tool("example_tool", {"param": "value"})
    # print(f"Example tool call result: {json.dumps(example_result, indent=2)}")
    
    # Start interactive mode
    tester.interactive_tool_testing()

if __name__ == "__main__":
    main() 