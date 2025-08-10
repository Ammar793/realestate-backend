#!/usr/bin/env python3
"""
Simple WebSocket test client for the Selador Real Estate Backend
This demonstrates how to connect to the WebSocket API and send queries
"""

import asyncio
import websockets
import json
import sys

async def test_websocket_connection():
    """Test the WebSocket connection and send a sample query"""
    
    # Replace with your actual WebSocket endpoint
    # Format: wss://{api-id}.execute-api.{region}.amazonaws.com/{stage}
    websocket_url = "wss://YOUR_API_ID.execute-api.us-west-2.amazonaws.com/production"
    
    try:
        print(f"Connecting to WebSocket: {websocket_url}")
        
        async with websockets.connect(websocket_url) as websocket:
            print("✅ Connected to WebSocket")
            
            # Send a test query
            test_message = {
                "action": "invoke",
                "question": "What are the zoning requirements for residential development in Seattle?",
                "context": "Looking at a property in Capitol Hill area",
                "query_type": "zoning"
            }
            
            print(f"📤 Sending message: {json.dumps(test_message, indent=2)}")
            await websocket.send(json.dumps(test_message))
            
            # Listen for responses
            print("📥 Listening for responses...")
            response_count = 0
            
            while True:
                try:
                    # Set a timeout for receiving messages
                    response = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                    response_count += 1
                    
                    print(f"\n📨 Response #{response_count}:")
                    try:
                        parsed_response = json.loads(response)
                        print(json.dumps(parsed_response, indent=2))
                        
                        # Check if this is the final result
                        if parsed_response.get("type") == "result":
                            print("\n✅ Received final result, closing connection")
                            break
                        elif parsed_response.get("type") == "error":
                            print(f"\n❌ Received error: {parsed_response.get('error')}")
                            break
                            
                    except json.JSONDecodeError:
                        print(f"Raw response: {response}")
                        
                except asyncio.TimeoutError:
                    print("\n⏰ Timeout waiting for response, closing connection")
                    break
                    
    except websockets.exceptions.ConnectionClosed as e:
        print(f"❌ WebSocket connection closed: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    print("\n🏁 Test completed")
    return True

def main():
    """Main function to run the WebSocket test"""
    print("🚀 Starting WebSocket test for Selador Real Estate Backend")
    print("=" * 60)
    
    # Check if websockets library is available
    try:
        import websockets
    except ImportError:
        print("❌ websockets library not found. Install it with:")
        print("   pip install websockets")
        sys.exit(1)
    
    # Run the async test
    try:
        asyncio.run(test_websocket_connection())
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    main() 