import json
import os
import boto3
import asyncio
import base64
import logging
from strands_orchestrator import StrandsAgentOrchestrator
import time

# Configure logging for Lambda - this ensures logs show up in CloudWatch
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

# Reuse client across invocations
_bedrock = boto3.client("bedrock-agent-runtime", region_name=os.environ.get("AWS_REGION", "us-west-2"))

KB_ID = os.environ["KNOWLEDGE_BASE_ID"]
MODEL_ARN = os.environ["MODEL_ARN"]  # e.g., arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0

logger.info(f"Initialized with KB_ID: {KB_ID}, MODEL_ARN: {MODEL_ARN}")

# Initialize agent orchestrator
_orchestrator = None

def _get_orchestrator():
    """Get or create the Strands agent orchestrator instance"""
    global _orchestrator
    if _orchestrator is None:
        print("=== CREATING NEW STRANDS ORCHESTRATOR INSTANCE ===")
        logger.info("Creating new Strands agent orchestrator instance")
        try:
            _orchestrator = StrandsAgentOrchestrator()
            print("=== ORCHESTRATOR INSTANCE CREATED SUCCESSFULLY ===")
            logger.info("Orchestrator instance created successfully")
        except Exception as e:
            print(f"=== FAILED TO CREATE ORCHESTRATOR INSTANCE: {e} ===")
            logger.error(f"Failed to create orchestrator instance: {e}")
            logger.error(f"Error type: {type(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
    else:
        print("=== REUSING EXISTING ORCHESTRATOR INSTANCE ===")
        logger.debug("Reusing existing Strands agent orchestrator instance")
    
    # Validate the orchestrator is working
    try:
        status = _orchestrator.get_system_status()
        logger.info(f"Orchestrator status: {status}")
    except Exception as e:
        logger.error(f"Orchestrator validation failed: {e}")
        # Reset the orchestrator if it's not working
        _orchestrator = None
        raise Exception(f"Orchestrator validation failed: {e}")
    
    return _orchestrator

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "OPTIONS,POST"
    }

def _send_websocket_message(connection_id: str, message: dict, domain: str, stage: str) -> bool:
    """Send a message to a WebSocket connection via API Gateway Management API"""
    try:
        api_gateway_management_api = boto3.client(
            'apigatewaymanagementapi',
            endpoint_url=f"https://{domain}/{stage}"
        )
        
        api_gateway_management_api.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(message)
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send WebSocket message to {connection_id}: {e}")
        return False

