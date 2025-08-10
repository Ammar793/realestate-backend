#!/bin/bash

# Deploy both Lambda functions for Selador Real Estate Backend
# This script packages and deploys both the main-lambda and websocket-handler-lambda functions

set -e

echo "🚀 Deploying all Lambda functions..."

# Configuration
MAIN_FUNCTION_NAME="selador-realestate-backend"
WEBSOCKET_FUNCTION_NAME="selador-websocket-handler"
REGION="us-west-2"
MAIN_LAMBDA_DIR="main-lambda"
WEBSOCKET_LAMBDA_DIR="websocket-handler-lambda"
MAIN_PACKAGE_NAME="main-lambda-package.zip"
WEBSOCKET_PACKAGE_NAME="websocket-lambda-package.zip"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[HEADER]${NC} $1"
}

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check if we're in the right directory
if [ ! -d "$MAIN_LAMBDA_DIR" ] || [ ! -d "$WEBSOCKET_LAMBDA_DIR" ]; then
    print_error "Lambda directories not found. Please run this script from the backend directory."
    exit 1
fi

# Check if shared directory exists
if [ ! -d "shared" ]; then
    print_error "Shared directory not found. Please run this script from the backend directory."
    exit 1
fi

print_header "Starting deployment process for all Lambda functions..."

# Function to deploy a lambda
deploy_lambda() {
    local function_name=$1
    local lambda_dir=$2
    local package_name=$3
    local description=$4
    
    print_status "Deploying $description..."
    
    # Clean up previous package
    if [ -f "$package_name" ]; then
        print_status "Removing previous package for $description..."
        rm -f "$package_name"
    fi
    
    # Create temporary directory for packaging
    local temp_dir=$(mktemp -d)
    print_status "Created temporary directory for $description: $temp_dir"
    
    # Copy Lambda function files
    print_status "Copying $description files..."
    cp -r "$lambda_dir"/* "$temp_dir/"
    cp -r shared "$temp_dir/"
    
    # Install dependencies
    print_status "Installing Python dependencies for $description..."
    cd "$temp_dir"
    pip install -r requirements.txt -t . --quiet
    
    # Remove unnecessary files to reduce package size
    print_status "Cleaning up package for $description..."
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
    
    # Create deployment package
    print_status "Creating deployment package for $description..."
    zip -r "$package_name" . -q
    
    # Move package back to original directory
    cd - > /dev/null
    mv "$temp_dir/$package_name" .
    
    # Clean up temporary directory
    rm -rf "$temp_dir"
    
    print_status "Package created for $description: $package_name"
    
    # Check package size
    local package_size=$(du -h "$package_name" | cut -f1)
    print_status "Package size for $description: $package_size"
    
    # Deploy to AWS Lambda
    print_status "Deploying $description to AWS Lambda..."
    
    # Check if function exists
    if aws lambda get-function --function-name "$function_name" --region "$REGION" &>/dev/null; then
        print_status "Updating existing Lambda function: $function_name..."
        aws lambda update-function-code \
            --function-name "$function_name" \
            --zip-file "fileb://$package_name" \
            --region "$REGION"
        
        print_status "Updating function configuration for $function_name..."
        
        # Set different configurations based on function type
        if [ "$function_name" = "$MAIN_FUNCTION_NAME" ]; then
            # Main lambda - longer timeout for processing
            aws lambda update-function-configuration \
                --function-name "$function_name" \
                --timeout 900 \
                --memory-size 1024 \
                --region "$REGION"
        else
            # WebSocket handler - shorter timeout since it just queues messages
            aws lambda update-function-configuration \
                --function-name "$function_name" \
                --timeout 30 \
                --memory-size 256 \
                --region "$REGION"
        fi
        
        print_status "Lambda function $function_name updated successfully!"
    else
        print_warning "Lambda function '$function_name' not found."
        print_status "You'll need to create it first or update the function name in this script."
        print_status "Package is ready for manual deployment."
    fi
    
    # Clean up package
    print_status "Cleaning up deployment package for $description..."
    rm -f "$package_name"
}

# Deploy main lambda
deploy_lambda "$MAIN_FUNCTION_NAME" "$MAIN_LAMBDA_DIR" "$MAIN_PACKAGE_NAME" "Main Lambda (SQS processor)"

# Deploy websocket handler lambda
deploy_lambda "$WEBSOCKET_FUNCTION_NAME" "$WEBSOCKET_LAMBDA_DIR" "$WEBSOCKET_PACKAGE_NAME" "WebSocket Handler Lambda"

print_header "✅ All Lambda deployments completed!"
print_status ""
print_status "Next steps:"
print_status "1. Ensure your API Gateway WebSocket API is configured with the WebSocket Handler Lambda integration"
print_status "2. Ensure your SQS queue is configured and the WebSocket Handler Lambda has permission to send messages to it"
print_status "3. Ensure your Main Lambda is configured as an SQS trigger and has permission to read from the queue"
print_status "4. Test the WebSocket connection using the test client"
print_status "5. Check CloudWatch logs for any errors"
print_status ""
print_status "For testing, run: python test_websocket_client.py"
print_status "Remember to update the WebSocket URL in the test client first!"
print_status ""
print_status "Architecture:"
print_status "WebSocket Client → API Gateway → WebSocket Handler Lambda → SQS Queue → Main Lambda → WebSocket Client" 