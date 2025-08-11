import json
import os
import boto3
import asyncio
import logging

# Configure basic logging for Lambda
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Reuse client across invocations
_bedrock = boto3.client("bedrock-agent-runtime", region_name=os.environ.get("AWS_REGION", "us-west-2"))

KB_ID = os.environ["KNOWLEDGE_BASE_ID"]
MODEL_ARN = os.environ["MODEL_ARN"]

# Initialize agent orchestrator
_orchestrator = None

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "OPTIONS,POST"
    }

def _build_reference_numbers(resp):
    """
    Assign stable numbers to unique retrieved references across the whole response.
    Returns (ref_num_map, ordered_refs) where:
      - ref_num_map maps a retrievedReference 'key' to its number
      - ordered_refs is a list of {id, source, source_link, page, chunk, text}
    """
    ref_num_map = {}
    ordered_refs = []
    next_num = 1

    if "citations" not in resp:
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
                next_num += 1

    return ref_num_map, ordered_refs

def _inject_inline_citations(resp, answer):
    """
    Inserts [n] markers into the answer text based on spans & retrievedReferences.
    Returns (answer_with_cites, ordered_refs)
    """
    if not answer or "citations" not in resp:
        return answer, []

    ref_num_map, ordered_refs = _build_reference_numbers(resp)
    if not ref_num_map:
        return answer, ordered_refs

    # Build a list of insert operations: (pos, "[1][2]")
    inserts = []
    for c in resp.get("citations", []):
        part = c.get("generatedResponsePart", {}).get("textResponsePart", {})
        span = part.get("span") or {}
        end = span.get("end")
        if end is None:
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

    if not inserts:
        return answer, ordered_refs

    # Apply inserts from end to start so indices don't shift
    inserts.sort(key=lambda x: x[0], reverse=True)
    out = answer
    for pos, marker in inserts:
        if 0 <= pos <= len(out):
            out = out[:pos] + marker + out[pos:]

    return out, ordered_refs

def _normalize_location_to_link(uri: str) -> (str, str):
    """Convert KB locations to a friendly source name + clickable link."""
    if not uri:
        return "Knowledge Base Source", "Knowledge Base Source"
    source_name = uri
    source_link = uri
    if uri.startswith("s3://johnlscott/"):
        file_name = uri.replace("s3://johnlscott/", "")
        source_name = file_name
        source_link = f"https://johnlscott.s3.amazonaws.com/{file_name}"
    elif uri.startswith("s3://"):
        file_name = uri.replace("s3://", "")
        source_name = file_name
        source_link = f"https://{file_name.replace('/', '.s3.amazonaws.com/', 1)}"
    return source_name, source_link


def _fallback_citations_from_retrieve(kb_client, kb_id: str, query: str, max_results: int = 6):
    """
    If retrieve_and_generate doesn't include citations, call retrieve() directly
    and synthesize a citations array from the top results.
    """
    try:
        res = kb_client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": max_results}}
        )
    except Exception as e:
        logger.warning(f"Fallback retrieve() failed: {e}")
        return []

    items = res.get("retrievalResults", []) or []
    citations = []
    for i, item in enumerate(items, start=1):
        loc = item.get("location", {}) or {}
        web_url = (loc.get("webLocation") or {}).get("url")
        s3_uri = (loc.get("s3Location") or {}).get("uri")
        uri = web_url or s3_uri or "Knowledge Base Source"
        source_name, source_link = _normalize_location_to_link(uri)

        text_obj = item.get("content") or {}
        snippet = text_obj.get("text") if isinstance(text_obj, dict) else (text_obj or "")

        meta = item.get("metadata", {}) or {}
        page = meta.get("x-amz-bedrock-kb-document-page-number", "Unknown")
        chunk = meta.get("x-amz-bedrock-kb-document-chunk", "Unknown")

        citations.append({
            "id": i,
            "source": source_name,
            "source_link": source_link,
            "page": str(page),
            "chunk": snippet,
            "text": snippet
        })
    return citations