async def _process_sqs_message_and_stream_response(connection_id: str, query: str, context: str, query_type: str, 
                                                  domain: str, stage: str) -> None:
    """Process SQS message and stream agent response to WebSocket client"""
    try:
        logger.info(f"Starting SQS message processing for connection {connection_id}")
        
        # Send initial status
        _send_websocket_message(connection_id, {
            "type": "status",
            "message": "Processing your query...",
            "timestamp": time.time()
        }, domain, stage)
        
        # Execute the query with native Strands streaming
        try:
            logger.info("Getting orchestrator instance for streaming")
            orchestrator = _get_orchestrator()
            logger.info("Orchestrator retrieved, starting route_query")
            
            # Use native Strands streaming
            event_count = 0
            start_time = time.time()
            
            async for stream_event in orchestrator.route_query(query, context, query_type):
                event_count += 1
                current_time = time.time()
                elapsed_time = current_time - start_time
                
                logger.info(f"Received stream event #{event_count}: type={stream_event.get('type')} (elapsed: {elapsed_time:.2f}s)")
                
                # Check if we're approaching Lambda timeout (leave 30 seconds buffer)
                if elapsed_time > 870:  # 15 minutes - 30 seconds buffer
                    logger.warning("Approaching Lambda timeout, sending timeout message and stopping")
                    _send_websocket_message(connection_id, {
                        "type": "error",
                        "error": "Query timeout - Lambda execution time limit reached",
                        "timestamp": current_time
                    }, domain, stage)
                    break
                
                if stream_event.get("type") == "stream":
                    # This is a Strands event - process it based on event type
                    event = stream_event.get("event", {})
                    logger.info(f"Processing stream event: {list(event.keys())}")
                    
                    # Handle different types of Strands events
                    if "data" in event:
                        # Text generation event - stream text to client
                        logger.info(f"Sending text chunk: {len(event['data'])} characters")
                        _send_websocket_message(connection_id, {
                            "type": "text_chunk",
                            "data": event["data"],
                            "timestamp": current_time
                        }, domain, stage)
                        
                    elif "current_tool_use" in event:
                        # Tool usage event
                        tool_info = event["current_tool_use"]
                        logger.info(f"Sending tool use event: {tool_info.get('name', 'Unknown')}")
                        _send_websocket_message(connection_id, {
                            "type": "tool_use",
                            "tool_name": tool_info.get("name", "Unknown"),
                            "tool_id": tool_info.get("toolUseId", ""),
                            "input": tool_info.get("input", {}),
                            "timestamp": current_time
                        }, domain, stage)
                        
                    elif "reasoning" in event and event.get("reasoning"):
                        # Reasoning event
                        logger.info("Sending reasoning event")
                        _send_websocket_message(connection_id, {
                            "type": "reasoning",
                            "text": event.get("reasoningText", ""),
                            "signature": event.get("reasoning_signature", ""),
                            "timestamp": current_time
                        }, domain, stage)
                        
                    elif "start" in event and event.get("start"):
                        # New cycle started
                        logger.info("Sending cycle start event")
                        _send_websocket_message(connection_id, {
                            "type": "cycle_start",
                            "timestamp": current_time
                        }, domain, stage)
                        
                    elif "message" in event:
                        # New message created
                        message = event["message"]
                        logger.info(f"Sending message event: role={message.get('role', 'unknown')}")
                        
                        # Extract message content if available
                        message_content = None
                        if hasattr(message, 'content'):
                            message_content = message.content
                        elif isinstance(message, dict) and 'content' in message:
                            message_content = message['content']
                        
                        _send_websocket_message(connection_id, {
                            "type": "message",
                            "role": message.get("role", "unknown"),
                            "content": message_content,
                            "timestamp": current_time
                        }, domain, stage)
                        
                    elif "result" in event:
                        # Final result
                        result = event["result"]
                        logger.info("Sending final result event")
                        _send_websocket_message(connection_id, {
                            "type": "result",
                            "content": result.content if hasattr(result, 'content') else str(result),
                            "agent": stream_event.get("agent", "unknown"),
                            "query_type": stream_event.get("query_type", "general"),
                            "timestamp": current_time
                        }, domain, stage)
                        
                elif stream_event.get("type") == "error":
                    # Error event
                    logger.error(f"Received error event: {stream_event.get('error')}")
                    _send_websocket_message(connection_id, {
                        "type": "error",
                        "error": stream_event.get("error", "Unknown error"),
                        "timestamp": current_time
                    }, domain, stage)
                    break
                    
            total_time = time.time() - start_time
            logger.info(f"Streaming completed after {event_count} events in {total_time:.2f} seconds")
            
            # Send completion status
            _send_websocket_message(connection_id, {
                "type": "status",
                "message": "Query completed successfully",
                "timestamp": time.time()
            }, domain, stage)
            
        except Exception as e:
            logger.error(f"Error in agent streaming: {e}")
            logger.error(f"Error type: {type(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            _send_websocket_message(connection_id, {
                "type": "error",
                "error": f"Agent execution failed: {str(e)}",
                "timestamp": time.time()
            }, domain, stage)
            
    except Exception as e:
        logger.error(f"Error in SQS message processing: {e}")
        logger.error(f"Error type: {type(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        _send_websocket_message(connection_id, {
            "type": "error",
            "error": f"SQS message processing failed: {str(e)}",
            "timestamp": time.time()
        }, domain, stage)


async def _process_sqs_message(sqs_event: dict) -> None:
    """Process SQS message and stream response to WebSocket"""
    try:
        logger.info("Processing SQS message")
        
        # Process each record in the SQS event
        for record in sqs_event.get('Records', []):
            try:
                # Parse the message body
                message_body = json.loads(record.get('body', '{}'))
                logger.info(f"Processing SQS message: {list(message_body.keys())}")
                
                # Extract message details
                connection_id = message_body.get('connection_id')
                domain = message_body.get('domain')
                stage = message_body.get('stage')
                question = message_body.get('question')
                context = message_body.get('context', '')
                query_type = message_body.get('query_type', 'general')
                
                if not all([connection_id, domain, stage, question]):
                    logger.error(f"Missing required fields in SQS message: {message_body}")
                    continue
                
                logger.info(f"Processing query for connection {connection_id}: {len(question)} characters")
                
                # Process the message and stream response
                await _process_sqs_message_and_stream_response(
                    connection_id, question, context, query_type, domain, stage
                )
                
                logger.info(f"Successfully processed SQS message for connection {connection_id}")
                
            except Exception as e:
                logger.error(f"Error processing SQS record: {e}")
                import traceback
                logger.error(f"Full traceback: {traceback.format_exc()}")
                continue
                
    except Exception as e:
        logger.error(f"Error in SQS message processing: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")

