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
                    
                    # Create citation entry
                    citation_entry = {
                        "id": citation_counter,
                        "source": source_name,
                        "source_link": source_link,
                        "page": page,
                        "chunk": chunk,
                        "text": r.get("content", "")[:200] + "..." if len(r.get("content", "")) > 200 else r.get("content", "")
                    }
                    
                    citations.append(citation_entry)
                    citation_map[citation_counter] = {
                        "id": citation_counter,
                        "source": source_name,
                        "source_link": source_link,
                        "page": page,
                        "chunk": chunk,
                        "text": r.get("content", "")[:200] + "..." if len(r.get("content", "")) > 200 else r.get("content", "")
                    }
                    citation_counter += 1
            else:
                print("DEBUG: No retrieved references found in citation")  # Debug logging
                # Try to extract from the generatedResponsePart if available
                generated_part = c.get("generatedResponsePart", {})
                if generated_part:
                    print(f"DEBUG: Found generatedResponsePart: {generated_part}")  # Debug logging
                    # Look for any reference information in the generated part
                    text_part = generated_part.get("textResponsePart", {})
                    if text_part:
                        span = text_part.get("span", {})
                        text = text_part.get("text", "")
                        print(f"DEBUG: Found text response part: span={span}, text={text[:100]}...")  # Debug logging
    else:
        print("DEBUG: No citations found in response structure")  # Debug logging
    
    # If no citations were found in the response structure, try to extract them from the text
    if not citations and answer:
        import re
        # Find all citation markers like [1], [2], etc.
        citation_markers = re.findall(r'\[(\d+)\]', answer)
        if citation_markers:
            print(f"DEBUG: Found citation markers in text: {citation_markers}")  # Debug logging
            # Use the actual citation numbers from the text, not renumber them
            for marker in sorted(set(citation_markers), key=int):
                citation_entry = {
                    "id": int(marker),  # Use the actual citation number
                    "source": "Seattle Municipal Code",
                    "source_link": "https://johnlscott.s3.amazonaws.com/Seattle%20Municipal%20Code.pdf",
                    "page": "See SMC for details",
                    "chunk": "Relevant section",
                    "text": f"Citation {marker} from Seattle Municipal Code - Referenced in AI response"
                }
                citations.append(citation_entry)
                citation_map[int(marker)] = {
                    "id": int(marker),
                    "source": "Seattle Municipal Code",
                    "source_link": "https://johnlscott.s3.amazonaws.com/Seattle%20Municipal%20Code.pdf",
                    "page": "See SMC for details",
                    "chunk": "Relevant section",
                    "text": f"Citation {marker} from Seattle Municipal Code - Referenced in AI response"
                }
    
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
                    "chunk": chunk,
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
            "body": json.dumps({"error": "Failed to query Bedrock knowledge base", "details": str(e)})
        }
