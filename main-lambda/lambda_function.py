import json
import os
import boto3
import asyncio
from shared.strands_orchestrator import StrandsAgentOrchestrator

# Reuse client across invocations
_bedrock = boto3.client("bedrock-agent-runtime", region_name=os.environ.get("AWS_REGION", "us-west-2"))

KB_ID = os.environ["KNOWLEDGE_BASE_ID"]
MODEL_ARN = os.environ["MODEL_ARN"]  # e.g., arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0

# Initialize agent orchestrator
_orchestrator = None

def _get_orchestrator():
    """Get or create the Strands agent orchestrator instance"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = StrandsAgentOrchestrator()
    return _orchestrator

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

    # Apply inserts from end to start so indices don’t shift
    inserts.sort(key=lambda x: x[0], reverse=True)
    out = answer
    for pos, marker in inserts:
        if 0 <= pos <= len(out):
            out = out[:pos] + marker + out[pos:]

    return out, ordered_refs


async def _handle_agent_query(body: dict) -> dict:
    """Handle queries using the multi-agent system"""
    try:
        query = body.get("question", "")
        context_text = body.get("context", "")
        query_type = body.get("query_type", "general")
        
        if not query:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Question is required for agent queries"})
            }
        
        # Route query through Strands agent orchestrator
        orchestrator = _get_orchestrator()
        result = await orchestrator.route_query(query, context_text, query_type)
        
        return {
            "statusCode": 200,
            "headers": {**_cors_headers(), "Content-Type": "application/json"},
            "body": json.dumps(result)
        }
        
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": _cors_headers(),
            "body": json.dumps({"error": "Failed to process agent query", "details": str(e)})
        }

async def _handle_tool_execution(body: dict) -> dict:
    """Handle direct tool execution requests by forwarding to tool lambda"""
    try:
        # Forward tool execution requests to the dedicated tool lambda
        # This lambda now only handles agent queries and workflows
        return {
            "statusCode": 400,
            "headers": _cors_headers(),
            "body": json.dumps({"error": "Tool execution has been moved to a separate lambda. Please use the tool lambda endpoint."})
        }
        
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": _cors_headers(),
            "body": json.dumps({"error": "Failed to process tool request", "details": str(e)})
        }



async def _handle_workflow_execution(body: dict) -> dict:
    """Handle workflow execution requests"""
    try:
        workflow_name = body.get("workflow")
        parameters = body.get("parameters", {})
        
        if not workflow_name:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Workflow name is required"})
            }
        
        # Execute workflow through Strands agent orchestrator
        orchestrator = _get_orchestrator()
        result = await orchestrator.execute_workflow(workflow_name, parameters)
        
        return {
            "statusCode": 200,
            "headers": {**_cors_headers(), "Content-Type": "application/json"},
            "body": json.dumps(result)
        }
        
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": _cors_headers(),
            "body": json.dumps({"error": "Failed to execute workflow", "details": str(e)})
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

        # Check if this is an agent query or workflow execution
        if body.get("use_agents") or body.get("workflow"):
            # Use the Strands multi-agent system with AgentCore Gateway
            if body.get("workflow"):
                return asyncio.run(_handle_workflow_execution(body))
            else:
                return asyncio.run(_handle_agent_query(body))
        
        # Check if this is a direct tool execution request
        if body.get("tool_name"):
            return asyncio.run(_handle_tool_execution(body))
        
        # Fall back to original Bedrock knowledge base approach
        question = body.get("question")
        context_text = body.get("context")
        if not question or not context_text:
            return {
                "statusCode": 400,
                "headers": _cors_headers(),
                "body": json.dumps({"error": "Question and context are required"})
            }

        # Build RetrieveAndGenerate request
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
        resp = _bedrock.retrieve_and_generate(**req)

        raw_answer = (resp.get("output") or {}).get("text") or ""
        answer_with_cites, ordered_refs = _inject_inline_citations(resp, raw_answer)

        result = {
            "answer": answer_with_cites or f'I found relevant info for: "{question}", but no direct model output was returned.',
            "citations": ordered_refs,  # Now has proper structure with source_link
            "citation_map": { str(r["id"]): r for r in ordered_refs },
            "confidence": min(0.95, 0.7 + 0.05 * len(ordered_refs)) if ordered_refs else 0.8
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
            "body": json.dumps({"error": "Failed to process request", "details": str(e)})
        }