def _build_reference_numbers(resp):
    """
    Assign stable numbers to unique retrieved references across the whole response.
    Returns (ref_num_map, ordered_refs) where:
      - ref_num_map maps a retrievedReference 'key' to its number
      - ordered_refs is a list of {id, source, source_link, page, chunk, text}
    """
    logger.debug(f"Building reference numbers from response with {len(resp.get('citations', []))} citations")
    
    ref_num_map = {}
    ordered_refs = []
    next_num = 1

    if "citations" not in resp:
        logger.debug("No citations found in response")
        return ref_num_map, ordered_refs

    def ref_key(r):
        # Build a stable key for a reference
        meta = r.get("metadata", {})
        page = meta.get("x-amz-bedrock-kb-document-page-number", "Unknown")
        chunk = meta.get("x-amz-bedrock-kb-document-chunk", "Unknown")
        uri = (r.get("location", {}).get("webLocation", {}) or {}).get("url") \
              or (r.get("location", {}).get("s3Location", {}) or {}).get("uri") \
              or "Knowledge Base Source"
        return (uri, str(page), str(chunk))

    for c in resp.get("citations", []):
        logger.debug(f"Processing citation with {len(c.get('retrievedReferences', []))} retrieved references")
        for r in c.get("retrievedReferences", []):
            k = ref_key(r)
            if k not in ref_num_map:
                ref_num_map[k] = next_num
                # materialize a record for the UI
                uri, page, chunk = k
                text_obj = r.get("content") or {}
                snippet = text_obj.get("text") if isinstance(text_obj, dict) else (text_obj or "")
                
                # Clean up the source name and create proper S3 link
                source_name = uri
                source_link = uri
                
                # If it's an S3 URI, clean it up and create a proper link
                if uri.startswith("s3://johnlscott/"):
                    # Remove the s3://johnlscott/ prefix
                    file_name = uri.replace("s3://johnlscott/", "")
                    source_name = file_name
                    # Create the proper S3 link
                    source_link = f"https://johnlscott.s3.amazonaws.com/{file_name}"
                elif uri.startswith("s3://"):
                    # Handle other S3 URIs
                    file_name = uri.replace("s3://", "")
                    source_name = file_name
                    source_link = f"https://{file_name.replace('/', '.s3.amazonaws.com/', 1)}"
                
                ordered_refs.append({
                    "id": next_num,
                    "source": source_name,
                    "source_link": source_link,
                    "page": page,
                    "chunk": snippet,
                    "text": snippet
                })
                logger.debug(f"Added reference {next_num}: {source_name} (page {page})")
                next_num += 1

    logger.info(f"Built {len(ordered_refs)} unique references from {len(resp.get('citations', []))} citations")
    return ref_num_map, ordered_refs


def _inject_inline_citations(resp, answer):
    """
    Inserts [n] markers into the answer text based on spans & retrievedReferences.
    Returns (answer_with_cites, ordered_refs)
    """
    logger.debug(f"Injecting inline citations into answer of length {len(answer) if answer else 0}")
    
    if not answer or "citations" not in resp:
        logger.debug("No answer or citations to process")
        return answer, []

    ref_num_map, ordered_refs = _build_reference_numbers(resp)
    if not ref_num_map:
        logger.debug("No reference numbers built")
        return answer, ordered_refs

    # Build a list of insert operations: (pos, "[1][2]")
    inserts = []
    for c in resp.get("citations", []):
        part = c.get("generatedResponsePart", {}).get("textResponsePart", {})
        span = part.get("span") or {}
        end = span.get("end")
        if end is None:
            logger.debug("Citation span end position not found")
            continue

        nums = []
        for r in c.get("retrievedReferences", []):
            meta = r.get("metadata", {})
            page = meta.get("x-amz-bedrock-kb-document-page-number", "Unknown")
            chunk = meta.get("x-amz-bedrock-kb-document-chunk", "Unknown")
            uri = (r.get("location", {}).get("webLocation", {}) or {}).get("url") \
                  or (r.get("location", {}).get("s3Location", {}) or {}).get("uri") \
                  or "Knowledge Base Source"
            key = (uri, str(page), str(chunk))
            n = ref_num_map.get(key)
            if n and n not in nums:
                nums.append(n)

        if nums:
            inserts.append((int(end), "".join(f"[{n}]" for n in sorted(nums))))
            logger.debug(f"Added citation insert at position {end}: {nums}")

    if not inserts:
        logger.debug("No citation inserts to apply")
        return answer, ordered_refs

    # Apply inserts from end to start so indices don't shift
    inserts.sort(key=lambda x: x[0], reverse=True)
    out = answer
    for pos, marker in inserts:
        if 0 <= pos <= len(out):
            out = out[:pos] + marker + out[pos:]
            logger.debug(f"Applied citation marker '{marker}' at position {pos}")

    logger.info(f"Injected {len(inserts)} citation markers into answer")
    return out, ordered_refs


