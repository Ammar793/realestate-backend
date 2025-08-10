#!/bin/bash

# Development Setup Script for Backend
# This script helps set up the development environment with the new organized structure

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Backend Development Setup${NC}"
echo "================================"
echo ""

# Check if we're in the right directory
if [ ! -d "main-lambda" ] || [ ! -d "tool-lambda" ] || [ ! -d "shared" ]; then
    echo -e "${RED}❌ Please run this script from the backend directory${NC}"
    echo "Current directory: $(pwd)"
    exit 1
fi

echo -e "${BLUE}📁 Current Directory Structure:${NC}"
echo "├── main-lambda/     # Main lambda function (with requirements.txt)"
echo "├── tool-lambda/     # Tool execution lambda (with requirements.txt)"
echo "├── shared/          # Shared components"
echo "├── requirements.txt # Shared dependencies"
echo "└── README.md        # Documentation"
echo ""

# Check Python installation
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Python 3 found: $(python3 --version)${NC}"

# Install dependencies
echo -e "${BLUE}📦 Installing Python dependencies...${NC}"
echo -e "${BLUE}  Installing shared dependencies...${NC}"
if [ -f "requirements.txt" ]; then
    pip3 install -r requirements.txt
    echo -e "${GREEN}✅ Shared dependencies installed${NC}"
else
    echo -e "${YELLOW}⚠️  No shared requirements.txt found${NC}"
fi

echo -e "${BLUE}  Installing main-lambda dependencies...${NC}"
if [ -f "main-lambda/requirements.txt" ]; then
    pip3 install -r main-lambda/requirements.txt
    echo -e "${GREEN}✅ Main lambda dependencies installed${NC}"
else
    echo -e "${YELLOW}⚠️  No main-lambda/requirements.txt found${NC}"
fi

echo -e "${BLUE}  Installing tool-lambda dependencies...${NC}"
if [ -f "tool-lambda/requirements.txt" ]; then
    pip3 install -r tool-lambda/requirements.txt
    echo -e "${GREEN}✅ Tool lambda dependencies installed${NC}"
else
    echo -e "${YELLOW}⚠️  No tool-lambda/requirements.txt found${NC}"
fi

# Check environment configuration
echo -e "${BLUE}🔧 Checking environment configuration...${NC}"
if [ -f "config.env.example" ]; then
    if [ ! -f "config.env" ]; then
        echo -e "${YELLOW}⚠️  config.env not found. Creating from template...${NC}"
        cp config.env.example config.env
        echo -e "${GREEN}✅ Created config.env from template${NC}"
        echo -e "${YELLOW}⚠️  Please edit config.env with your actual values${NC}"
    else
        echo -e "${GREEN}✅ config.env found${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  No config.env.example found${NC}"
fi

# Test imports
echo -e "${BLUE}🧪 Testing imports...${NC}"

echo -e "${BLUE}  Testing main lambda...${NC}"
cd main-lambda
if python3 -c "import lambda_function; print('✅ Main lambda imports successfully')" 2>/dev/null; then
    echo -e "${GREEN}✅ Main lambda ready${NC}"
else
    echo -e "${RED}❌ Main lambda import failed${NC}"
fi
cd ..

echo -e "${BLUE}  Testing tool lambda...${NC}"
cd tool-lambda
if python3 -c "import tool_lambda_function; print('✅ Tool lambda imports successfully')" 2>/dev/null; then
    echo -e "${GREEN}✅ Tool lambda ready${NC}"
else
    echo -e "${RED}❌ Tool lambda import failed${NC}"
fi
cd ..

echo -e "${BLUE}  Testing shared components...${NC}"
cd shared
if python3 -c "import strands_orchestrator; print('✅ Orchestrator imports successfully')" 2>/dev/null; then
    echo -e "${GREEN}✅ Shared components ready${NC}"
else
    echo -e "${RED}❌ Shared components import failed${NC}"
fi
cd ..

echo ""
echo -e "${GREEN}🎉 Development environment setup completed!${NC}"
echo ""
echo -e "${BLUE}📚 Next Steps:${NC}"
echo "1. Edit config.env with your AWS credentials and configuration"
echo "2. Test the AgentCore gateway: cd shared && python3 start_gateway.py"
echo "3. Deploy tool lambda: cd tool-lambda && ./deploy-tool-lambda.sh"
echo "4. Push changes to trigger CI/CD deployment"
echo ""
echo -e "${BLUE}🔍 Useful Commands:${NC}"
echo "• View main lambda: cat main-lambda/lambda_function.py"
echo "• View tool lambda: cat tool-lambda/tool_lambda_function.py"
echo "• View orchestrator: cat shared/strands_orchestrator.py"
echo "• Check agents: ls shared/agents/"
echo ""
echo -e "${GREEN}Happy coding! 🚀${NC}" 