#!/bin/bash

# Navigation Script for Backend
# Quick access to different parts of the organized codebase

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

show_help() {
    echo -e "${GREEN}🚀 Backend Navigation${NC}"
    echo "===================="
    echo ""
    echo -e "${BLUE}Usage:${NC} ./nav.sh [command]"
    echo ""
    echo -e "${BLUE}Commands:${NC}"
    echo "  main          - Navigate to main lambda directory"
    echo "  tool          - Navigate to tool lambda directory"
    echo "  shared        - Navigate to shared components directory"
    echo "  agents        - Navigate to agents directory"
    echo "  deploy        - Deploy tool lambda function"
    echo "  setup         - Run development setup"
    echo "  test          - Test all components"
    echo "  status        - Show current status"
    echo "  help          - Show this help message"
    echo ""
    echo -e "${BLUE}Examples:${NC}"
    echo "  ./nav.sh main     # Go to main lambda"
    echo "  ./nav.sh tool     # Go to tool lambda"
    echo "  ./nav.sh deploy   # Deploy tool lambda"
    echo ""
}

navigate_to() {
    local dir="$1"
    local desc="$2"
    
    if [ -d "$dir" ]; then
        echo -e "${GREEN}📁 Navigating to $desc...${NC}"
        cd "$dir"
        echo -e "${BLUE}Current directory: $(pwd)${NC}"
        echo -e "${YELLOW}Available files:${NC}"
        ls -la
    else
        echo -e "${YELLOW}⚠️  Directory $dir not found${NC}"
    fi
}

test_components() {
    echo -e "${BLUE}🧪 Testing all components...${NC}"
    
    # Test main lambda
    echo -e "${BLUE}  Testing main lambda...${NC}"
    cd main-lambda
    if python3 -c "import lambda_function; print('✅ Main lambda ready')" 2>/dev/null; then
        echo -e "${GREEN}✅ Main lambda ready${NC}"
    else
        echo -e "${YELLOW}⚠️  Main lambda import failed${NC}"
    fi
    cd ..
    
    # Test tool lambda
    echo -e "${BLUE}  Testing tool lambda...${NC}"
    cd tool-lambda
    if python3 -c "import tool_lambda_function; print('✅ Tool lambda ready')" 2>/dev/null; then
        echo -e "${GREEN}✅ Tool lambda ready${NC}"
    else
        echo -e "${YELLOW}⚠️  Tool lambda import failed${NC}"
    fi
    cd ..
    
    # Test shared components
    echo -e "${BLUE}  Testing shared components...${NC}"
    cd shared
    if python3 -c "import strands_orchestrator; print('✅ Orchestrator ready')" 2>/dev/null; then
        echo -e "${GREEN}✅ Shared components ready${NC}"
    else
        echo -e "${YELLOW}⚠️  Shared components import failed${NC}"
    fi
    cd ..
    
    echo -e "${GREEN}🎉 Component testing completed!${NC}"
}

show_status() {
    echo -e "${GREEN}📊 Backend Status${NC}"
    echo "================"
    echo ""
    
    echo -e "${BLUE}📁 Directory Structure:${NC}"
    echo "├── main-lambda/     $(if [ -d "main-lambda" ]; then echo "✅"; else echo "❌"; fi)"
    echo "├── tool-lambda/     $(if [ -d "tool-lambda" ]; then echo "✅"; else echo "❌"; fi)"
    echo "├── shared/          $(if [ -d "shared" ]; then echo "✅"; else echo "❌"; fi)"
    echo "├── requirements.txt $(if [ -f "requirements.txt" ]; then echo "✅"; else echo "❌"; fi)"
    echo "└── config.env       $(if [ -f "config.env" ]; then echo "✅"; else echo "❌"; fi)"
    echo ""
    
    echo -e "${BLUE}🔧 Configuration:${NC}"
    if [ -f "config.env" ]; then
        echo "✅ Environment file configured"
    else
        echo "⚠️  Environment file not configured (run ./nav.sh setup)"
    fi
    
    echo ""
    echo -e "${BLUE}📚 Quick Access:${NC}"
    echo "• Main Lambda: ./nav.sh main"
    echo "• Tool Lambda: ./nav.sh tool"
    echo "• Shared: ./nav.sh shared"
    echo "• Deploy: ./nav.sh deploy"
}

# Main script logic
case "${1:-help}" in
    "main")
        navigate_to "main-lambda" "Main Lambda Function"
        ;;
    "tool")
        navigate_to "tool-lambda" "Tool Lambda Function"
        ;;
    "shared")
        navigate_to "shared" "Shared Components"
        ;;
    "agents")
        navigate_to "shared/agents" "Agents Directory"
        ;;
    "deploy")
        if [ -f "tool-lambda/deploy-tool-lambda.sh" ]; then
            echo -e "${GREEN}🚀 Deploying tool lambda...${NC}"
            cd tool-lambda
            ./deploy-tool-lambda.sh
        else
            echo -e "${YELLOW}⚠️  Deploy script not found${NC}"
        fi
        ;;
    "setup")
        if [ -f "dev-setup.sh" ]; then
            echo -e "${GREEN}🔧 Running development setup...${NC}"
            ./dev-setup.sh
        else
            echo -e "${YELLOW}⚠️  Setup script not found${NC}"
        fi
        ;;
    "test")
        test_components
        ;;
    "status")
        show_status
        ;;
    "help"|*)
        show_help
        ;;
esac 