async def _handle_agent_query(body: dict) -> dict:
    """Handle agent query requests"""
    logger.info("Handling agent query request")
    logger.debug(f"Agent query body: {json.dumps(body, default=str)}")
    
    try:
        # Extract query parameters
        query = body.get("question", "").strip()
        context_text = body.get("context", "").strip()
        query_type = body.get("query_type", "general").strip()
        
        if not query:
            logger.warning("Agent query missing required 'question' field")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Question is required"})
            }
        
        logger.info(f"Processing agent query: '{query}' (type: {query_type})")
        logger.info(f"Context length: {len(context_text)} characters")
        
        # Execute query through Strands agent orchestrator
        logger.info("Executing query through Strands agent orchestrator")
        orchestrator = _get_orchestrator()
        
        print("=== CALLING route_query_sync METHOD ===")
        logger.info("Calling orchestrator.route_query_sync() method")
        result = await orchestrator.route_query_sync(query, context_text, query_type)
        
        print(f"=== AGENT QUERY COMPLETED, RESULT LENGTH: {len(str(result))} ===")
        logger.info(f"Agent query completed successfully, result length: {len(str(result))}")
        
        if result.get("success"):
            logger.info("Agent query executed successfully")
            logger.debug(f"Agent query result: {json.dumps(result, default=str)}")
            
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "success": True,
                    "content": result.get("content", ""),
                    "agent": result.get("agent", "unknown"),
                    "query_type": result.get("query_type", "general"),
                    "tools_available": result.get("tools_available", 0),
                    "tools_used": result.get("tools_used", 0),
                    "selected_agent": result.get("selected_agent", "unknown")
                }, default=str)
            }
        else:
            logger.error(f"Agent query failed: {result.get('error', 'Unknown error')}")
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "success": False,
                    "error": result.get("error", "Agent execution failed"),
                    "agent": result.get("agent", "unknown"),
                    "query_type": result.get("query_type", "general")
                }, default=str)
            }
            
    except Exception as e:
        logger.error(f"Error handling agent query: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "success": False,
                "error": f"Internal server error: {str(e)}"
            }, default=str)
        }


async def _handle_workflow_execution(body: dict) -> dict:
    """Handle workflow execution requests"""
    logger.info("Handling workflow execution request")
    logger.debug(f"Workflow execution body: {json.dumps(body, default=str)}")
    
    try:
        workflow_name = body.get("workflow")
        parameters = body.get("parameters", {})
        
        logger.info(f"Executing workflow: {workflow_name} with {len(parameters)} parameters")
        logger.debug(f"Workflow parameters: {json.dumps(parameters, default=str)}")
        
        if not workflow_name:
            logger.warning("Workflow execution missing required 'workflow' field")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Workflow name is required"})
            }
        
        # Execute workflow through Strands agent orchestrator
        logger.info("Executing workflow through Strands agent orchestrator")
        orchestrator = _get_orchestrator()
        
        # Execute the workflow
        result = await orchestrator.execute_workflow(workflow_name, parameters)
        
        if result.get("success"):
            logger.info(f"Workflow {workflow_name} executed successfully")
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "success": True,
                    "workflow": workflow_name,
                    "results": result.get("results", {}),
                    "message": f"Workflow {workflow_name} completed successfully"
                }, default=str)
            }
        else:
            logger.error(f"Workflow {workflow_name} execution failed: {result.get('error', 'Unknown error')}")
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "success": False,
                    "workflow": workflow_name,
                    "error": result.get("error", "Workflow execution failed")
                }, default=str)
            }
            
    except Exception as e:
        logger.error(f"Error executing workflow: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "success": False,
                "error": f"Internal server error: {str(e)}"
            }, default=str)
        }

