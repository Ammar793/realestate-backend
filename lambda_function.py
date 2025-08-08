import json
import os
import boto3

# Reuse client across invocations
_bedrock = boto3.client("bedrock-agent-runtime", region_name=os.environ.get("AWS_REGION", "us-west-2"))

KB_ID = os.environ["KNOWLEDGE_BASE_ID"]
MODEL_ARN = os.environ["MODEL_ARN"]  # e.g., arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0

def _process_response(resp, original_question):
    # See response shape: output.text, citations[].retrievedReferences[].metadata, etc.
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agent-runtime/client/retrieve_and_generate.html
    answer = (resp.get("output") or {}).get("text") or ""
    citations = []
    citation_map = {}
    
    print(f"DEBUG: Full Bedrock response: {json.dumps(resp, indent=2)}")  # Debug logging
    print(f"DEBUG: Answer text: {answer[:500]}...")  # Debug logging
    
    # First, try to extract citations from the response structure
    if "citations" in resp and resp["citations"]:
        print(f"DEBUG: Found citations in response: {len(resp['citations'])}")  # Debug logging
        citation_counter = 1
        for c in resp["citations"]:
            retrieved_refs = c.get("retrievedReferences", [])
            if retrieved_refs:
                print(f"DEBUG: Found {len(retrieved_refs)} retrieved references")  # Debug logging
                for r in retrieved_refs:
                    meta = r.get("metadata", {})
                    page = meta.get("x-amz-bedrock-kb-document-page-number", "Unknown")
                    chunk = meta.get("x-amz-bedrock-kb-document-chunk", "Unknown")
                    uri = (r.get("location", {}).get("webLocation", {}) or {}).get("url") \
                           or (r.get("location", {}).get("s3Location", {}) or {}).get("uri") \
                           or "Knowledge Base Source"
                    
                    # Create citation entry
                    citation_entry = {
                        "id": citation_counter,
                        "source": uri,
                        "page": page,
                        "chunk": chunk,
                        "text": r.get("content", "")[:200] + "..." if len(r.get("content", "")) > 200 else r.get("content", "")
                    }
                    
                    citations.append(citation_entry)
                    citation_map[citation_counter] = citation_entry
                    citation_counter += 1
    else:
        print("DEBUG: No citations found in response structure")  # Debug logging
    
    # If no citations were found in the response structure, try to extract them from the text
    if not citations and answer:
        import re
        # Find all citation markers like [1], [2], etc.
        citation_markers = re.findall(r'\[(\d+)\]', answer)
        if citation_markers:
            print(f"DEBUG: Found citation markers in text: {citation_markers}")  # Debug logging
            citation_counter = 1
            for marker in sorted(set(citation_markers), key=int):
                citation_entry = {
                    "id": citation_counter,
                    "source": "Seattle Municipal Code",
                    "page": "Unknown",
                    "chunk": "Unknown",
                    "text": f"Citation {marker} from Seattle Municipal Code"
                }
                citations.append(citation_entry)
                citation_map[citation_counter] = citation_entry
                citation_counter += 1
    
    confidence = 0.8
    if citations:
        confidence = min(0.95, 0.7 + 0.05 * len(citations))

    if not answer:
        answer = f'I found relevant info for: "{original_question}", but no direct model output was returned.'

    result = {
        "answer": answer,
        "citations": citations,
        "citation_map": citation_map,
        "confidence": confidence
    }
    
    print(f"DEBUG: Processed result: {json.dumps(result, indent=2)}")  # Debug logging
    return result

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "OPTIONS,POST"
    }

def handler(event, context):
    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": _cors_headers(), "body": ""}

    try:
        body = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            body = json.loads(base64.b64decode(body))
        else:
            body = json.loads(body)

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
            "input": {"text": f"{question}\n\nContext: {context_text}"},
            "retrieveAndGenerateConfiguration": {
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": KB_ID,
                    "modelArn": MODEL_ARN,
                    "retrievalConfiguration": {
                        "vectorSearchConfiguration": { "numberOfResults": 5 }
                    },
                    "generationConfiguration": {
                        "promptTemplate": {
                            "textPromptTemplate": (
                                "You are a helpful assistant that answers questions about Seattle properties using "
                                "the Seattle Municipal Code.\n\n"
                                "User question:\n$query$\n\n"
                                "Relevant excerpts:\n$search_results$\n\n"
                                "Instructions:\n"
                                "- Cite specific SMC sections when possible using numbered citations [1], [2], etc.\n"
                                "- Include citations inline in your response where you reference specific information.\n"
                                "- If info is missing, say so.\n"
                                "- Format your response with proper citations like this: 'According to SMC 23.34.080 [1], the property is zoned...'\n"
                                "Final answer:"
                            )
                        }
                    }
                }
            }
        }

        resp = _bedrock.retrieve_and_generate(**req)
        result = _process_response(resp, question)

        return {
            "statusCode": 200,
            "headers": {**_cors_headers(), "Content-Type": "application/json"},
            "body": json.dumps(result)
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": _cors_headers(),
            "body": json.dumps({"error": "Failed to query Bedrock knowledge base", "details": str(e)})
        }
