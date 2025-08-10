import json
import os
import boto3
import asyncio

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

async def _execute_rag_tool(parameters: dict) -> dict:
    """Execute RAG tool for knowledge base queries"""
    query = parameters.get("query", "")
    context = parameters.get("context", "")
    
    if not query:
        return {"error": "Query parameter is required"}
    
    # Use existing Bedrock knowledge base logic
    req = {
        "input": {"text": query},
        "retrieveAndGenerateConfiguration": {
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": KB_ID,
                "modelArn": MODEL_ARN,
                "retrievalConfiguration": {
                    "vectorSearchConfiguration": {"numberOfResults": 6}
                },
                "generationConfiguration": {
                    "promptTemplate": {
                        "textPromptTemplate": (
                            "User question:\n$query$\n\n"
                            "Property context:\n<context>\n"
                            f"{context}\n"
                            "</context>\n\n"
                            "Relevant excerpts from the knowledge base:\n$search_results$\n\n"
                            "Answer the question based on the knowledge base and context:"
                        )
                    }
                }
            }
        }
    }
    
    resp = _bedrock.retrieve_and_generate(**req)
    raw_answer = (resp.get("output") or {}).get("text") or ""
    answer_with_cites, ordered_refs = _inject_inline_citations(resp, raw_answer)
    
    return {
        "answer": answer_with_cites,
        "citations": ordered_refs,
        "confidence": min(0.95, 0.7 + 0.05 * len(ordered_refs)) if ordered_refs else 0.8
    }

async def _execute_property_analysis_tool(parameters: dict) -> dict:
    """Execute property analysis tool"""
    address = parameters.get("address", "")
    analysis_type = parameters.get("analysis_type", "comprehensive")
    
    if not address:
        return {"error": "Address parameter is required"}
    
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
    location = parameters.get("location", "")
    property_type = parameters.get("property_type", "residential")
    timeframe = parameters.get("timeframe", "1year")
    
    if not location:
        return {"error": "Location parameter is required"}
    
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
    try:
        tool_name = body.get("tool_name")
        parameters = body.get("parameters", {})
        
        if not tool_name:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Tool name is required"})
            }
        
        # Execute the tool based on name
        if tool_name == "rag_query":
            result = await _execute_rag_tool(parameters)
        elif tool_name == "property_analysis":
            result = await _execute_property_analysis_tool(parameters)
        elif tool_name == "market_analysis":
            result = await _execute_market_analysis_tool(parameters)
        else:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": f"Unknown tool: {tool_name}"})
            }
        
        return {
            "statusCode": 200,
            "headers": {**_cors_headers(), "Content-Type": "application/json"},
            "body": json.dumps(result)
        }
        
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": _cors_headers(),
            "body": json.dumps({"error": "Failed to execute tool", "details": str(e)})
        }

def handler(event, context):
    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": _cors_headers(), "body": ""}

    try:
        body = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            import base64
            body = json.loads(base64.b64decode(body))
        else:
            body = json.loads(body)

        # Handle tool execution requests
        if body.get("tool_name"):
            return asyncio.run(_handle_tool_execution(body))
        
        # If no tool_name, return error
        return {
            "statusCode": 400,
            "headers": _cors_headers(),
            "body": json.dumps({"error": "Tool name is required for tool lambda"})
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": _cors_headers(),
            "body": json.dumps({"error": "Failed to process tool request", "details": str(e)})
        } 