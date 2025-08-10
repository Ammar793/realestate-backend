# Tool Lambda Function

This directory contains a separate Lambda function specifically for handling tool execution requests. This separation allows for better scalability and maintenance of the tool-specific functionality.

## Overview

The tool lambda function (`tool_lambda_function.py`) handles direct tool execution requests from the AgentCore Gateway, including:

- **RAG Query Tool**: Knowledge base queries with context
- **Property Analysis Tool**: Property-specific analysis and recommendations
- **Market Analysis Tool**: Market insights and trends

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Frontend      │    │  Main Lambda     │    │  Tool Lambda    │
│                 │    │  (Agents/        │    │  (Tool         │
│                 │    │   Workflows)     │    │   Execution)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌──────────────────┐
                    │  AgentCore       │
                    │  Gateway         │
                    └──────────────────┘
```

## Setup Instructions

### 1. Create the Tool Lambda Function

You can create the tool lambda function using the provided CloudFormation template:

```bash
# Deploy the CloudFormation stack
aws cloudformation create-stack \
  --stack-name selador-tool-lambda \
  --template-body file://tool-lambda-template.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters ParameterKey=Environment,ParameterValue=dev

# Wait for stack creation to complete
aws cloudformation wait stack-create-complete --stack-name selador-tool-lambda
```

### 2. Update Environment Variables

After creating the lambda function, update the environment variables with your actual values:

```bash
aws lambda update-function-configuration \
  --function-name selador-realestate-tools \
  --environment Variables='{KNOWLEDGE_BASE_ID="your-kb-id",MODEL_ARN="your-model-arn"}'
```

### 3. Deploy the Code

The CI/CD pipeline will automatically deploy both lambda functions. The tool lambda will be deployed as `selador-realestate-tools`.

## API Endpoints

### Tool Execution Endpoint

**POST** `/tools`

**Request Body:**
```json
{
  "tool_name": "rag_query",
  "query": "What are the zoning requirements for ADUs?",
  "context": "Property at 123 Main St, Seattle, WA"
}
```

**Available Tools:**

1. **`rag_query`**
   - Parameters: `tool_name`, `query`, `context`
   - Purpose: Knowledge base queries with property context

2. **`property_analysis`**
   - Parameters: `tool_name`, `address`, `analysis_type`
   - Purpose: Property-specific analysis and recommendations

3. **`market_analysis`**
   - Parameters: `tool_name`, `location`, `property_type`, `timeframe`
   - Purpose: Market insights and trends

**Note:** The `tool_name` field is now included in the input schema as an enum with values: `["rag_query", "property_analysis", "market_analysis"]`. This field is required for all tool executions and helps the lambda function route the request to the appropriate tool handler.

## Integration with Main Lambda

The main lambda function now forwards tool execution requests to the tool lambda with an appropriate error message. This ensures a clean separation of concerns:

- **Main Lambda**: Handles agent queries and workflow execution
- **Tool Lambda**: Handles direct tool execution requests

## Monitoring and Logging

Both lambda functions log to CloudWatch. You can monitor:

- **Main Lambda**: `selador-realestate-backend`
- **Tool Lambda**: `selador-realestate-tools`

## Scaling Considerations

- **Main Lambda**: Optimized for agent orchestration and workflow management
- **Tool Lambda**: Optimized for tool execution with Bedrock integration
- **Independent Scaling**: Each lambda can scale independently based on demand

## Troubleshooting

### Common Issues

1. **Tool Lambda Not Found**
   - Ensure the CloudFormation stack was created successfully
   - Check that the function name matches in the deployment workflow

2. **Environment Variables Missing**
   - Verify `KNOWLEDGE_BASE_ID` and `MODEL_ARN` are set
   - Check CloudWatch logs for configuration errors

3. **Permission Denied**
   - Ensure the IAM role has proper Bedrock permissions
   - Check API Gateway integration settings

### Debugging

```bash
# Check lambda function status
aws lambda get-function --function-name selador-realestate-tools

# View recent logs
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/selador-realestate-tools

# Test tool execution
aws lambda invoke \
  --function-name selador-realestate-tools \
  --payload '{"tool_name":"rag_query","parameters":{"query":"test","context":"test"}}' \
  response.json
```

## Future Enhancements

- Add authentication and authorization
- Implement tool-specific rate limiting
- Add more specialized tools (e.g., permit lookup, zoning analysis)
- Implement tool result caching
- Add tool execution metrics and monitoring 