async def _execute_rag_tool(parameters: dict) -> dict:
    """Execute RAG tool for knowledge base queries (with robust citations)."""
    logger.info("Executing RAG tool")
    query = parameters.get("query", "")
    context = parameters.get("context", "")

    logger.info(f"RAG parameters: query='{query[:80]}{'...' if len(query) > 80 else ''}', context_len={len(context)}")
    if not query:
        logger.warning("RAG tool: Query parameter is required")
        return {"error": "Query parameter is required"}

    try:
        # Citations-friendly prompt (important for spans/citations)
        req = {
            "input": {"text": query},
            "retrieveAndGenerateConfiguration": {
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": KB_ID,
                    "modelArn": MODEL_ARN,   # ensure same profile as main lambda
                    "retrievalConfiguration": {
                        "vectorSearchConfiguration": {"numberOfResults": 6}
                    },
                    "generationConfiguration": {
                        "promptTemplate": {
                            "textPromptTemplate": (
                                "$output_format_instructions$\n"
                                "User question:\n$query$\n\n"
                                "Property context (not from KB):\n<context>\n"
                                f"{context}\n"
                                "</context>\n\n"
                                "Relevant excerpts from the knowledge base:\n$search_results$\n\n"
                                "Instructions:\n"
                                "- Cite specific sections inline with [1], [2], etc.\n"
                                "- If information is missing, say so.\n"
                                "Final answer:"
                            )
                        }
                    }
                }
            }
        }

        logger.info("Calling Bedrock retrieve_and_generate()")
        resp = _bedrock.retrieve_and_generate(**req)
        logger.info(f"Bedrock response received; keys={list(resp.keys())}")

        raw_answer = (resp.get("output") or {}).get("text") or ""
        logger.info(f"Raw answer length: {len(raw_answer)}")

        # Primary path: build citations from RnG 'citations' using your existing helpers
        answer_with_cites, ordered_refs = _inject_inline_citations(resp, raw_answer)
        logger.info(f"Primary citations built from RnG: {len(ordered_refs)}")

        # Fallback: no citations → direct retrieve() and synthesize
        if not ordered_refs:
            logger.info("No citations from retrieve_and_generate; attempting fallback retrieve()")
            fallback = _fallback_citations_from_retrieve(_bedrock, KB_ID, query, max_results=6)
            if fallback:
                ordered_refs = fallback
                # Optional: append a simple sources line so markers appear
                if raw_answer.strip():
                    refs_line = " ".join(f"[{c['id']}]" for c in ordered_refs)
                    answer_with_cites = f"{raw_answer}\n\nSources: {refs_line}"
            logger.info(f"Fallback citations count: {len(ordered_refs)}")

        confidence = min(0.95, 0.7 + 0.05 * len(ordered_refs)) if ordered_refs else 0.8
        logger.info(f"RAG tool completed with confidence: {confidence}")

        # Also provide a citation_map for parity with main lambda
        citation_map = {str(c["id"]): c for c in ordered_refs}

        return {
            "answer": answer_with_cites or raw_answer,
            "citations": ordered_refs,
            "citation_map": citation_map,
            "confidence": confidence
        }

    except Exception as e:
        logger.error(f"RAG tool error: {e}", exc_info=True)
        return {"error": f"RAG tool execution failed: {str(e)}"}

async def _execute_property_analysis_tool(parameters: dict) -> dict:
    """Execute property analysis tool"""
    logger.info("Executing property analysis tool")
    address = parameters.get("address", "")
    analysis_type = parameters.get("analysis_type", "comprehensive")
    
    logger.info(f"Property analysis parameters: address='{address}', analysis_type='{analysis_type}'")
    
    if not address:
        logger.warning("Property analysis: Address parameter is required")
        return {"error": "Address parameter is required"}
    
    logger.info("Property analysis completed")
    # Placeholder implementation - replace with actual property analysis logic
    return {
        "address": address,
        "analysis_type": analysis_type,
        "results": {
            "zoning": "R-1 (Residential)",
            "permit_history": "No recent permits",
            "development_potential": "Medium",
            "recommendations": ["Consider ADU development", "Check setback requirements"]
        }
    }

