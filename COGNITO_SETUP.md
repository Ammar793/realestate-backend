# Cognito Authentication Setup for AgentCore Gateway

This document explains how to set up Amazon Cognito authentication for your AgentCore Gateway to secure access to your MCP tools.

## Overview

The implementation provides:
- **OAuth2 Client Credentials Flow**: Secure authentication using Cognito app client credentials
- **Automatic Token Management**: Handles token refresh and expiration automatically
- **Seamless Integration**: Works with existing Strands agents and MCP clients
- **Fallback Support**: Maintains backward compatibility with existing access tokens

## Prerequisites

1. **AWS Account** with access to Cognito and Bedrock services
2. **Cognito User Pool** configured for your application
3. **Cognito App Client** with client credentials enabled
4. **AgentCore Gateway** already created and configured

## Step 1: Configure Cognito User Pool

### 1.1 Create User Pool (if not exists)
```bash
# Using AWS CLI
aws cognito-idp create-user-pool \
  --pool-name "JLSRealEstatePool" \
  --policies "PasswordPolicy={MinimumLength=8,RequireUppercase=true,RequireLowercase=true,RequireNumbers=true,RequireSymbols=false}" \
  --auto-verified-attributes "email" \
  --username-attributes "email"
```

### 1.2 Create App Client
```bash
# Create app client with client credentials
aws cognito-idp create-user-pool-client \
  --user-pool-id "your-user-pool-id" \
  --client-name "JLSRealEstateClient" \
  --generate-secret \
  --explicit-auth-flows "ALLOW_USER_PASSWORD_AUTH" "ALLOW_REFRESH_TOKEN_AUTH" \
  --supported-identity-providers "COGNITO"
```

### 1.3 Get App Client Details
```bash
# Get client ID and secret
aws cognito-idp describe-user-pool-client \
  --user-pool-id "your-user-pool-id" \
  --client-id "your-client-id"
```

## Step 2: Configure Environment Variables

### 2.1 Local Development (.env file)
```bash
# Copy the example file
cp config.env.example .env

# Edit with your values
COGNITO_CLIENT_ID=your-cognito-client-id
COGNITO_CLIENT_SECRET=your-cognito-client-secret
COGNITO_TOKEN_URL=https://your-domain.auth.us-west-2.amazoncognito.com/oauth2/token
COGNITO_USER_POOL_ID=your-user-pool-id
COGNITO_IDENTITY_POOL_ID=your-identity-pool-id
```

### 2.2 GitHub Actions (Repository Variables)
Set these as **Repository Variables** in your GitHub repository:

**Variables (public):**
- `COGNITO_CLIENT_ID`
- `COGNITO_TOKEN_URL`
- `COGNITO_USER_POOL_ID`
- `COGNITO_IDENTITY_POOL_ID`

**Secrets (private):**
- `COGNITO_CLIENT_SECRET`

### 2.3 AWS Lambda Environment Variables
The GitHub Actions workflow automatically sets these in your Lambda functions.

## Step 3: Update AgentCore Gateway

### 3.1 Run the Setup Script
```bash
cd backend
python shared/setup_agentcore_gateway.py
```

This will:
- Update your gateway with Cognito authentication
- Save the new configuration to `agentcore_config.json`
- Test the authentication flow

### 3.2 Verify Configuration
Check that `agentcore_config.json` contains:
```json
{
  "gateway_id": "your-gateway-id",
  "gateway_url": "https://your-gateway-url.amazonaws.com",
  "target_id": "your-target-id",
  "cognito_client_info": {
    "client_id": "your-client-id",
    "client_secret": "your-client-secret",
    "token_url": "https://your-domain.auth.us-west-2.amazoncognito.com/oauth2/token",
    "user_pool_id": "your-user-pool-id",
    "identity_pool_id": "your-identity-pool-id"
  }
}
```

## Step 4: Test the Integration

### 4.1 Run the Test Script
```bash
cd backend
python test_cognito_auth.py
```