async def _handle_debug_request(body: dict) -> dict:
    """Handle debug requests to test tool execution and orchestrator state"""
    print("=== ENTERING DEBUG HANDLER ===")
    logger.info("Handling debug request")
    
    try:
        debug_type = body.get("debug_type", "status")
        
        print(f"=== DEBUG TYPE: {debug_type} ===")
        logger.info(f"Debug request type: {debug_type}")
        
        orchestrator = _get_orchestrator()
        
        if debug_type == "status":
            # Get orchestrator status
            debug_info = orchestrator.get_debug_info()
            print(f"=== DEBUG STATUS: {debug_info} ===")
            return {
                "statusCode": 200,
                "headers": {**_cors_headers(), "Content-Type": "application/json"},
                "body": json.dumps(debug_info)
            }
            
        elif debug_type == "test_tool":
            # Test a specific tool
            tool_name = body.get("tool_name", "")
            parameters = body.get("parameters", {})
            
            if not tool_name:
                return {
                    "statusCode": 400,
                    "body": json.dumps({"error": "tool_name is required for tool testing"})
                }
            
            print(f"=== TESTING TOOL: {tool_name} ===")
            logger.info(f"Testing tool: {tool_name} with parameters: {parameters}")
            
            result = orchestrator.debug_tool_execution(tool_name, parameters)
            print(f"=== TOOL TEST RESULT: {result} ===")
            
            return {
                "statusCode": 200,
                "headers": {**_cors_headers(), "Content-Type": "application/json"},
                "body": json.dumps(result)
            }
            
        elif debug_type == "list_tools":
            # List all available tools
            tools_info = orchestrator.get_available_tools()
            print(f"=== AVAILABLE TOOLS: {tools_info} ===")
            
            return {
                "statusCode": 200,
                "headers": {**_cors_headers(), "Content-Type": "application/json"},
                "body": json.dumps({"tools": tools_info})
            }
            
        else:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": f"Unknown debug type: {debug_type}"})
            }
            
    except Exception as e:
        print(f"=== DEBUG REQUEST FAILED: {str(e)} ===")
        logger.error(f"Failed to process debug request: {str(e)}", exc_info=True)
        import traceback
        print(f"=== FULL TRACEBACK: {traceback.format_exc()} ===")
        return {
            "statusCode": 500,
            "headers": _cors_headers(),
            "body": json.dumps({"error": "Failed to process debug request", "details": str(e)})
        }