async def _execute_market_analysis_tool(parameters: dict) -> dict:
    """Execute market analysis tool"""
    logger.info("Executing market analysis tool")
    location = parameters.get("location", "")
    property_type = parameters.get("property_type", "residential")
    timeframe = parameters.get("timeframe", "1year")
    
    logger.info(f"Market analysis parameters: location='{location}', property_type='{property_type}', timeframe='{timeframe}'")
    
    if not location:
        logger.warning("Market analysis: Location parameter is required")
        return {"error": "Location parameter is required"}
    
    logger.info("Market analysis completed")
    # Placeholder implementation - replace with actual market analysis logic
    return {
        "location": location,
        "property_type": property_type,
        "timeframe": timeframe,
        "market_insights": {
            "trend": "Increasing",
            "price_change": "+5.2%",
            "inventory": "Low",
            "days_on_market": "15"
        }
    }

async def _handle_tool_execution(body: dict) -> dict:
    """Handle direct tool execution requests from AgentCore Gateway"""
    logger.info("Handling tool execution request")
    try:
        tool_name = body.get("tool_name")
        # Filter out tool_name from parameters since it's not a tool parameter
        parameters = {k: v for k, v in body.items() if k != "tool_name"}
        
        logger.info(f"Tool execution: tool_name='{tool_name}', parameters={parameters}")
        
        if not tool_name:
            logger.warning("Tool execution: Tool name is required")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Tool name is required"})
            }
        
        logger.info(f"Executing tool: {tool_name}")
        # Execute the tool based on name
        if tool_name == "rag_query":
            result = await _execute_rag_tool(parameters)
        elif tool_name == "property_analysis":
            result = await _execute_property_analysis_tool(parameters)
        elif tool_name == "market_analysis":
            result = await _execute_market_analysis_tool(parameters)
        else:
            logger.warning(f"Tool execution: Unknown tool '{tool_name}'")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": f"Unknown tool: {tool_name}"})
            }
        
        logger.info(f"Tool '{tool_name}' executed successfully")
        return {
            "statusCode": 200,
            "headers": {**_cors_headers(), "Content-Type": "application/json"},
            "body": json.dumps(result)
        }
        
    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        return {
            "statusCode": 500,
            "headers": _cors_headers(),
            "body": json.dumps({"error": "Failed to execute tool", "details": str(e)})
        }

def handler(event, context):
    logger.info("Lambda function invoked")
    logger.info(f"Event: {event}")
    logger.info(f"Context: {context.function_name}")
    
    try:
        logger.info("Processing request body")
        # The event itself is the body when coming from AgentCore Gateway
        body = event if isinstance(event, dict) else {}
        
        logger.info(f"Request body: {body}")

        # Handle tool execution requests
        if body.get("tool_name"):
            logger.info(f"Executing tool: {body.get('tool_name')}")
            return asyncio.run(_handle_tool_execution(body))
        
        # Check if tool_name is in the parameters (new schema structure)
        if isinstance(body, dict) and any(key in body for key in ["query", "address", "location"]):
            # Extract tool_name from the parameters
            tool_name = body.get("tool_name")
            if tool_name:
                logger.info(f"Executing tool from parameters: {tool_name}")
                return asyncio.run(_handle_tool_execution(body))
            else:
                logger.warning("Parameters provided but no tool_name specified")
                return {
                    "statusCode": 400,
                    "headers": _cors_headers(),
                    "body": json.dumps({"error": "tool_name is required when providing tool parameters"})
                }
        
        # If no tool_name, return error
        logger.warning("No tool_name provided")
        return {
            "statusCode": 400,
            "headers": _cors_headers(),
            "body": json.dumps({"error": "Tool name is required for tool lambda"})
        }

    except Exception as e:
        logger.error(f"Error in handler: {e}")
        return {
            "statusCode": 500,
            "headers": _cors_headers(),
            "body": json.dumps({"error": "Failed to process tool request", "details": str(e)})
        } 