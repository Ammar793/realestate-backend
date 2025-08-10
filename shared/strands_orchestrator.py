from typing import Dict, Any, List
from strands import Agent
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
        logger.info("=== INITIALIZING STRANDS AGENT ORCHESTRATOR ===")
        
        self.agents: Dict[str, Agent] = {}
        self.mcp_client = None
        self.gateway_tools = []
        self.agent_tools = {}  # Initialize agent_tools dict
        
        # Load AgentCore configuration
        logger.info("Loading AgentCore configuration...")
        self.config = self._load_agentcore_config()
        logger.info(f"Configuration loaded: {list(self.config.keys())}")
        
        # Initialize the agent system
        logger.info("Setting up agents...")
        self._setup_agents()
        logger.info(f"Agents created: {list(self.agents.keys())}")
        
        logger.info("Setting up AgentCore Gateway...")
        self._setup_agentcore_gateway()
        
        logger.info("Setting up workflows...")
        self._setup_workflows()
        
        logger.info("=== STRANDS ORCHESTRATOR INITIALIZATION COMPLETE ===")
        logger.info(f"Final status: {len(self.agents)} agents, {len(self.gateway_tools)} tools, MCP client: {self.mcp_client is not None}")
    
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
        logger.info("=== SETTING UP AGENTS ===")
        
        # Create Bedrock model for agents
        logger.info("Creating Bedrock model...")
        bedrock_model = BedrockModel(
            inference_profile_id="anthropic.claude-3-5-sonnet-20241022-v1:0",
            temperature=0.7,
            streaming=False,
        )
        logger.info("Bedrock model created successfully")
        
        # Create agents without tools initially - tools will be added after gateway setup
        logger.info("Creating supervisor agent...")
        self.agents["supervisor"] = Agent(
            name="supervisor",
            description="Coordinates and routes queries to appropriate agents",
            system_prompt="""You are a supervisor agent that coordinates real estate analysis tasks. 
            Route queries to the appropriate specialized agents and synthesize their responses.
            You have access to powerful tools that you can use directly to perform analysis and provide comprehensive insights.
            
            Available agents:
            - rag: For knowledge base queries and document retrieval
            - property: For property-specific analysis and insights
            - market: For market trends and analysis
            
            When you have access to tools, use them proactively to gather information and provide data-driven insights.
            Always provide clear, actionable insights and cite your sources when possible.""",
            model=bedrock_model
        )
        logger.info("Supervisor agent created")
        
        # RAG agent for knowledge base queries
        logger.info("Creating RAG agent...")
        self.agents["rag"] = Agent(
            name="rag",
            description="Handles knowledge base queries and document retrieval",
            system_prompt="""You are a RAG agent specialized in real estate knowledge base queries. 
            You have access to powerful tools that you can use directly to retrieve and synthesize information from documents.
            When you have access to tools, use them proactively to search knowledge bases, retrieve documents, and gather information.
            Always provide citations and source information when available.
            Focus on providing accurate, up-to-date information from the knowledge base.""",
            model=bedrock_model
        )
        logger.info("RAG agent created")
        
        # Market analysis agent
        logger.info("Creating market agent...")
        self.agents["market"] = Agent(
            name="market",
            description="Analyzes market trends and provides market insights",
            system_prompt="""You are a market analysis agent. Analyze market trends, 
            provide insights on pricing, and identify market opportunities.
            You have access to powerful tools that you can use directly to gather market data and perform analysis.
            When you have access to tools, use them proactively to collect market data, analyze trends, and provide insights.
            Provide data-driven insights with specific metrics and trends.""",
            model=bedrock_model
        )
        logger.info("Market agent created")
        
        # Property analysis agent
        logger.info("Creating property agent...")
        self.agents["property"] = Agent(
            name="property",
            description="Analyzes individual properties and provides property insights",
            system_prompt="""You are a property analysis agent. Analyze property characteristics, 
            zoning, permits, and provide property-specific recommendations.
            You have access to powerful tools that you can use directly to gather property data and perform analysis.
            When you have access to tools, use them proactively to collect property information, analyze zoning data, and gather permit information.
            Focus on practical insights for real estate development and investment.""",
            model=bedrock_model
        )
        logger.info("Property agent created")
        
        logger.info(f"All agents created successfully: {list(self.agents.keys())}")
    
    def _setup_agentcore_gateway(self):
        """Setup connection to AgentCore Gateway with Cognito authentication"""
        logger.info("=== SETTING UP AGENTCORE GATEWAY ===")
        
        if not self.config.get("gateway_url"):
            logger.warning("AgentCore Gateway URL not configured. Agents will run without tools.")
            return
        
        logger.info(f"Gateway URL: {self.config.get('gateway_url')}")
        logger.info(f"Region: {self.config.get('region')}")
        
        try:
            # Try to get Cognito authenticator
            logger.info("Attempting to create Cognito authenticator...")
            from cognito_auth import create_cognito_authenticator_from_config, create_cognito_authenticator_from_env
            
            # First try from config, then from environment
            cognito_auth = create_cognito_authenticator_from_config(self.config)
            if not cognito_auth:
                logger.info("Cognito auth from config failed, trying environment...")
                cognito_auth = create_cognito_authenticator_from_env()
            
            if cognito_auth:
                logger.info("Using Cognito authentication for AgentCore Gateway")
                
                # Create MCP client with Cognito authentication
                def create_streamable_http_transport(mcp_url: str):
                    headers = cognito_auth.get_auth_headers()
                    logger.info(f"Created transport with headers: {list(headers.keys())}")
                    return streamablehttp_client(mcp_url, headers=headers)
                
                self.mcp_client = MCPClient(
                    lambda: create_streamable_http_transport(self.config["gateway_url"])
                )
                logger.info("MCP client created with Cognito authentication")
                
            else:
                # Fallback to legacy access token if available
                if self.config.get("access_token"):
                    logger.info("Using legacy access token for AgentCore Gateway")
                    
                    def create_streamable_http_transport(mcp_url: str, access_token: str):
                        return streamablehttp_client(mcp_url, headers={"Authorization": f"Bearer {access_token}"})
                    
                    self.mcp_client = MCPClient(
                        lambda: create_streamable_http_transport(
                            self.config["gateway_url"], 
                            self.config["access_token"]
                        )
                    )
                    logger.info("MCP client created with legacy access token")
                else:
                    logger.warning("No authentication method available for AgentCore Gateway")
                    return
            
            # Get tools from gateway
            logger.info("Loading tools from gateway...")
            self._load_gateway_tools()
            
            # Add tools to agents
            logger.info("Distributing tools to agents...")
            self._distribute_tools_to_agents()
            
            logger.info(f"AgentCore Gateway connected successfully with {len(self.gateway_tools)} tools")
            
        except Exception as e:
            logger.error(f"Error setting up AgentCore Gateway: {e}")
            logger.error(f"Error type: {type(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            self.mcp_client = None
    
    def _load_gateway_tools(self):
        """Load all tools from the AgentCore Gateway"""
        if not self.mcp_client:
            logger.warning("No MCP client available for loading tools")
            return
        
        logger.info("=== LOADING GATEWAY TOOLS ===")
        
        try:
            with self.mcp_client:
                logger.info("MCP client context entered")
                more_tools = True
                pagination_token = None
                tools_loaded = 0
                
                while more_tools:
                    logger.info(f"Loading tools batch {tools_loaded + 1}...")
                    tmp_tools = self.mcp_client.list_tools_sync(pagination_token=pagination_token)
                    logger.info(f"Retrieved {len(tmp_tools)} tools in this batch")
                    
                    # Log tool details
                    for tool in tmp_tools:
                        logger.info(f"Tool: {tool.tool_name} - {tool.description}")
                    
                    self.gateway_tools.extend(tmp_tools)
                    tools_loaded += len(tmp_tools)
                    
                    if tmp_tools.pagination_token is None:
                        more_tools = False
                        logger.info("No more tools to load (pagination complete)")
                    else:
                        pagination_token = tmp_tools.pagination_token
                        logger.info(f"Continuing with pagination token: {pagination_token}")
                        
            logger.info(f"Successfully loaded {len(self.gateway_tools)} tools from gateway")
            logger.info(f"Tool names: {[tool.tool_name for tool in self.gateway_tools]}")
            
        except Exception as e:
            logger.error(f"Error loading gateway tools: {e}")
            logger.error(f"Error type: {type(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
    
    def _distribute_tools_to_agents(self):
        """Distribute gateway tools to appropriate agents"""
        if not self.gateway_tools:
            logger.warning("No gateway tools available for distribution")
            return
        
        logger.info(f"=== DISTRIBUTING {len(self.gateway_tools)} TOOLS TO AGENTS ===")
        
        # Map tools to agents based on functionality
        tool_mapping = {
            "rag_query": ["rag", "supervisor"],
            "property_analysis": ["property", "supervisor"],
            "market_analysis": ["market", "supervisor"]
        }
        
        logger.info(f"Tool mapping: {tool_mapping}")
        
        # Create new agents with tools for each agent
        for agent_name in self.agents:
            logger.info(f"Processing agent: {agent_name}")
            if agent_name in self.agents:
                # Get the original agent
                original_agent = self.agents[agent_name]
                logger.info(f"Original agent {agent_name} retrieved")
                
                # Get tools for this agent
                agent_tools = []
                for tool in self.gateway_tools:
                    tool_name = tool.tool_name
                    logger.info(f"Checking tool: {tool_name}")
                    # Find which agents should have this tool
                    target_agents = tool_mapping.get(tool_name, ["supervisor"])
                    logger.info(f"Tool {tool_name} targets agents: {target_agents}")
                    if agent_name in target_agents:
                        agent_tools.append(tool)
                        logger.info(f"Added tool {tool_name} to agent {agent_name}")
                
                logger.info(f"Agent {agent_name} will have {len(agent_tools)} tools")
                
                if agent_tools:
                    # Create a new agent with tools
                    logger.info(f"Creating new agent {agent_name} with tools")
                    new_agent = Agent(
                        name=original_agent.name,
                        description=original_agent.description,
                        system_prompt=original_agent.system_prompt,
                        model=original_agent.model,
                        tools=agent_tools  # Pass tools during initialization
                    )
                    
                    # Replace the original agent with the new one that has tools
                    self.agents[agent_name] = new_agent
                    logger.info(f"Successfully created agent {agent_name} with {len(agent_tools)} tools")
                    
                    # Store tool info for reference
                    if agent_name not in self.agent_tools:
                        self.agent_tools[agent_name] = []
                    self.agent_tools[agent_name].extend(agent_tools)
                    logger.info(f"Stored {len(agent_tools)} tools for agent {agent_name}")
                else:
                    logger.info(f"Agent {agent_name} has no tools assigned")
        
        logger.info(f"=== TOOL DISTRIBUTION COMPLETE ===")
        logger.info(f"Final agent tools: {self.agent_tools}")
    
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
            logger.info(f"=== STRANDS ORCHESTRATOR: Starting route_query ===")
            logger.info(f"Query: {query}")
            logger.info(f"Context: {context}")
            logger.info(f"Query Type: {query_type}")
            
            # Determine which agent to use based on query type
            target_agent_name = self._select_agent_for_query(query, query_type)
            logger.info(f"Selected agent: {target_agent_name}")
            
            if target_agent_name not in self.agents:
                logger.error(f"Agent {target_agent_name} not found in available agents: {list(self.agents.keys())}")
                return {
                    "success": False,
                    "error": f"Agent {target_agent_name} not found"
                }
            
            target_agent = self.agents[target_agent_name]
            logger.info(f"Retrieved agent: {target_agent.name}")
            
            # Check if agent has tools
            agent_tools_count = len(self.agent_tools.get(target_agent_name, []))
            logger.info(f"Agent {target_agent_name} has {agent_tools_count} tools available")
            
            if agent_tools_count > 0:
                logger.info(f"Available tools for {target_agent_name}: {[tool.tool_name for tool in self.agent_tools[target_agent_name]]}")
            
            # Create the full query with context
            full_query = f"Query: {query}"
            if context:
                full_query += f"\nContext: {context}"
            if query_type != "general":
                full_query += f"\nQuery Type: {query_type}"
            
            logger.info(f"Full query to send to agent: {full_query}")
            logger.info(f"=== EXECUTING AGENT {target_agent_name} ===")
            
            # Execute the agent - it now has tools and can execute them directly
            try:
                logger.info(f"Calling agent.invoke() with query...")
                response = target_agent(full_query)
                logger.info(f"Agent execution completed successfully")
                logger.info(f"Response type: {type(response)}")
                logger.info(f"Response attributes: {dir(response)}")
                
                # Extract content from response
                if hasattr(response, 'content'):
                    content = response.content
                    logger.info(f"Response content type: {type(content)}")
                    logger.info(f"Response content: {content}")
                else:
                    content = str(response)
                    logger.info(f"Response as string: {content}")
                
                # Check for tools used
                tools_used = getattr(response, 'tools_used', 0)
                logger.info(f"Tools used in execution: {tools_used}")
                
                # Check for other response attributes
                if hasattr(response, 'stop_reason'):
                    logger.info(f"Stop reason: {response.stop_reason}")
                if hasattr(response, 'metrics'):
                    logger.info(f"Execution metrics: {response.metrics}")
                if hasattr(response, 'state'):
                    logger.info(f"Final state: {response.state}")
                
                return {
                    "success": True,
                    "content": content,
                    "agent": target_agent_name,
                    "query_type": query_type,
                    "tools_available": agent_tools_count,
                    "tools_used": tools_used,
                    "selected_agent": target_agent_name,
                    "response_type": str(type(response))
                }
                
            except Exception as agent_error:
                logger.error(f"Error executing agent {target_agent_name}: {agent_error}")
                logger.error(f"Error type: {type(agent_error)}")
                logger.error(f"Error details: {str(agent_error)}")
                import traceback
                logger.error(f"Full traceback: {traceback.format_exc()}")
                return {
                    "success": False,
                    "error": f"Agent execution failed: {str(agent_error)}",
                    "agent": target_agent_name,
                    "query_type": query_type,
                    "error_type": str(type(agent_error))
                }
            
        except Exception as e:
            logger.error(f"Error routing query: {e}")
            logger.error(f"Error type: {type(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
                "error_type": str(type(e))
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
            
            # Execute the agent - it now has tools and can execute them directly
            try:
                response = agent(action_prompt)
                
                return {
                    "success": True,
                    "content": response.content if hasattr(response, 'content') else str(response),
                    "agent": agent.name,
                    "action": action,
                    "parameters": parameters,
                    "tools_available": len(self.agent_tools.get(agent.name, [])),
                    "tools_used": getattr(response, 'tools_used', 0)
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
            "agent_tools": {agent: len(tools) for agent, tools in self.agent_tools.items()},
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
    
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a specific tool with given parameters"""
        if not self.mcp_client:
            return {"success": False, "error": "AgentCore Gateway not connected"}
        
        # Find the tool by name
        target_tool = None
        for tool in self.gateway_tools:
            if tool.tool_name == tool_name:
                target_tool = tool
                break
        
        if not target_tool:
            return {"success": False, "error": f"Tool {tool_name} not found"}
        
        try:
            # Execute the tool using MCP client
            with self.mcp_client:
                result = self.mcp_client.call_tool_sync(tool_name, parameters)
                return {
                    "success": True,
                    "tool_name": tool_name,
                    "result": result,
                    "parameters": parameters
                }
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return {
                "success": False,
                "error": f"Tool execution failed: {str(e)}",
                "tool_name": tool_name
            }
    
    def debug_tool_execution(self, tool_name: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Debug method to test tool execution directly"""
        logger.info(f"=== DEBUGGING TOOL EXECUTION: {tool_name} ===")
        
        if not self.mcp_client:
            logger.error("No MCP client available")
            return {"success": False, "error": "No MCP client available"}
        
        # Find the tool
        target_tool = None
        for tool in self.gateway_tools:
            if tool.tool_name == tool_name:
                target_tool = tool
                break
        
        if not target_tool:
            logger.error(f"Tool {tool_name} not found in gateway tools")
            logger.info(f"Available tools: {[tool.tool_name for tool in self.gateway_tools]}")
            return {"success": False, "error": f"Tool {tool_name} not found"}
        
        logger.info(f"Found tool: {target_tool.tool_name}")
        logger.info(f"Tool description: {target_tool.description}")
        logger.info(f"Tool input schema: {getattr(target_tool, 'input_schema', 'Not available')}")
        
        # Use default parameters if none provided
        if parameters is None:
            parameters = {}
            logger.info("Using empty parameters for tool execution")
        
        logger.info(f"Executing tool with parameters: {parameters}")
        
        try:
            with self.mcp_client:
                logger.info("MCP client context entered for tool execution")
                result = self.mcp_client.call_tool_sync(tool_name, parameters)
                logger.info(f"Tool execution completed successfully")
                logger.info(f"Result type: {type(result)}")
                logger.info(f"Result: {result}")
                
                return {
                    "success": True,
                    "tool_name": tool_name,
                    "result": result,
                    "parameters": parameters,
                    "result_type": str(type(result))
                }
                
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            logger.error(f"Error type: {type(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "error": f"Tool execution failed: {str(e)}",
                "tool_name": tool_name,
                "error_type": str(type(e))
            }
    
    def get_debug_info(self) -> Dict[str, Any]:
        """Get comprehensive debug information about the orchestrator state"""
        return {
            "orchestrator_status": "active",
            "agents_count": len(self.agents),
            "agents": list(self.agents.keys()),
            "gateway_connected": self.mcp_client is not None,
            "gateway_tools_count": len(self.gateway_tools),
            "gateway_tools": [tool.tool_name for tool in self.gateway_tools],
            "agent_tools": {agent: [tool.tool_name for tool in tools] for agent, tools in self.agent_tools.items()},
            "config_keys": list(self.config.keys()) if self.config else [],
            "mcp_client_type": str(type(self.mcp_client)) if self.mcp_client else "None"
        }
    
    def get_agent_tools(self, agent_name: str) -> List[Dict[str, Any]]:
        """Get tools available for a specific agent"""
        if agent_name not in self.agent_tools:
            return []
        
        tools_info = []
        for tool in self.agent_tools[agent_name]:
            tools_info.append({
                "name": tool.tool_name,
                "description": tool.description,
                "input_schema": getattr(tool, 'input_schema', {})
            })
        return tools_info 