async def _async_handler(event, context):
    # Force immediate output to ensure we see this
    print("=== LAMBDA FUNCTION STARTED ===")
    print(f"Event type: {event.get('httpMethod', 'Unknown')}")
    print(f"Function: {context.function_name}, Version: {context.function_version}")
    
    logger.info("Lambda function invoked")
    logger.info(f"Event type: {event.get('httpMethod', 'Unknown')}")
    logger.debug(f"Full event: {json.dumps(event, default=str)}")
    logger.info(f"Context: function_name={context.function_name}, function_version={context.function_version}, memory_limit={context.memory_limit_in_mb}MB")
    
    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        logger.info("Handling CORS preflight request")
        return {"statusCode": 200, "headers": _cors_headers(), "body": ""}

    try:
        # Check if this is an SQS event
        if event.get("Records") and event["Records"][0].get("eventSource") == "aws:sqs":
            logger.info("Request identified as SQS event")
            print(f"=== USING SQS PATH ===")
            
            # Process SQS message and stream response to WebSocket
            await _process_sqs_message(event)
            
            # Return success response for SQS processing
            return {
                "statusCode": 200,
                "body": "SQS message processed successfully"
            }
        
        # Handle HTTP requests (agent queries, workflows, debug)
        body = event.get("body") or "{}"
        logger.debug(f"Raw body: {body}")
        
        if event.get("isBase64Encoded"):
            logger.debug("Decoding base64 encoded body")
            body = json.loads(base64.b64decode(body))
        else:
            logger.debug("Parsing JSON body")
            body = json.loads(body)

        logger.info(f"Parsed request body with keys: {list(body.keys())}")
        logger.debug(f"Request body content: {json.dumps(body, default=str)}")

        # Check if this is an agent query or workflow execution
        if body.get("use_agents") or body.get("workflow"):
            logger.info("Request identified as agent/workflow request")
            print(f"=== USING AGENT/WORKFLOW PATH ===")
            # Use the Strands multi-agent system with AgentCore Gateway
            if body.get("workflow"):
                logger.info("Executing workflow")
                return await _handle_workflow_execution(body)
            else:
                logger.info("Processing agent query")
                return await _handle_agent_query(body)
        
        # Check if this is a debug request
        elif body.get("debug_type"):
            logger.info("Request identified as debug request")
            print(f"=== USING DEBUG PATH ===")
            return await _handle_debug_request(body)
        
        else:
            logger.info("Request identified as default HTTP request")
            print(f"=== USING DEFAULT HTTP PATH ===")
            # Fall back to original Bedrock knowledge base approach
            question = body.get("question")
            context_text = body.get("context")
            
            logger.info(f"Knowledge base query: question_length={len(question) if question else 0}, context_length={len(context_text) if context_text else 0}")
            
            if not question or not context_text:
                logger.warning("Missing required fields: question or context")
                return {
                    "statusCode": 400,
                    "headers": _cors_headers(),
                    "body": json.dumps({"error": "Question and context are required"})
                }

            # Build RetrieveAndGenerate request
            logger.info("Building Bedrock RetrieveAndGenerate request")
            req = {
                "input": {"text": question},
                "retrieveAndGenerateConfiguration": {
                    "type": "KNOWLEDGE_BASE",
                    "knowledgeBaseConfiguration": {
                        "knowledgeBaseId": KB_ID,
                        "modelArn": "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0",
                        "retrievalConfiguration": {
                            "vectorSearchConfiguration": { "numberOfResults": 6 }
                        },
                        "generationConfiguration": {
                            "promptTemplate": {
                                "textPromptTemplate": (
                                    # REQUIRED tokens:
                                    "$output_format_instructions$\n"
                                    "User question:\n$query$\n\n"
                                    "Property context (not from KB):\n<context>\n"
                                    f"{context_text}\n"
                                    "</context>\n\n"
                                    "Relevant excerpts from the knowledge base:\n$search_results$\n\n"
                                    "Instructions:\n"
                                    "- Cite specific SMC sections with [1], [2], etc.\n"
                                    "- If information is missing, say so.\n"
                                    "Final answer:"
                                )
                            }
                        }
                    }
                }
            }
        
            logger.debug(f"Bedrock request: {json.dumps(req, default=str)}")
            logger.info("Calling Bedrock retrieveAndGenerate API")
            
            resp = _bedrock.retrieve_and_generate(**req)
            
            logger.info("Bedrock API call completed successfully")
            logger.debug(f"Bedrock response keys: {list(resp.keys())}")

            raw_answer = (resp.get("output") or {}).get("text") or ""
            logger.info(f"Raw answer length: {len(raw_answer)}")
            logger.debug(f"Raw answer: {raw_answer[:500]}...")
            
            answer_with_cites, ordered_refs = _inject_inline_citations(resp, raw_answer)
            logger.info(f"Answer with citations length: {len(answer_with_cites)}, references count: {len(ordered_refs)}")

            result = {
                "answer": answer_with_cites or f'I found relevant info for: "{question}", but no direct model output was returned.',
                "citations": ordered_refs,  # Now has proper structure with source_link
                "citation_map": { str(r["id"]): r for r in ordered_refs },
                "confidence": min(0.95, 0.7 + 0.05 * len(ordered_refs)) if ordered_refs else 0.8
            }

            logger.info(f"Final result prepared: answer_length={len(result['answer'])}, citations={len(result['citations'])}, confidence={result['confidence']}")
            logger.debug(f"Final result: {json.dumps(result, default=str)}")

            return {
                "statusCode": 200,
                "headers": {**_cors_headers(), "Content-Type": "application/json"},
                "body": json.dumps(result)
            }

    except Exception as e:
        logger.error(f"Lambda function failed with error: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": _cors_headers(),
            "body": json.dumps({"error": "Failed to process request", "details": str(e)})
        }

def handler(event, context):
    """Synchronous wrapper for the async handler"""
    try:
        # Add context information logging
        logger.info(f"Lambda handler invoked - Function: {context.function_name}")
        logger.info(f"Lambda timeout: {context.get_remaining_time_in_millis()}ms remaining")
        logger.info(f"Lambda memory: {context.memory_limit_in_mb}MB allocated")
        
        # Run the async handler
        result = asyncio.run(_async_handler(event, context))
        
        logger.info("Lambda handler completed successfully")
        return result
        
    except Exception as e:
        logger.error(f"Lambda handler failed with error: {str(e)}")
        logger.error(f"Error type: {type(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        # Return a proper error response
        return {
            "statusCode": 500,
            "headers": _cors_headers(),
            "body": json.dumps({"error": "Lambda execution failed", "details": str(e)})
        }
