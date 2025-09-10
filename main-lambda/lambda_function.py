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

# Session-aware orchestrator management
_orchestrators = {}  # Dictionary to store orchestrators by connection_id

def _get_orchestrator(connection_id: str = None):
    """Get or create the Strands agent orchestrator instance for a specific connection"""
    global _orchestrators
    
    # If no connection_id provided, create a fresh instance (for non-websocket requests)
    if not connection_id:
        print("=== CREATING NEW STRANDS ORCHESTRATOR INSTANCE (NO CONNECTION ID) ===")
        logger.info("Creating new Strands agent orchestrator instance (no connection ID)")
        try:
            orchestrator = StrandsAgentOrchestrator()
            print("=== ORCHESTRATOR INSTANCE CREATED SUCCESSFULLY ===")
            logger.info("Orchestrator instance created successfully")
            return orchestrator
        except Exception as e:
            print(f"=== FAILED TO CREATE ORCHESTRATOR INSTANCE: {e} ===")
            logger.error(f"Failed to create orchestrator instance: {e}")
            logger.error(f"Error type: {type(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
    
    # For websocket requests, use connection_id to maintain session state
    if connection_id not in _orchestrators:
        print(f"=== CREATING NEW STRANDS ORCHESTRATOR INSTANCE FOR CONNECTION {connection_id} ===")
        logger.info(f"Creating new Strands agent orchestrator instance for connection {connection_id}")
        try:
            _orchestrators[connection_id] = StrandsAgentOrchestrator()
            print(f"=== ORCHESTRATOR INSTANCE CREATED SUCCESSFULLY FOR CONNECTION {connection_id} ===")
            logger.info(f"Orchestrator instance created successfully for connection {connection_id}")
        except Exception as e:
            print(f"=== FAILED TO CREATE ORCHESTRATOR INSTANCE FOR CONNECTION {connection_id}: {e} ===")
            logger.error(f"Failed to create orchestrator instance for connection {connection_id}: {e}")
            logger.error(f"Error type: {type(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
    else:
        print(f"=== REUSING EXISTING ORCHESTRATOR INSTANCE FOR CONNECTION {connection_id} ===")
        logger.debug(f"Reusing existing Strands agent orchestrator instance for connection {connection_id}")
    
    orchestrator = _orchestrators[connection_id]
    
    # Validate the orchestrator is working
    try:
        status = orchestrator.get_system_status()
        logger.info(f"Orchestrator status for connection {connection_id}: {status}")
    except Exception as e:
        logger.error(f"Orchestrator validation failed for connection {connection_id}: {e}")
        # Reset the orchestrator if it's not working
        del _orchestrators[connection_id]
        raise Exception(f"Orchestrator validation failed for connection {connection_id}: {e}")
    
    return orchestrator

def _cleanup_orchestrator(connection_id: str):
    """Clean up orchestrator instance when connection is closed"""
    global _orchestrators
    if connection_id in _orchestrators:
        print(f"=== CLEANING UP ORCHESTRATOR FOR CONNECTION {connection_id} ===")
        logger.info(f"Cleaning up orchestrator for connection {connection_id}")
        del _orchestrators[connection_id]

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "OPTIONS,POST"
    }

def _extract_tool_json_and_citations(text: str):
    """
    Extract a JSON object (prefer fenced ```json block) from agent text and return (parsed_obj, citations).
    Returns (None, None) if nothing parseable is found.
    """
    if not isinstance(text, str) or not text.strip():
        return None, None
    import json, re
    # 1) Whole-string JSON
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            if obj.get("tool") == "rag_query" or "citations" in obj:
                return obj, obj.get("citations")
    except Exception:
        pass
    # 2) Fenced block
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if not m:
        return None, None
    try:
        obj = json.loads(m.group(1))
        return obj, obj.get("citations") if isinstance(obj, dict) else None
    except Exception:
        return None, None

from botocore.config import Config

_WS_CLIENTS = {}  # key: base_url -> boto3 client
_BOTO_CFG = Config(
    max_pool_connections=50,
    retries={"max_attempts": 3, "mode": "standard"},
    connect_timeout=2,
    read_timeout=5,
)

def _get_ws_client(domain: str, stage: str):
    base_url = f"https://{domain}/{stage}"
    cli = _WS_CLIENTS.get(base_url)
    if cli is None:
        cli = boto3.client("apigatewaymanagementapi", endpoint_url=base_url, config=_BOTO_CFG)
        _WS_CLIENTS[base_url] = cli
    return cli

async def _send_websocket_message(connection_id: str, message: dict, domain: str, stage: str) -> bool:
    api = _get_ws_client(domain, stage)
    payload = json.dumps(message).encode("utf-8")
    try:
        # run the blocking boto3 call in a thread so streaming stays snappy
        await asyncio.to_thread(api.post_to_connection, ConnectionId=connection_id, Data=payload)
        return True
    except api.exceptions.GoneException:
        logger.info(f"WS connection {connection_id} is gone (410).")
        # Clean up orchestrator for this connection
        _cleanup_orchestrator(connection_id)
        return False
    except Exception as e:
        logger.error(f"WS send failed: {e}")
        # if endpoint rotated or client went bad, drop from cache so next call recreates it
        _WS_CLIENTS.pop(f"https://{domain}/{stage}", None)
        return False

import re

# --- state for hiding fenced JSON while we stream ---
in_json_fence = False
json_buf = []
citations_emitted = False

async def _filter_stream_and_emit_citations(
    text: str,
    conn_id: str,
    dom: str,
    stg: str,
) -> str:
    """
    Remove any ```json ... ``` blocks from streaming text.
    If a block is found, parse it once and emit a 'citations' frame.
    Returns the user-visible text with the fenced JSON removed.
    """
    global in_json_fence, json_buf, citations_emitted, citations_buffer, citation_map_buffer

    out = []
    i = 0
    while i < len(text):
        if not in_json_fence:
            start = text.find("```json", i)
            if start == -1:
                out.append(text[i:])
                break
            out.append(text[i:start])
            i = start + len("```json")
            in_json_fence = True
            json_buf = []
        else:
            end = text.find("```", i)
            if end == -1:
                json_buf.append(text[i:])
                break
            json_buf.append(text[i:end])
            block = "".join(json_buf).strip()

            # parse & emit citations once
            if not citations_emitted:
                parsed_obj, citations = _extract_tool_json_and_citations(block)
                if citations:
                    await _send_websocket_message(conn_id, {
                        "type": "citations",
                        "citations": citations,
                        "timestamp": time.time()
                    }, dom, stg)
                    citations_buffer = citations
                    citation_map_buffer = {
                        str(c["id"]): c
                        for c in citations
                        if isinstance(c, dict) and "id" in c
                    }
                    citations_emitted = True

            in_json_fence = False
            json_buf = []
            i = end + 3  # skip closing fence
    return "".join(out)


async def _strip_and_emit_from_block(
    txt: str,
    conn_id: str,
    dom: str,
    stg: str,
) -> str:
    """
    For non-streamed full messages: emit citations from any fenced block(s),
    then return the text with ALL fenced blocks removed.
    """
    # Emit citations (first match is enough)
    for m in re.finditer(r"```json\s*(\{[\s\S]*?\})\s*```", txt, flags=re.DOTALL | re.IGNORECASE):
        if not citations_emitted:
            parsed_obj, citations = _extract_tool_json_and_citations(m.group(1))
            if citations:
                await _send_websocket_message(conn_id, {
                    "type": "citations",
                    "citations": citations,
                    "timestamp": time.time()
                }, dom, stg)
    # Remove every fenced json block from visible text
    cleaned = re.sub(r"```json[\s\S]*?```", "", txt, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()

async def _process_sqs_message_and_stream_response(connection_id: str, query: str, context: str, query_type: str, 
                                                  domain: str, stage: str) -> None:
    """Process SQS message and stream agent response to WebSocket client"""

    citations_buffer = []
    citation_map_buffer = {}
    try:
        logger.info(f"Starting SQS message processing for connection {connection_id}")
        
        # Send initial status
        await _send_websocket_message(connection_id, {
            "type": "status",
            "message": "Processing your query...",
            "timestamp": time.time()
        }, domain, stage)
        
        # Execute the query with native Strands streaming
        try:
            logger.info("Getting orchestrator instance for streaming")
            orchestrator = _get_orchestrator(connection_id)  # Pass connection_id for session awareness
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
                    await _send_websocket_message(connection_id, {
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
                        # Text generation event - stream text to client (hide fenced JSON)
                        safe = await _filter_stream_and_emit_citations(event["data"], connection_id, domain, stage)
                        if safe:
                            logger.info(f"Sending text chunk: {len(safe)} characters (after filtering)")
                            await _send_websocket_message(connection_id, {
                                "type": "text_chunk",
                                "data": safe,
                                "timestamp": current_time
                            }, domain, stage)
                        
                    elif "current_tool_use" in event:
                        # Tool usage event
                        tool_info = event["current_tool_use"]
                        logger.info(f"Sending tool use event: {tool_info.get('name', 'Unknown')}")
                        await _send_websocket_message(connection_id, {
                            "type": "tool_use",
                            "tool_name": tool_info.get("name", "Unknown"),
                            "tool_id": tool_info.get("toolUseId", ""),
                            "input": tool_info.get("input", {}),
                            "timestamp": current_time
                        }, domain, stage)
                        
                    elif "reasoning" in event and event.get("reasoning"):
                        # Reasoning event
                        logger.info("Sending reasoning event")
                        await _send_websocket_message(connection_id, {
                            "type": "reasoning",
                            "text": event.get("reasoningText", ""),
                            "signature": event.get("reasoning_signature", ""),
                            "timestamp": current_time
                        }, domain, stage)
                        
                    elif "start" in event and event.get("start"):
                        # New cycle started
                        logger.info("Sending cycle start event")
                        await _send_websocket_message(connection_id, {
                            "type": "cycle_start",
                            "timestamp": current_time
                        }, domain, stage)
                        
                    elif "message" in event:
                        message = event["message"]
                        logger.info(f"Sending message event: role={message.get('role', 'unknown')}")

                        # Extract content
                        message_content = None
                        if hasattr(message, 'content'):
                            message_content = message.content
                        elif isinstance(message, dict) and 'content' in message:
                            message_content = message['content']

                        if isinstance(message_content, str) and message_content:
                            safe = await _filter_stream_and_emit_citations(message_content, connection_id, domain, stage)
                            if safe:
                                await _send_websocket_message(connection_id, {
                                    "type": "message",
                                    "role": message.get("role", "unknown"),
                                    "content": safe,
                                    "timestamp": current_time
                                }, domain, stage)
                            continue

                        elif isinstance(message_content, list):
                            pretty_text_parts = []
                            for item in message_content:
                                if isinstance(item, dict):
                                    if "text" in item and isinstance(item["text"], str):
                                        pretty_text_parts.append(
                                            await _strip_and_emit_from_block(item["text"], connection_id, domain, stage)
                                        )
                                    if "toolResult" in item and isinstance(item["toolResult"], dict):
                                        tr = item["toolResult"]
                                        tr_content = tr.get("content")
                                        if isinstance(tr_content, list):
                                            tr_texts = [seg.get("text", "") for seg in tr_content if isinstance(seg, dict) and "text" in seg]
                                            if tr_texts:
                                                pretty_text_parts.append(
                                                    await _strip_and_emit_from_block("\n".join(tr_texts), connection_id, domain, stage)
                                                )
                            safe_text = "\n".join([t for t in pretty_text_parts if t]).strip()
                            if safe_text:
                                await _send_websocket_message(connection_id, {
                                    "type": "message",
                                    "role": message.get("role", "unknown"),
                                    "content": safe_text,
                                    "timestamp": current_time
                                }, domain, stage)
                            continue

                        # Fall back: forward raw (non-string/non-list) content as-is
                        await _send_websocket_message(connection_id, {
                            "type": "message",
                            "role": message.get("role", "unknown"),
                            "content": message_content,
                            "timestamp": current_time
                        }, domain, stage)
                        
                    elif "result" in event:
                        result = event["result"]
                        logger.info("Sending final result event")

                        # Try to parse citations from the final content as a fallback
                        final_content = result.content if hasattr(result, 'content') else str(result)
                        if isinstance(final_content, str):
                            parsed_obj, parsed_cites = _extract_tool_json_and_citations(final_content)
                            if parsed_cites and not citations_buffer:
                                citations_buffer = parsed_cites
                                citation_map_buffer = {str(c["id"]): c for c in parsed_cites if isinstance(c, dict) and "id" in c}

                        await _send_websocket_message(connection_id, {
                            "type": "result",
                            "content": final_content,
                            "agent": stream_event.get("agent", "unknown"),
                            "query_type": stream_event.get("query_type", "general"),
                            "citations": citations_buffer,            # <—— include them
                            "citation_map": citation_map_buffer,      # optional, your UI supports it
                            "timestamp": current_time
                        }, domain, stage)
                        
                elif stream_event.get("type") == "error":
                    # Error event
                    logger.error(f"Received error event: {stream_event.get('error')}")
                    await _send_websocket_message(connection_id, {
                        "type": "error",
                        "error": stream_event.get("error", "Unknown error"),
                        "timestamp": current_time
                    }, domain, stage)
                    break
                    
            total_time = time.time() - start_time
            logger.info(f"Streaming completed after {event_count} events in {total_time:.2f} seconds")
            
            # Send completion status
            await _send_websocket_message(connection_id, {
                "type": "status",
                "message": "Query completed successfully",
                "timestamp": time.time()
            }, domain, stage)
            
        except Exception as e:
            logger.error(f"Error in agent streaming: {e}")
            logger.error(f"Error type: {type(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            await _send_websocket_message(connection_id, {
                "type": "error",
                "error": f"Agent execution failed: {str(e)}",
                "timestamp": time.time()
            }, domain, stage)
            
    except Exception as e:
        logger.error(f"Error in SQS message processing: {e}")
        logger.error(f"Error type: {type(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        await _send_websocket_message(connection_id, {
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
                    "citations": result.get("citations", []),
                    "confidence": result.get("confidence"),
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
