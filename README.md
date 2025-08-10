# Backend Services

This directory contains the backend services for the Selador Real Estate platform, organized into logical components for better maintainability and scalability.

## Directory Structure

```
backend/
├── main-lambda/           # Main lambda function (agents & workflows)
│   └── lambda_function.py
├── tool-lambda/           # Tool execution lambda function
│   ├── tool_lambda_function.py
│   ├── tool-lambda-template.yml
│   ├── TOOL_LAMBDA_README.md
│   └── deploy-tool-lambda.sh
├── shared/                # Shared components and utilities
│   ├── agents/           # Agent implementations
│   ├── strands_orchestrator.py
│   ├── agentcore_gateway.py
│   ├── setup_agentcore_gateway.py
│   └── start_gateway.py
├── requirements.txt       # Python dependencies
├── config.env.example     # Environment configuration template
└── README.md             # This file
```

## Components Overview

### Main Lambda (`main-lambda/`)
- **Purpose**: Handles agent queries and workflow execution
- **Function Name**: `selador-realestate-backend`
- **Responsibilities**:
  - Multi-agent orchestration
  - Workflow management
  - Agent routing and coordination

### Tool Lambda (`tool-lambda/`)
- **Purpose**: Handles direct tool execution requests
- **Function Name**: `selador-realestate-tools`
- **Responsibilities**:
  - RAG queries with knowledge base
  - Property analysis tools
  - Market analysis tools
  - Tool-specific Bedrock integration

### Shared Components (`shared/`)
- **Agents**: Individual agent implementations
- **Orchestrator**: Multi-agent coordination logic
- **Gateway**: AgentCore integration and setup
- **Utilities**: Common functionality shared across lambdas

## Quick Start

### 1. Environment Setup
```bash
# Copy and configure environment variables
cp config.env.example config.env
# Edit config.env with your actual values
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Deploy Tool Lambda (First Time)
```bash
cd tool-lambda
./deploy-tool-lambda.sh
```

### 4. Deploy Both Lambdas (CI/CD)
```bash
# Push to main branch to trigger automatic deployment
git push origin main
```

## Development

### Local Development
```bash
# Start the AgentCore gateway locally
cd shared
python start_gateway.py

# Test main lambda functionality
cd main-lambda
python -c "import lambda_function; print('Main lambda ready')"

# Test tool lambda functionality
cd tool-lambda
python -c "import tool_lambda_function; print('Tool lambda ready')"
```

### Testing
- **Main Lambda**: Test agent queries and workflow execution
- **Tool Lambda**: Test individual tool execution
- **Integration**: Test end-to-end workflows through the main lambda

## Deployment

The CI/CD pipeline automatically deploys both lambda functions when code is pushed to the main branch. The deployment workflow:

1. Builds separate deployment packages for each lambda
2. Updates both lambda functions with new code
3. Maintains proper separation of concerns

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
                    │  Shared          │
                    │  Components      │
                    └──────────────────┘
```

## Configuration

### Environment Variables
- `KNOWLEDGE_BASE_ID`: Bedrock knowledge base identifier
- `MODEL_ARN`: Bedrock model ARN for text generation
- `AWS_REGION`: AWS region for services

### AWS Services
- **Lambda**: Function execution
- **Bedrock**: AI/ML model inference
- **API Gateway**: HTTP endpoints
- **CloudWatch**: Logging and monitoring

## Monitoring

Both lambda functions log to CloudWatch:
- **Main Lambda**: `/aws/lambda/selador-realestate-backend`
- **Tool Lambda**: `/aws/lambda/selador-realestate-tools`

## Troubleshooting

### Common Issues
1. **Import Errors**: Ensure shared components are properly referenced
2. **Environment Variables**: Verify all required variables are set
3. **Permissions**: Check IAM roles and policies
4. **Dependencies**: Ensure requirements.txt is up to date

### Debugging
- Check CloudWatch logs for detailed error information
- Use local testing for rapid iteration
- Verify file paths after reorganization

## Contributing

When adding new functionality:
1. **Agents**: Add to `shared/agents/`
2. **Tools**: Add to `tool-lambda/`
3. **Workflows**: Add to `main-lambda/`
4. **Shared Logic**: Add to `shared/`

Maintain the separation of concerns and update this README as the structure evolves. 