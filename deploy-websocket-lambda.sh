#!/bin/bash

# DEPRECATED: This script is no longer used
# Use deploy-all-lambdas.sh instead for the new architecture
#
# The new architecture separates WebSocket handling from message processing:
# - WebSocket Handler Lambda: handles connections and queues messages (30s timeout)
# - Main Lambda: processes messages from SQS and streams responses (15min timeout)
#
# To deploy both lambdas, run: ./deploy-all-lambdas.sh

echo "⚠️  DEPRECATED: This script is no longer used!"
echo ""
echo "The new architecture requires two separate lambdas:"
echo "1. WebSocket Handler Lambda (websocket-handler-lambda/)"
echo "2. Main Lambda (main-lambda/)"
echo ""
echo "To deploy both lambdas, use the new deployment script:"
echo "  ./deploy-all-lambdas.sh"
echo ""
echo "For more information, see: WEBSOCKET_ARCHITECTURE_README.md"
echo ""
echo "Exiting without deployment..."

exit 1

# Original script content below (kept for reference)
# Deploy WebSocket-enabled Lambda function for Selador Real Estate Backend
# This script packages and deploys the updated main-lambda function

set -e

echo "🚀 Deploying WebSocket-enabled Lambda function..."

# Configuration
FUNCTION_NAME="selador-realestate-backend"
REGION="us-west-2"
LAMBDA_DIR="main-lambda"
PACKAGE_NAME="lambda-package.zip"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check if we're in the right directory
if [ ! -d "$LAMBDA_DIR" ]; then
    print_error "Lambda directory '$LAMBDA_DIR' not found. Please run this script from the backend directory."
    exit 1
fi

# Check if shared directory exists
if [ ! -d "shared" ]; then
    print_error "Shared directory not found. Please run this script from the backend directory."
    exit 1
fi

print_status "Starting deployment process..."

# Clean up previous package
if [ -f "$PACKAGE_NAME" ]; then
    print_status "Removing previous package..."
    rm -f "$PACKAGE_NAME"
fi

# Create temporary directory for packaging
TEMP_DIR=$(mktemp -d)
print_status "Created temporary directory: $TEMP_DIR"

# Copy Lambda function files
print_status "Copying Lambda function files..."
cp -r "$LAMBDA_DIR"/* "$TEMP_DIR/"
cp -r shared "$TEMP_DIR/"

# Install dependencies
print_status "Installing Python dependencies..."
cd "$TEMP_DIR"
pip install -r requirements.txt -t . --quiet

# Remove unnecessary files to reduce package size
print_status "Cleaning up package..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# Create deployment package
print_status "Creating deployment package..."
zip -r "$PACKAGE_NAME" . -q

# Move package back to original directory
cd - > /dev/null
mv "$TEMP_DIR/$PACKAGE_NAME" .

# Clean up temporary directory
rm -rf "$TEMP_DIR"

print_status "Package created: $PACKAGE_NAME"

# Check package size
PACKAGE_SIZE=$(du -h "$PACKAGE_NAME" | cut -f1)
print_status "Package size: $PACKAGE_SIZE"

# Deploy to AWS Lambda
print_status "Deploying to AWS Lambda..."

# Check if function exists
if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" &>/dev/null; then
    print_status "Updating existing Lambda function..."
    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file "fileb://$PACKAGE_NAME" \
        --region "$REGION"
    
    print_status "Updating function configuration..."
    aws lambda update-function-configuration \
        --function-name "$FUNCTION_NAME" \
        --timeout 900 \
        --memory-size 1024 \
        --region "$REGION"
        
    print_status "Lambda function updated successfully!"
else
    print_warning "Lambda function '$FUNCTION_NAME' not found."
    print_status "You'll need to create it first or update the function name in this script."
    print_status "Package is ready for manual deployment."
fi

# Clean up package
print_status "Cleaning up deployment package..."
rm -f "$PACKAGE_NAME"

print_status "✅ Deployment process completed!"
print_status ""
print_status "Next steps:"
print_status "1. Ensure your API Gateway WebSocket API is configured with the Lambda integration"
print_status "2. Test the WebSocket connection using the test client"
print_status "3. Check CloudWatch logs for any errors"
print_status ""
print_status "For testing, run: python test_websocket_client.py"
print_status "Remember to update the WebSocket URL in the test client first!" 