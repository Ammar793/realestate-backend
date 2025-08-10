import json
import os
import boto3
import logging
from typing import Dict, Any
import time

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Remove any existing handlers to avoid duplicate logs
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# Create a formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Create a handler that writes to stdout (Lambda captures this)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)

# Get a logger for this module
logger = logging.getLogger(__name__)

# Initialize SQS client
_sqs = boto3.client('sqs', region_name=os.environ.get("AWS_REGION", "us-west-2"))

# Get SQS queue URL from environment variable
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL")

def _format_websocket_response(status_code: int, body: str) -> Dict[str, Any]:
    """Format WebSocket response"""
    return {
        "statusCode": status_code,
        "body": body
    }

def _handle_websocket_connect(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle WebSocket connection"""
    try:
        connection_id = event["requestContext"]["connectionId"]
        logger.info(f"New WebSocket connection: {connection_id}")
        
        return _format_websocket_response(200, "Connected")
    except Exception as e:
        logger.error(f"Error in WebSocket connect: {e}")
        return _format_websocket_response(500, "Connection failed")

def _handle_websocket_disconnect(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle WebSocket disconnection"""
    try:
        connection_id = event["requestContext"]["connectionId"]
        logger.info(f"WebSocket disconnected: {connection_id}")
        
        return _format_websocket_response(200, "Disconnected")
    except Exception as e:
        logger.error(f"Error in WebSocket disconnect: {e}")
        return _format_websocket_response(500, "Disconnect failed")

def _handle_websocket_invoke(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle invoke action from WebSocket client - put message in SQS queue"""
    try:
        connection_id = event["requestContext"]["connectionId"]
        domain = event["requestContext"]["domainName"]
        stage = event["requestContext"]["stage"]
        
        # Parse the message body
        body = event.get("body", "{}")
        if isinstance(body, str):
            body = json.loads(body)
        
        # Extract query parameters
        query = body.get("question", "")
        context = body.get("context", "")
        query_type = body.get("query_type", "general")
        
        if not query:
            return _format_websocket_response(400, "Question is required")
        
        logger.info(f"Processing WebSocket invoke request: connection_id={connection_id}, query_length={len(query)}")
        
        # Prepare message for SQS
        sqs_message = {
            "connection_id": connection_id,
            "domain": domain,
            "stage": stage,
            "question": query,
            "context": context,
            "query_type": query_type,
            "timestamp": int(time.time() * 1000)  # Current timestamp in milliseconds
        }
        
        # Send message to SQS queue
        if not SQS_QUEUE_URL:
            logger.error("SQS_QUEUE_URL environment variable not set")
            return _format_websocket_response(500, "Configuration error: SQS queue not configured")
        
        try:
            response = _sqs.send_message(
                QueueUrl=SQS_QUEUE_URL,
                MessageBody=json.dumps(sqs_message),
                MessageAttributes={
                    'connection_id': {
                        'StringValue': connection_id,
                        'DataType': 'String'
                    },
                    'query_type': {
                        'StringValue': query_type,
                        'DataType': 'String'
                    }
                }
            )
            
            logger.info(f"Message sent to SQS successfully. MessageId: {response['MessageId']}")
            
            # Send immediate acknowledgment to WebSocket client
            return _format_websocket_response(200, "Query queued for processing")
            
        except Exception as e:
            logger.error(f"Failed to send message to SQS: {e}")
            return _format_websocket_response(500, f"Failed to queue query: {str(e)}")
        
    except Exception as e:
        logger.error(f"Error handling WebSocket invoke: {e}")
        return _format_websocket_response(500, f"Failed to process invoke: {str(e)}")

def _handle_websocket_default(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle default/unrecognized WebSocket actions"""
    try:
        connection_id = event["requestContext"]["connectionId"]
        logger.warning(f"Unrecognized WebSocket action for connection {connection_id}")
        
        return _format_websocket_response(400, "Unrecognized action")
    except Exception as e:
        logger.error(f"Error in WebSocket default handler: {e}")
        return _format_websocket_response(500, "Handler error")

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler for WebSocket events"""
    try:
        logger.info(f"WebSocket handler lambda invoked - Function: {context.function_name}")
        logger.info(f"Event type: {event.get('requestContext', {}).get('routeKey', 'Unknown')}")
        logger.debug(f"Full event: {json.dumps(event, default=str)}")
        
        # Check if this is a WebSocket event
        if event.get("requestContext", {}).get("routeKey"):
            logger.info("Request identified as WebSocket event")
            
            route_key = event["requestContext"]["routeKey"]
            logger.info(f"WebSocket route: {route_key}")
            
            # Route to appropriate WebSocket handler
            if route_key == "$connect":
                logger.info("Handling WebSocket connect event")
                result = _handle_websocket_connect(event)
                logger.info(f"WebSocket connect result: {result}")
                return result
            elif route_key == "$disconnect":
                logger.info("Handling WebSocket disconnect event")
                result = _handle_websocket_disconnect(event)
                logger.info(f"WebSocket disconnect result: {result}")
                return result
            elif route_key == "invoke":
                logger.info("Handling WebSocket invoke event")
                result = _handle_websocket_invoke(event)
                logger.info(f"WebSocket invoke result: {result}")
                return result
            else:
                logger.info(f"Handling WebSocket default event for route: {route_key}")
                result = _handle_websocket_default(event)
                logger.info(f"WebSocket default result: {result}")
                return result
        else:
            logger.error("Event is not a WebSocket event")
            return _format_websocket_response(400, "Invalid event type")
            
    except Exception as e:
        logger.error(f"WebSocket handler lambda failed with error: {str(e)}")
        logger.error(f"Error type: {type(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        return _format_websocket_response(500, f"Lambda execution failed: {str(e)}") 