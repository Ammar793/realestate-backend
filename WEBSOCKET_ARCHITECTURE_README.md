# WebSocket Architecture with SQS Integration

This document describes the new WebSocket architecture that separates WebSocket handling from message processing to avoid API Gateway timeout limitations.

## Architecture Overview

```
WebSocket Client → API Gateway → WebSocket Handler Lambda → SQS Queue → Main Lambda → WebSocket Client
```

### Components

1. **WebSocket Handler Lambda** (`websocket-handler-lambda/`)
   - Handles WebSocket connections ($connect, $disconnect, invoke)
   - Receives messages from clients and puts them in SQS queue
   - Short timeout (30 seconds) - just enough to queue messages
   - No heavy processing - just message queuing

2. **Main Lambda** (`main-lambda/`)
   - Processes messages from SQS queue
   - Executes agent queries and workflows
   - Streams responses back to WebSocket clients
   - Long timeout (15 minutes) - can handle complex processing
   - No direct WebSocket handling - only SQS processing

3. **SQS Queue**
   - Acts as a message buffer between the two lambdas
   - Handles message persistence and retry logic
   - Decouples WebSocket handling from message processing

## Benefits

- **No API Gateway Timeout**: WebSocket handler lambda completes quickly, avoiding 29-second timeout
- **Scalability**: Can process multiple messages concurrently via SQS
- **Reliability**: SQS provides message persistence and retry capabilities
- **Separation of Concerns**: Each lambda has a single responsibility

## Deployment

Use the new deployment script to deploy both lambdas:

```bash
cd backend
./deploy-all-lambdas.sh
```

This script will:
1. Package and deploy the main lambda (SQS processor)
2. Package and deploy the WebSocket handler lambda
3. Set appropriate timeouts and memory for each function

## Manual Setup Required

You'll need to manually create in the AWS Console:

1. **API Gateway WebSocket API**
   - Route: `$connect` → WebSocket Handler Lambda
   - Route: `$disconnect` → WebSocket Handler Lambda  
   - Route: `invoke` → WebSocket Handler Lambda

2. **SQS Queue**
   - Standard queue for message processing
   - Configure appropriate retention and visibility timeout

3. **Lambda Functions**
   - `selador-websocket-handler` (WebSocket Handler Lambda)
   - `selador-realestate-backend` (Main Lambda)

4. **IAM Permissions**
   - WebSocket Handler Lambda: Send messages to SQS
   - Main Lambda: Read messages from SQS, send WebSocket messages via API Gateway Management API

## Environment Variables

### WebSocket Handler Lambda
- `SQS_QUEUE_URL`: URL of the SQS queue to send messages to

### Main Lambda
- `KNOWLEDGE_BASE_ID`: Bedrock Knowledge Base ID
- `MODEL_ARN`: Bedrock model ARN
- Standard AWS environment variables (region, etc.)

## Message Flow

1. **Client connects** to WebSocket via API Gateway
2. **Client sends query** via WebSocket
3. **WebSocket Handler Lambda** receives message and puts it in SQS queue
4. **Main Lambda** picks up message from SQS queue
5. **Main Lambda** processes query and streams response back to WebSocket client
6. **Client receives** streaming response

## Testing

Test the WebSocket connection using the existing test client:

```bash
cd my-react-app
npm start
```

Update the WebSocket URL in `src/config/websocket.ts` to point to your deployed API Gateway WebSocket API.

## Troubleshooting

- **Connection Issues**: Check API Gateway WebSocket API configuration
- **Message Not Processing**: Check SQS queue and Main Lambda permissions
- **No Response**: Check Main Lambda logs for processing errors
- **Timeout Errors**: Ensure WebSocket Handler Lambda timeout is set to 30 seconds or less

## Monitoring

Monitor both lambdas in CloudWatch:
- WebSocket Handler Lambda: Connection handling and message queuing
- Main Lambda: Message processing and WebSocket response sending
- SQS Queue: Message throughput and error rates 