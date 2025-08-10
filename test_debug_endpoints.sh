#!/bin/bash

# Test script for debug endpoints
# Make sure to replace the URL with your actual Lambda function URL

LAMBDA_URL="YOUR_LAMBDA_FUNCTION_URL_HERE"

echo "=== TESTING DEBUG ENDPOINTS ==="

# Test 1: Get orchestrator status
echo -e "\n1. Testing orchestrator status..."
curl -X POST "$LAMBDA_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "debug_type": "status"
  }' | jq '.'

# Test 2: List available tools
echo -e "\n2. Testing list tools..."
curl -X POST "$LAMBDA_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "debug_type": "list_tools"
  }' | jq '.'

# Test 3: Test a specific tool (replace 'rag_query' with an actual tool name)
echo -e "\n3. Testing tool execution..."
curl -X POST "$LAMBDA_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "debug_type": "test_tool",
    "tool_name": "rag_query",
    "parameters": {}
  }' | jq '.'

# Test 4: Test agent query
echo -e "\n4. Testing agent query..."
curl -X POST "$LAMBDA_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "use_agents": true,
    "question": "What are the zoning requirements?",
    "context": "Testing agent execution",
    "query_type": "rag_query"
  }' | jq '.'

echo -e "\n=== DEBUG TESTS COMPLETED ===" 