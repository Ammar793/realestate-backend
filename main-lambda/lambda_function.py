import json
import os
import boto3
import asyncio
import base64
import logging
from strands_orchestrator import StrandsAgentOrchestrator

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

# Now import the rest of your code

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
        _orchestrator = StrandsAgentOrchestrator()
        print("=== ORCHESTRATOR INSTANCE CREATED SUCCESSFULLY ===")
    else:
        print("=== REUSING EXISTING ORCHESTRATOR INSTANCE ===")
        logger.debug("Reusing existing Strands agent orchestrator instance")
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
    """Handle queries using the multi-agent system"""
    print("=== ENTERING AGENT QUERY HANDLER ===")
    logger.info("Handling agent query request")
    logger.debug(f"Agent query body: {json.dumps(body, default=str)}")
    
    try:
        query = body.get("question", "")
        context_text = body.get("context", "")
        query_type = body.get("query_type", "general")
        
        print(f"=== AGENT QUERY PARAMS: type={query_type}, query_length={len(query)}, context_length={len(context_text)} ===")
        logger.info(f"Processing agent query: type={query_type}, query_length={len(query)}, context_length={len(context_text)}")
        
        if not query:
            print("=== ERROR: Missing question field ===")
            logger.warning("Agent query missing required 'question' field")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Question is required for agent queries"})
            }
        
        # Route query through Strands agent orchestrator
        print("=== ROUTING THROUGH STRANDS ORCHESTRATOR ===")
        logger.info("Routing query through Strands agent orchestrator")
        orchestrator = _get_orchestrator()
        print("=== ORCHESTRATOR OBTAINED, CALLING route_query ===")
        result = await orchestrator.route_query(query, context_text, query_type)
        
        print(f"=== AGENT QUERY COMPLETED, RESULT LENGTH: {len(str(result))} ===")
        logger.info(f"Agent query completed successfully, result length: {len(str(result))}")
        logger.debug(f"Agent query result: {json.dumps(result, default=str)}")
        
        return {
            "statusCode": 200,
            "headers": {**_cors_headers(), "Content-Type": "application/json"},
            "body": json.dumps(result)
        }
        
    except Exception as e:
        print(f"=== AGENT QUERY FAILED: {str(e)} ===")
        logger.error(f"Failed to process agent query: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": _cors_headers(),
            "body": json.dumps({"error": "Failed to process agent query", "details": str(e)})
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
        result = await orchestrator.execute_workflow(workflow_name, parameters)
        
        logger.info(f"Workflow execution completed successfully, result length: {len(str(result))}")
        logger.debug(f"Workflow execution result: {json.dumps(result, default=str)}")
        
        return {
            "statusCode": 200,
            "headers": {**_cors_headers(), "Content-Type": "application/json"},
            "body": json.dumps(result)
        }
        
    except Exception as e:
        logger.error(f"Failed to execute workflow: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": _cors_headers(),
            "body": json.dumps({"error": "Failed to execute workflow", "details": str(e)})
        }

def handler(event, context):
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
                return asyncio.run(_handle_workflow_execution(body))
            else:
                logger.info("Processing agent query")
                return asyncio.run(_handle_agent_query(body))
        
        # Fall back to original Bedrock knowledge base approach
        logger.info("Using Bedrock knowledge base approach")
        print(f"=== USING BEDROCK KNOWLEDGE BASE PATH ===")
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
