#!/bin/bash

# Deploy Tool Lambda Function
# This script helps set up the tool lambda function using CloudFormation

set -e

# Configuration
STACK_NAME="selador-tool-lambda"
FUNCTION_NAME="selador-realestate-tools"
REGION="us-west-2"
TEMPLATE_FILE="tool-lambda-template.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Deploying Tool Lambda Function${NC}"
echo "=================================="

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI is not installed. Please install it first.${NC}"
    exit 1
fi

# Check if template file exists
if [ ! -f "$TEMPLATE_FILE" ]; then
    echo -e "${RED}❌ Template file $TEMPLATE_FILE not found${NC}"
    exit 1
fi

# Check if stack already exists
if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" &> /dev/null; then
    echo -e "${YELLOW}⚠️  Stack $STACK_NAME already exists. Updating...${NC}"
    
    # Update existing stack
    aws cloudformation update-stack \
        --stack-name "$STACK_NAME" \
        --template-body "file://$TEMPLATE_FILE" \
        --capabilities CAPABILITY_NAMED_IAM \
        --region "$REGION" \
        --parameters ParameterKey=Environment,ParameterValue=dev
    
    echo -e "${YELLOW}⏳ Waiting for stack update to complete...${NC}"
    aws cloudformation wait stack-update-complete --stack-name "$STACK_NAME" --region "$REGION"
    
else
    echo -e "${GREEN}📦 Creating new stack $STACK_NAME...${NC}"
    
    # Create new stack
    aws cloudformation create-stack \
        --stack-name "$STACK_NAME" \
        --template-body "file://$TEMPLATE_FILE" \
        --capabilities CAPABILITY_NAMED_IAM \
        --region "$REGION" \
        --parameters ParameterKey=Environment,ParameterValue=dev
    
    echo -e "${YELLOW}⏳ Waiting for stack creation to complete...${NC}"
    aws cloudformation wait stack-create-complete --stack-name "$STACK_NAME" --region "$REGION"
fi

echo -e "${GREEN}✅ Stack deployment completed successfully!${NC}"

# Get stack outputs
echo -e "${GREEN}📋 Stack Outputs:${NC}"
aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs' \
    --output table

# Check if lambda function exists
if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" &> /dev/null; then
    echo -e "${GREEN}✅ Lambda function $FUNCTION_NAME exists${NC}"
    
    # Show function configuration
    echo -e "${GREEN}📋 Function Configuration:${NC}"
    aws lambda get-function-configuration \
        --function-name "$FUNCTION_NAME" \
        --region "$REGION" \
        --query '{FunctionName:FunctionName,Runtime:Runtime,Handler:Handler,Timeout:Timeout,MemorySize:MemorySize,Environment:Environment}' \
        --output table
    
else
    echo -e "${RED}❌ Lambda function $FUNCTION_NAME not found${NC}"
    echo "Please check the CloudFormation stack outputs and ensure the function was created correctly."
fi

echo ""
echo -e "${GREEN}🎉 Tool Lambda deployment completed!${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Update environment variables with your actual values:"
echo "   aws lambda update-function-configuration \\"
echo "     --function-name $FUNCTION_NAME \\"
echo "     --region $REGION \\"
echo "     --environment Variables='{KNOWLEDGE_BASE_ID=\"your-kb-id\",MODEL_ARN=\"your-model-arn\"}'"
echo ""
echo "2. Deploy the actual code using the CI/CD pipeline"
echo "3. Test the function with a sample request"
echo ""
echo -e "${GREEN}Happy coding! 🚀${NC}" 