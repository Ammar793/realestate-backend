from typing import Dict, Any, List
from strands import Agent, Message
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client
import asyncio
import logging
import json
import os

logger = logging.getLogger(__name__)

class StrandsAgentOrchestrator:
    """Orchestrates agents using Strands framework with AgentCore Gateway"""
    
    def __init__(self):
        # Remove AgentSystem dependency but keep everything else
        self.agents: Dict[str, Agent] = {}
        self.mcp_client = None
        self.gateway_tools = []
        
        # Load AgentCore configuration
        self.config = self._load_agentcore_config()
        
        # Initialize the agent system
        self._setup_agents()
        self._setup_agentcore_gateway()
        self._setup_workflows()
    
    def _load_agentcore_config(self) -> Dict[str, Any]:
        """Load AgentCore Gateway configuration"""
        try:
            if os.path.exists("agentcore_config.json"):
                with open("agentcore_config.json", "r") as f:
                    return json.load(f)
            else:
                logger.warning("agentcore_config.json not found. Using environment variables.")
                return {
                    "gateway_url": os.getenv("AGENTCORE_GATEWAY_URL"),
                    "access_token": os.getenv("AGENTCORE_ACCESS_TOKEN"),
                    "region": os.getenv("AWS_REGION", "us-west-2")
                }
        except Exception as e:
            logger.error(f"Error loading AgentCore config: {e}")
            return {}
    
    def _setup_agents(self):
        """Initialize Strands agents with Bedrock models"""
        # Create Bedrock model for agents
        bedrock_model = BedrockModel(
            inference_profile_id="anthropic.claude-3-5-sonnet-20241022-v1:0",
            temperature=0.7,
            streaming=False,
        )
        
        # Create agents (simplified without AgentSystem)
        self.agents["supervisor"] = Agent(
            name="supervisor",
            description="Coordinates and routes queries to appropriate agents",
            system_prompt="""You are a supervisor agent that coordinates real estate analysis tasks. 
            Route queries to the appropriate specialized agents and synthesize their responses.
            Use the available tools to perform analysis and provide comprehensive insights.
            
            Available agents:
            - rag: For knowledge base queries and document retrieval
            - property: For property-specific analysis and insights
            - market: For market trends and analysis
            
            Always provide clear, actionable insights and cite your sources when possible.""",
            model=bedrock_model
        )
        
        # RAG agent for knowledge base queries
        self.agents["rag"] = Agent(
            name="rag",
            description="Handles knowledge base queries and document retrieval",
            system_prompt="""You are a RAG agent specialized in real estate knowledge base queries. 
            Use the available tools to retrieve and synthesize information from documents.
            Always provide citations and source information when available.
            Focus on providing accurate, up-to-date information from the knowledge base.""",
            model=bedrock_model
        )
        
        # Market analysis agent
        self.agents["market"] = Agent(
            name="market",
            description="Analyzes market trends and provides market insights",
            system_prompt="""You are a market analysis agent. Analyze market trends, 
            provide insights on pricing, and identify market opportunities.
            Use the available tools to gather market data and perform analysis.
            Provide data-driven insights with specific metrics and trends.""",
            model=bedrock_model
        )
        
        # Property analysis agent
        self.agents["property"] = Agent(
            name="property",
            description="Analyzes individual properties and provides property insights",
            system_prompt="""You are a property analysis agent. Analyze property characteristics, 
            zoning, permits, and provide property-specific recommendations.
            Use the available tools to gather property data and perform analysis.
            Focus on practical insights for real estate development and investment.""",
            model=bedrock_model
        )
        
        # Remove the AgentSystem.add_agent calls but keep agents in our dict
        # for agent in self.agents.values():
        #     self.agent_system.add_agent(agent)
    
    def _setup_agentcore_gateway(self):
        """Setup connection to AgentCore Gateway"""
        if not self.config.get("gateway_url") or not self.config.get("access_token"):
            logger.warning("AgentCore Gateway not configured. Agents will run without tools.")
            return
        
        try:
            # Create MCP client for AgentCore Gateway
            def create_streamable_http_transport(mcp_url: str, access_token: str):
                return streamablehttp_client(mcp_url, headers={"Authorization": f"Bearer {access_token}"})
            
            self.mcp_client = MCPClient(
                lambda: create_streamable_http_transport(
                    self.config["gateway_url"], 
                    self.config["access_token"]
                )
            )
            
            # Get tools from gateway
            self._load_gateway_tools()
            
            # Add tools to agents
            self._distribute_tools_to_agents()
            
            logger.info(f"AgentCore Gateway connected successfully with {len(self.gateway_tools)} tools")
            
        except Exception as e:
            logger.error(f"Error setting up AgentCore Gateway: {e}")
            self.mcp_client = None
    
    def _load_gateway_tools(self):
        """Load all tools from the AgentCore Gateway"""
        if not self.mcp_client:
            return
        
        try:
            with self.mcp_client:
                more_tools = True
                pagination_token = None
                
                while more_tools:
                    tmp_tools = self.mcp_client.list_tools_sync(pagination_token=pagination_token)
                    self.gateway_tools.extend(tmp_tools)
                    
                    if tmp_tools.pagination_token is None:
                        more_tools = False
                    else:
                        pagination_token = tmp_tools.pagination_token
                        
            logger.info(f"Loaded {len(self.gateway_tools)} tools from gateway")
            
        except Exception as e:
            logger.error(f"Error loading gateway tools: {e}")
    
    def _distribute_tools_to_agents(self):
        """Distribute gateway tools to appropriate agents"""
        if not self.gateway_tools:
            return
        
        # Map tools to agents based on functionality
        tool_mapping = {
            "rag_query": ["rag", "supervisor"],
            "property_analysis": ["property", "supervisor"],
            "market_analysis": ["market", "supervisor"]
        }
        
        for tool in self.gateway_tools:
            tool_name = tool.tool_name
            
            # Find which agents should have this tool
            target_agents = tool_mapping.get(tool_name, ["supervisor"])
            
            for agent_name in target_agents:
                if agent_name in self.agents:
                    try:
                        self.agents[agent_name].add_tool(tool)
                        logger.info(f"Added tool {tool_name} to agent {agent_name}")
                    except Exception as e:
                        logger.error(f"Error adding tool {tool_name} to agent {agent_name}: {e}")
    
    def _setup_workflows(self):
        """Define agent workflows"""
        # Property analysis workflow
        self.workflows = {
            "property_analysis": {
                "description": "Comprehensive property analysis",
                "steps": [
                    {"agent": "property", "action": "analyze_property"},
                    {"agent": "rag", "action": "query_knowledge_base"},
                    {"agent": "supervisor", "action": "synthesize_results"}
                ]
            },
            "market_research": {
                "description": "Market research and analysis",
                "steps": [
                    {"agent": "market", "action": "analyze_market"},
                    {"agent": "rag", "action": "query_knowledge_base"},
                    {"agent": "supervisor", "action": "synthesize_market_results"}
                ]
            },
            "comprehensive_analysis": {
                "description": "Full property and market analysis",
                "steps": [
                    {"agent": "property", "action": "analyze_property"},
                    {"agent": "market", "action": "analyze_market"},
                    {"agent": "rag", "action": "query_knowledge_base"},
                    {"agent": "supervisor", "action": "synthesize_comprehensive_results"}
                ]
            }
        }
    
    async def route_query(self, query: str, context: str = "", query_type: str = "general") -> Dict[str, Any]:
        """Route a query through the Strands agent system"""
        try:
            # Determine which agent to use based on query type
            target_agent_name = self._select_agent_for_query(query, query_type)
            
            if target_agent_name not in self.agents:
                return {
                    "success": False,
                    "error": f"Agent {target_agent_name} not found"
                }
            
            target_agent = self.agents[target_agent_name]
            
            # Create the full query with context
            full_query = f"Query: {query}"
            if context:
                full_query += f"\nContext: {context}"
            if query_type != "general":
                full_query += f"\nQuery Type: {query_type}"
            
            # Execute the agent directly using Strands Agent.__call__ method
            try:
                # Use the agent directly - Strands Agent objects are callable
                response = await target_agent(full_query)
                
                return {
                    "success": True,
                    "content": response.content if hasattr(response, 'content') else str(response),
                    "agent": target_agent_name,
                    "query_type": query_type,
                    "tools_used": len(self.gateway_tools),
                    "selected_agent": target_agent_name
                }
                
            except Exception as agent_error:
                logger.error(f"Error executing agent {target_agent_name}: {agent_error}")
                return {
                    "success": False,
                    "error": f"Agent execution failed: {str(agent_error)}",
                    "agent": target_agent_name,
                    "query_type": query_type
                }
            
        except Exception as e:
            logger.error(f"Error routing query: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _select_agent_for_query(self, query: str, query_type: str) -> str:
        """Select the most appropriate agent for a given query"""
        query_lower = query.lower()
        
        # Keyword-based routing
        if any(word in query_lower for word in ["zoning", "permit", "property", "address", "development"]):
            return "property"
        elif any(word in query_lower for word in ["market", "trend", "price", "inventory", "demand"]):
            return "market"
        elif any(word in query_lower for word in ["regulation", "code", "requirement", "document"]):
            return "rag"
        else:
            # Default to supervisor for complex queries
            return "supervisor"
    
    async def execute_workflow(self, workflow_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a predefined workflow"""
        if workflow_name not in self.workflows:
            raise ValueError(f"Unknown workflow: {workflow_name}")
        
        workflow = self.workflows[workflow_name]
        logger.info(f"Executing workflow: {workflow_name}")
        
        # Execute workflow steps
        results = {}
        for step in workflow["steps"]:
            agent_name = step["agent"]
            action = step["action"]
            
            if agent_name in self.agents:
                agent = self.agents[agent_name]
                # Execute the action (this will be enhanced with AgentCore tools)
                result = await self._execute_agent_action(agent, action, parameters)
                results[action] = result
        
        return {
            "workflow": workflow_name,
            "success": True,
            "results": results
        }
    
    async def _execute_agent_action(self, agent: Agent, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an action on a specific agent"""
        try:
            # Create the action prompt with parameters
            action_prompt = f"Execute action: {action}"
            if parameters:
                action_prompt += f"\nParameters: {json.dumps(parameters, indent=2)}"
            
            # Execute the agent directly using Strands Agent.__call__ method
            try:
                # Use the agent directly - Strands Agent objects are callable
                response = await agent(action_prompt)
                
                return {
                    "success": True,
                    "content": response.content if hasattr(response, 'content') else str(response),
                    "agent": agent.name,
                    "action": action,
                    "parameters": parameters
                }
                
            except Exception as agent_error:
                logger.error(f"Error executing action {action} on agent {agent.name}: {agent_error}")
                return {
                    "success": False,
                    "error": f"Agent action execution failed: {str(agent_error)}",
                    "agent": agent.name,
                    "action": action
                }
            
        except Exception as e:
            logger.error(f"Error executing agent action: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get the status of the Strands agent system"""
        return {
            "orchestrator": "strands_with_agentcore_simplified",
            "status": "active",
            "agents": list(self.agents.keys()),
            "gateway_connected": self.mcp_client is not None,
            "tools_available": len(self.gateway_tools),
            "workflows": list(self.workflows.keys()),
            "gateway_config": {
                "url": self.config.get("gateway_url"),
                "region": self.config.get("region")
            }
        }
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools from the gateway"""
        tools_info = []
        for tool in self.gateway_tools:
            tools_info.append({
                "name": tool.tool_name,
                "description": tool.description,
                "input_schema": getattr(tool, 'input_schema', {})
            })
        return tools_info 