This will test:
- Cognito authentication
- Token management
- MCP connection with authentication
- Tool listing

### 4.2 Expected Output
```
🚀 Starting Cognito + AgentCore integration tests...

==================================================
TEST 1: Standalone Cognito Authentication
==================================================
Testing standalone Cognito authentication...
✅ Successfully obtained token: eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
✅ Auth headers: {'Authorization': 'Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...', 'Content-Type': 'application/json'}
✅ Token is valid: True

==================================================
TEST 2: Full AgentCore + Cognito Integration
==================================================
Creating Cognito authenticator...
Testing Cognito authentication...
✅ Successfully obtained access token: eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
Testing MCP connection with Cognito authentication...
Initializing MCP...
✅ MCP Server Initialize successful! - {...}
Listing tools...
✅ List MCP tools. # of tools - 3
List of tools - 
rag_query
property_analysis
market_analysis

🎉 Complete integration test successful!
Found 3 tools in the gateway

==================================================
TEST SUMMARY
==================================================
🎉 ALL TESTS PASSED!
✅ Cognito authentication is working
✅ AgentCore gateway integration is working
✅ Your setup is ready for production use
```

## Step 5: Deploy to Production

### 5.1 Push to Main Branch
The GitHub Actions workflow will automatically:
- Build Lambda packages with new dependencies
- Update environment variables
- Deploy to AWS Lambda

### 5.2 Verify Deployment
Check your Lambda function logs to ensure:
- Cognito authentication is working
- MCP tools are accessible
- No authentication errors

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Your Client   │───▶│  Cognito Auth    │───▶│ AgentCore      │
│                 │    │  (OAuth2)        │    │ Gateway        │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │  Access Token    │
                       │  (JWT)          │
                       └──────────────────┘
```

## Security Features

- **Automatic Token Refresh**: Tokens are refreshed before expiration
- **Secure Storage**: Client secrets are stored as GitHub secrets
- **Token Validation**: Automatic validation of token authenticity
- **Fallback Support**: Graceful degradation if authentication fails

## Troubleshooting

### Common Issues

#### 1. Authentication Failed
```
Error: Token request failed: 400
```
**Solution**: Check your Cognito app client configuration and ensure client credentials are enabled.

#### 2. Invalid Client ID
```
Error: invalid_client
```
**Solution**: Verify `COGNITO_CLIENT_ID` matches your Cognito app client.

#### 3. Gateway Connection Failed
```
Error: MCP connection failed
```
**Solution**: Check your gateway URL and ensure the gateway is accessible.

#### 4. Missing Dependencies
```
ImportError: No module named 'requests'
```
**Solution**: Ensure `requests>=2.31.0` is in your requirements.txt.

### Debug Mode
Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Cognito Configuration
```bash
# Verify user pool
aws cognito-idp describe-user-pool --user-pool-id your-user-pool-id

# Verify app client
aws cognito-idp describe-user-pool-client \
  --user-pool-id your-user-pool-id \
  --client-id your-client-id
```

## Monitoring

### CloudWatch Logs
Monitor your Lambda functions for:
- Authentication success/failure
- Token refresh events
- MCP connection status

### Metrics to Watch
- Authentication success rate
- Token refresh frequency
- Gateway response times

## Best Practices

1. **Rotate Secrets**: Regularly rotate Cognito client secrets
2. **Monitor Usage**: Track authentication patterns and failures
3. **Error Handling**: Implement graceful fallbacks for auth failures
4. **Logging**: Log authentication events for security monitoring
5. **Testing**: Regularly test the authentication flow

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Verify your Cognito configuration
3. Review CloudWatch logs for detailed error messages
4. Ensure all environment variables are correctly set

## Next Steps

After successful setup:
1. **Test with Real Data**: Verify tools work with your actual data
2. **Monitor Performance**: Track response times and success rates
3. **Scale Up**: Add more tools and agents as needed
4. **Security Review**: Conduct security assessment of your setup 