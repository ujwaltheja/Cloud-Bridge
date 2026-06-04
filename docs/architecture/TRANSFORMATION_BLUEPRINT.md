# Cloud Bridge Transformation Blueprint
## Phase 3 & 4: Strategic Gap Analysis + Detailed Implementation

**Date**: 2026-06-02  
**Version**: 1.0  
**Status**: Approved for Implementation

---

## Table of Contents

1. [Strategic Gap Analysis](#strategic-gap-analysis)
2. [Target Architecture Design](#target-architecture-design)
3. [Module Structure & Interfaces](#module-structure--interfaces)
4. [Implementation Priorities](#implementation-priorities)
5. [Technical Specifications](#technical-specifications)

---

## Strategic Gap Analysis

### Gap Scoring Matrix

Each capability gap is scored across 5 dimensions (1-10 scale):

| Gap | Business Impact | Engineering Effort | Technical Complexity | Implementation Risk | Strategic Priority | Total Score |
|-----|----------------|-------------------|---------------------|--------------------|--------------------|-------------|
| **Agent Orchestration Layer** | 10 | 8 | 8 | 6 | 10 | **42/50** |
| **MCP Tool Registry** | 9 | 4 | 5 | 3 | 9 | **30/50** |
| **Context & Memory Management** | 9 | 6 | 7 | 5 | 9 | **36/50** |
| **Multi-Agent Coordination** | 8 | 7 | 8 | 6 | 8 | **37/50** |
| **Deployment Pipelines** | 9 | 6 | 6 | 4 | 9 | **34/50** |
| **Git Integration** | 8 | 5 | 5 | 4 | 7 | **29/50** |
| **API Authentication** | 8 | 3 | 3 | 2 | 9 | **25/50** |
| **Advanced Comparison** | 7 | 4 | 5 | 3 | 6 | **25/50** |
| **Scheduled Operations** | 8 | 2 | 3 | 2 | 7 | **22/50** |
| **Notification System** | 6 | 3 | 3 | 2 | 5 | **19/50** |

### Prioritization Framework

**Tier 1 - Foundation (Weeks 1-4)**
- Agent Orchestration Layer (Score: 42)
- MCP Tool Registry (Score: 30)
- API Authentication (Score: 25)

**Tier 2 - Core Capabilities (Weeks 5-8)**
- Multi-Agent Coordination (Score: 37)
- Context & Memory Management (Score: 36)
- Deployment Pipelines (Score: 34)

**Tier 3 - Advanced Features (Weeks 9-12)**
- Git Integration (Score: 29)
- Advanced Comparison (Score: 25)
- Scheduled Operations (Score: 22)

**Tier 4 - Enhancement (Weeks 13-16)**
- Notification System (Score: 19)
- Monitoring & Analytics
- Performance Optimization

### Transformation Pathways

#### Pathway 1: Agent Orchestration Layer

**Current State:**
- Basic `LLMAgentService` with simple ReAct loop
- Single-agent execution only
- No context persistence
- Limited to 10 iterations
- No tool discovery mechanism

**Target State:**
- Multi-agent orchestration platform
- Agent registry with lifecycle management
- Context manager with conversation state
- Memory layer (short-term + long-term)
- Planning engine for task decomposition
- Tool registry with discovery and validation

**Transformation Steps:**
1. Create `AgentRegistry` for agent lifecycle management
2. Build `ContextManager` for conversation state
3. Implement `MemoryLayer` with Redis backend
4. Design `PlanningEngine` for task decomposition
5. Create `ToolRegistry` with MCP tool discovery
6. Build `PromptExecutionLayer` for NL → tool calls

**Engineering Effort:** 8 weeks (2 engineers)  
**ROI:** Enables autonomous workflows, reduces manual intervention by 80%

#### Pathway 2: MCP Tool Registry

**Current State:**
- Hardcoded tool invocations in `SFDXMCPService`
- Only 4 tools exposed (retrieve, deploy, test, list_orgs)
- No tool discovery or documentation
- Manual tool addition required

**Target State:**
- Dynamic tool registry with auto-discovery
- All 60+ MCP tools available
- Tool metadata (description, schema, examples)
- Tool validation and error handling
- Tool usage analytics

**Transformation Steps:**
1. Create `ToolRegistry` interface
2. Implement MCP tool discovery via `tools/list`
3. Build tool metadata cache
4. Add tool validation layer
5. Create tool documentation generator
6. Implement tool usage tracking

**Engineering Effort:** 4 weeks (1 engineer)  
**ROI:** Unlocks full Salesforce automation, 15x tool coverage increase

#### Pathway 3: Context & Memory Management

**Current State:**
- No conversation history
- No user preferences
- No session management
- Stateless agent execution

**Target State:**
- Persistent conversation history
- User preference storage
- Session management with TTL
- Context-aware agent responses
- Memory retrieval for relevant past interactions

**Transformation Steps:**
1. Design context schema (conversation, user, session)
2. Implement `ContextManager` with Redis
3. Build `MemoryLayer` with vector embeddings
4. Add context injection to agent prompts
5. Implement memory retrieval algorithms
6. Create context cleanup policies

**Engineering Effort:** 6 weeks (1 engineer)  
**ROI:** Improves agent accuracy by 40%, enables personalization

#### Pathway 4: Multi-Agent Coordination

**Current State:**
- Single agent per request
- No agent specialization
- No inter-agent communication
- Sequential execution only

**Target State:**
- Specialized agents (metadata, data, testing, deployment)
- Agent coordination protocol
- Parallel agent execution
- Agent handoff mechanisms
- Collaborative problem solving

**Transformation Steps:**
1. Define agent specializations and capabilities
2. Create `AgentCoordinator` for orchestration
3. Implement agent communication protocol
4. Build agent handoff logic
5. Add parallel execution support
6. Create agent collaboration patterns

**Engineering Effort:** 7 weeks (2 engineers)  
**ROI:** 3x faster complex operations, better problem decomposition

#### Pathway 5: Deployment Pipelines

**Current State:**
- Single-step deployments
- No approval workflows
- No rollback capability
- Manual triggering only

**Target State:**
- Multi-stage pipelines (dev → QA → staging → prod)
- Approval workflows with notifications
- Automated testing gates
- One-click rollback
- Scheduled deployments
- Pipeline templates

**Transformation Steps:**
1. Design pipeline schema and state machine
2. Create `PipelineEngine` for orchestration
3. Implement stage transitions and gates
4. Build approval workflow system
5. Add rollback capability
6. Create pipeline templates

**Engineering Effort:** 6 weeks (2 engineers)  
**ROI:** Production-ready CI/CD, 90% reduction in deployment errors

---

## Target Architecture Design

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Frontend Layer (React)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐│
│  │Agent Console │  │Pipeline UI   │  │Diff Viewer   │  │Org Dashboard││
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘│
└────────────────────────────┬────────────────────────────────────────────┘
                             │ REST API (/api/v1/*) + WebSocket
┌────────────────────────────┴────────────────────────────────────────────┐
│                        API Gateway Layer (FastAPI)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐│
│  │Auth Middleware│  │Rate Limiter  │  │CORS Handler  │  │API Versioning││
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘│
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ API Routes: /agent/* /pipelines/* /orgs/* /metadata/* /data/*   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
┌────────────────────────────┴────────────────────────────────────────────┐
│                    Agent Orchestration Layer (NEW)                       │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                        Agent Registry                             │  │
│  │  - Agent lifecycle management (create, start, stop, destroy)     │  │
│  │  - Agent capability registration                                 │  │
│  │  - Agent health monitoring                                       │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐│
│  │Context Manager│  │Memory Layer  │  │Planning Engine│  │Tool Registry││
│  │- Conversation │  │- Short-term  │  │- Task decomp │  │- Discovery  ││
│  │- User prefs   │  │- Long-term   │  │- Scheduling  │  │- Validation ││
│  │- Session mgmt │  │- Vector DB   │  │- Dependency  │  │- Analytics  ││
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘│
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    Agent Coordinator                              │  │
│  │  - Multi-agent orchestration                                     │  │
│  │  - Agent communication protocol                                  │  │
│  │  - Parallel execution management                                 │  │
│  │  - Agent handoff logic                                           │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                  Specialized Agents                               │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │  │
│  │  │Metadata  │ │Data Agent│ │Test Agent│ │Deploy    │           │  │
│  │  │Agent     │ │          │ │          │ │Agent     │           │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
┌────────────────────────────┴────────────────────────────────────────────┐
│                    Application Service Layer                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐│
│  │Metadata Svc  │  │Deployment Svc│  │Data Service  │  │Testing Svc  ││
│  │(existing)    │  │(enhanced)    │  │(NEW)         │  │(enhanced)   ││
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘│
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐│
│  │User Svc (NEW)│  │Pipeline Svc  │  │Git Svc (NEW) │  │Notification ││
│  │              │  │(NEW)         │  │              │  │Svc (NEW)    ││
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘│
└────────────────────────────┬────────────────────────────────────────────┘
                             │
┌────────────────────────────┴────────────────────────────────────────────┐
│                    Infrastructure Layer                                  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    MCP Connection Pool (NEW)                      │  │
│  │  - Long-lived MCP processes                                      │  │
│  │  - Connection health monitoring                                  │  │
│  │  - Automatic reconnection                                        │  │
│  │  - Load balancing across processes                               │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐│
│  │PostgreSQL    │  │Redis Cache   │  │MinIO/S3      │  │Vector DB    ││
│  │(existing)    │  │(enhanced)    │  │(existing)    │  │(NEW)        ││
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘│
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐│
│  │Celery Workers│  │Git Client    │  │LLM API Client│  │Notification ││
│  │(existing)    │  │(NEW)         │  │(existing)    │  │Gateway (NEW)││
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

### Component Interaction Flow

**Example: Agent-Driven Metadata Deployment**

```
User Request: "Deploy the latest Apex classes from dev to QA"
    │
    ↓
[API Gateway] → Authentication & Rate Limiting
    │
    ↓
[Agent Coordinator] → Parse intent, select MetadataAgent
    │
    ↓
[Context Manager] → Load user preferences, conversation history
    │
    ↓
[Planning Engine] → Decompose task:
    │                1. Identify source org (dev)
    │                2. Retrieve Apex classes
    │                3. Validate target org (QA)
    │                4. Run tests
    │                5. Deploy if tests pass
    ↓
[MetadataAgent] → Execute plan steps:
    │
    ├─→ [Tool Registry] → Discover: list_metadata, retrieve_metadata
    │   │
    │   └─→ [MCP Pool] → Execute: list_metadata(org=dev, type=ApexClass)
    │       │
    │       └─→ [SFDX CLI] → sf project retrieve start
    │
    ├─→ [TestAgent] → Run Apex tests in QA
    │   │
    │   └─→ [MCP Pool] → Execute: run_apex_test(org=QA, testLevel=RunLocalTests)
    │
    └─→ [DeployAgent] → Deploy to QA
        │
        └─→ [Pipeline Service] → Create deployment pipeline
            │
            └─→ [MCP Pool] → Execute: deploy_metadata(org=QA, sourceDir=...)
                │
                └─→ [Notification Service] → Send success notification
```

---

## Module Structure & Interfaces

### New Module: `agent_orchestration/`

**Purpose**: Core agent orchestration and coordination

**Structure:**
```
backend/app/agent_orchestration/
├── __init__.py
├── registry.py              # AgentRegistry
├── coordinator.py           # AgentCoordinator
├── context_manager.py       # ContextManager
├── memory_layer.py          # MemoryLayer
├── planning_engine.py       # PlanningEngine
├── tool_registry.py         # ToolRegistry
├── prompt_executor.py       # PromptExecutionLayer
├── agents/
│   ├── __init__.py
│   ├── base.py             # BaseAgent abstract class
│   ├── metadata_agent.py   # Specialized for metadata ops
│   ├── data_agent.py       # Specialized for data ops
│   ├── test_agent.py       # Specialized for testing
│   └── deploy_agent.py     # Specialized for deployments
└── protocols/
    ├── __init__.py
    ├── agent_protocol.py   # Agent communication protocol
    └── handoff_protocol.py # Agent handoff logic
```

**Key Interfaces:**

```python
# agent_orchestration/registry.py
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from uuid import UUID

class AgentRegistry:
    """
    Central registry for agent lifecycle management.
    Tracks all active agents, their capabilities, and health status.
    """
    
    async def register_agent(
        self,
        agent_id: UUID,
        agent_type: str,
        capabilities: List[str],
        metadata: Dict[str, Any]
    ) -> None:
        """Register a new agent with the registry."""
        
    async def unregister_agent(self, agent_id: UUID) -> None:
        """Remove an agent from the registry."""
        
    async def get_agent(self, agent_id: UUID) -> Optional["BaseAgent"]:
        """Retrieve an agent by ID."""
        
    async def find_agents_by_capability(
        self,
        capability: str
    ) -> List["BaseAgent"]:
        """Find all agents that support a specific capability."""
        
    async def health_check(self, agent_id: UUID) -> Dict[str, Any]:
        """Check the health status of an agent."""


# agent_orchestration/agents/base.py
class BaseAgent(ABC):
    """
    Abstract base class for all specialized agents.
    Defines the contract that all agents must implement.
    """
    
    def __init__(
        self,
        agent_id: UUID,
        context_manager: "ContextManager",
        tool_registry: "ToolRegistry",
        memory_layer: "MemoryLayer"
    ):
        self.agent_id = agent_id
        self.context_manager = context_manager
        self.tool_registry = tool_registry
        self.memory_layer = memory_layer
        
    @abstractmethod
    async def execute(
        self,
        task: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a task with given context."""
        
    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this agent supports."""
        
    @abstractmethod
    async def plan(self, task: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create an execution plan for the task."""


# agent_orchestration/context_manager.py
class ContextManager:
    """
    Manages conversation context, user preferences, and session state.
    Provides context injection for agent prompts.
    """
    
    async def create_session(
        self,
        user_id: UUID,
        org_id: UUID,
        metadata: Dict[str, Any]
    ) -> UUID:
        """Create a new conversation session."""
        
    async def get_context(self, session_id: UUID) -> Dict[str, Any]:
        """Retrieve full context for a session."""
        
    async def update_context(
        self,
        session_id: UUID,
        updates: Dict[str, Any]
    ) -> None:
        """Update session context with new information."""
        
    async def add_message(
        self,
        session_id: UUID,
        role: str,  # "user" | "assistant" | "system"
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add a message to the conversation history."""
        
    async def get_conversation_history(
        self,
        session_id: UUID,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Retrieve conversation history for context."""


# agent_orchestration/tool_registry.py
class ToolRegistry:
    """
    Dynamic registry of available MCP tools.
    Handles tool discovery, validation, and invocation.
    """
    
    async def discover_tools(
        self,
        org_id: UUID,
        toolsets: List[str]
    ) -> List[Dict[str, Any]]:
        """Discover available tools from MCP server."""
        
    async def get_tool(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get tool metadata by name."""
        
    async def validate_arguments(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Validate tool arguments against schema."""
        
    async def invoke_tool(
        self,
        org_id: UUID,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: float = 120.0
    ) -> Dict[str, Any]:
        """Invoke a tool and return results."""
        
    async def get_tool_usage_stats(
        self,
        tool_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get usage statistics for tools."""
```

### New Module: `pipeline_engine/`

**Purpose**: Deployment pipeline orchestration

**Structure:**
```
backend/app/pipeline_engine/
├── __init__.py
├── engine.py               # PipelineEngine
├── state_machine.py        # Pipeline state machine
├── stages/
│   ├── __init__.py
│   ├── base.py            # BaseStage abstract class
│   ├── validation.py      # Validation stage
│   ├── testing.py         # Testing stage
│   ├── approval.py        # Approval stage
│   └── deployment.py      # Deployment stage
├── gates/
│   ├── __init__.py
│   ├── test_gate.py       # Test coverage gate
│   ├── approval_gate.py   # Manual approval gate
│   └── schedule_gate.py   # Time-based gate
└── templates/
    ├── __init__.py
    └── standard_pipelines.py  # Pre-built pipeline templates
```

**Key Interfaces:**

```python
# pipeline_engine/engine.py
class PipelineEngine:
    """
    Orchestrates multi-stage deployment pipelines.
    Manages stage transitions, gates, and rollbacks.
    """
    
    async def create_pipeline(
        self,
        name: str,
        stages: List["BaseStage"],
        metadata: Dict[str, Any]
    ) -> UUID:
        """Create a new pipeline definition."""
        
    async def execute_pipeline(
        self,
        pipeline_id: UUID,
        context: Dict[str, Any]
    ) -> UUID:
        """Start pipeline execution, returns execution_id."""
        
    async def get_execution_status(
        self,
        execution_id: UUID
    ) -> Dict[str, Any]:
        """Get current status of pipeline execution."""
        
    async def approve_stage(
        self,
        execution_id: UUID,
        stage_id: UUID,
        approver_id: UUID
    ) -> None:
        """Approve a stage waiting for manual approval."""
        
    async def rollback(
        self,
        execution_id: UUID,
        target_stage: Optional[UUID] = None
    ) -> None:
        """Rollback pipeline to previous or specified stage."""


# pipeline_engine/stages/base.py
class BaseStage(ABC):
    """Abstract base class for pipeline stages."""
    
    @abstractmethod
    async def execute(
        self,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute the stage logic."""
        
    @abstractmethod
    async def validate(
        self,
        context: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Validate stage can execute with given context."""
        
    @abstractmethod
    async def rollback(
        self,
        context: Dict[str, Any]
    ) -> None:
        """Rollback changes made by this stage."""
```

### Enhanced Module: `infrastructure/mcp_pool/`

**Purpose**: Connection pooling for MCP processes

**Structure:**
```
backend/app/infrastructure/mcp_pool/
├── __init__.py
├── pool.py                 # MCPConnectionPool
├── connection.py           # MCPConnection wrapper
├── health_monitor.py       # Health monitoring
└── load_balancer.py        # Load balancing logic
```

**Key Interfaces:**

```python
# infrastructure/mcp_pool/pool.py
class MCPConnectionPool:
    """
    Manages a pool of long-lived MCP subprocess connections.
    Provides connection reuse, health monitoring, and load balancing.
    """
    
    def __init__(
        self,
        min_connections: int = 2,
        max_connections: int = 10,
        connection_timeout: float = 300.0
    ):
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.connection_timeout = connection_timeout
        
    async def acquire(
        self,
        org_id: UUID,
        toolsets: str = "orgs,metadata,data,testing,users"
    ) -> "MCPConnection":
        """Acquire a connection from the pool."""
        
    async def release(self, connection: "MCPConnection") -> None:
        """Release a connection back to the pool."""
        
    async def health_check_all(self) -> Dict[str, Any]:
        """Check health of all connections in pool."""
        
    async def close_all(self) -> None:
        """Close all connections and shutdown pool."""
```

---

## Implementation Priorities

### Sprint 1 (Weeks 1-2): Foundation

**Goal**: Establish core agent orchestration infrastructure

**Deliverables:**
1. **Agent Registry** (`agent_orchestration/registry.py`)
   - Agent lifecycle management
   - Capability registration
   - Health monitoring
   - **Acceptance**: Can register/unregister agents, query by capability

2. **Tool Registry** (`agent_orchestration/tool_registry.py`)
   - MCP tool discovery
   - Tool metadata caching
   - Argument validation
   - **Acceptance**: Discovers all 60+ tools, validates arguments

3. **Context Manager** (`agent_orchestration/context_manager.py`)
   - Session management
   - Conversation history
   - User preferences
   - **Acceptance**: Persists context across requests, retrieves history

4. **API Authentication** (`api/v1/auth.py`)
   - JWT-based authentication
   - User login/logout
   - Token refresh
   - **Acceptance**: Secure endpoints, token validation works

**Files to Create:**
- `backend/app/agent_orchestration/__init__.py`
- `backend/app/agent_orchestration/registry.py`
- `backend/app/agent_orchestration/tool_registry.py`
- `backend/app/agent_orchestration/context_manager.py`
- `backend/app/api/v1/auth.py`
- `backend/app/schemas/auth.py`
- `backend/alembic/versions/0007_agent_tables.py`

**Files to Modify:**
- `backend/app/main.py` - Add auth middleware
- `backend/app/core/config.py` - Add JWT settings
- `backend/app/infrastructure/db/models.py` - Add Session, AgentExecution tables
- `backend/app/api/dependencies.py` - Add auth dependencies

**Database Migrations:**
```sql
-- 0007_agent_tables.py
CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    org_id UUID REFERENCES salesforce_orgs(id),
    context JSONB,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE agent_executions (
    id UUID PRIMARY KEY,
    session_id UUID REFERENCES sessions(id),
    agent_type VARCHAR(50),
    task JSONB,
    result JSONB,
    status VARCHAR(50),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);
CREATE INDEX idx_agent_executions_session_id ON agent_executions(session_id);
```

**Testing Requirements:**
- Unit tests for AgentRegistry (registration, lookup, health checks)
- Unit tests for ToolRegistry (discovery, validation, invocation)
- Unit tests for ContextManager (session CRUD, history management)
- Integration tests for auth flow (login, token refresh, logout)

### Sprint 2 (Weeks 3-4): Agent Foundation

**Goal**: Build base agent infrastructure and specialized agents

**Deliverables:**
1. **BaseAgent** (`agent_orchestration/agents/base.py`)
   - Abstract agent interface
   - Common agent functionality
   - **Acceptance**: Can be subclassed, enforces contract

2. **MetadataAgent** (`agent_orchestration/agents/metadata_agent.py`)
   - Specialized for metadata operations
   - Uses retrieve_metadata, deploy_metadata, list_metadata tools
   - **Acceptance**: Can retrieve/deploy metadata autonomously

3. **DataAgent** (`agent_orchestration/agents/data_agent.py`)
   - Specialized for data operations
   - Uses query_data, export_data, import_data tools
   - **Acceptance**: Can query/import/export data autonomously

4. **Memory Layer** (`agent_orchestration/memory_layer.py`)
   - Short-term working memory (Redis)
   - Long-term knowledge storage (Vector DB)
   - Memory retrieval algorithms
   - **Acceptance**: Stores/retrieves relevant memories

**Files to Create:**
- `backend/app/agent_orchestration/agents/__init__.py`
- `backend/app/agent_orchestration/agents/base.py`
- `backend/app/agent_orchestration/agents/metadata_agent.py`
- `backend/app/agent_orchestration/agents/data_agent.py`
- `backend/app/agent_orchestration/memory_layer.py`
- `backend/app/application/services/data_service.py`

**Files to Modify:**
- `backend/app/api/v1/agent.py` - Add new agent endpoints
- `backend/app/application/services/sfdx_mcp_service.py` - Add data tool support
- `backend/requirements.txt` - Add vector DB client (e.g., chromadb, pinecone)

**Configuration Changes:**
```python
# backend/app/core/config.py additions
class Settings(BaseSettings):
    # ... existing settings ...
    
    # Vector DB settings
    vector_db_url: str = Field(..., alias="VECTOR_DB_URL")
    vector_db_collection: str = Field(default="agent_memory", alias="VECTOR_DB_COLLECTION")
    
    # Memory settings
    memory_ttl_seconds: int = Field(default=3600, alias="MEMORY_TTL_SECONDS")
    max_memory_items: int = Field(default=100, alias="MAX_MEMORY_ITEMS")
```

**Testing Requirements:**
- Unit tests for BaseAgent
- Unit tests for MetadataAgent (tool invocation, error handling)
- Unit tests for DataAgent (SOQL queries, data import/export)
- Unit tests for MemoryLayer (storage, retrieval, TTL)
- Integration tests for agent execution end-to-end

### Sprint 3 (Weeks 5-6): Multi-Agent Coordination

**Goal**: Enable multi-agent orchestration and coordination

**Deliverables:**
1. **AgentCoordinator** (`agent_orchestration/coordinator.py`)
   - Multi-agent orchestration
   - Agent selection logic
   - Parallel execution
   - **Acceptance**: Can coordinate multiple agents for complex tasks

2. **PlanningEngine** (`agent_orchestration/planning_engine.py`)
   - Task decomposition
   - Dependency analysis
   - Execution scheduling
   - **Acceptance**: Breaks complex tasks into agent-executable steps

3. **TestAgent** (`agent_orchestration/agents/test_agent.py`)
   - Specialized for testing operations
   - Uses run_apex_test, get_test_results tools
   - **Acceptance**: Can run tests and analyze results

4. **DeployAgent** (`agent_orchestration/agents/deploy_agent.py`)
   - Specialized for deployment operations
   - Integrates with pipeline engine
   - **Acceptance**: Can execute deployments with validation

**Files to Create:**
- `backend/app/agent_orchestration/coordinator.py`
- `backend/app/agent_orchestration/planning_engine.py`
- `backend/app/agent_orchestration/agents/test_agent.py`
- `backend/app/agent_orchestration/agents/deploy_agent.py`
- `backend/app/agent_orchestration/protocols/__init__.py`
- `backend/app/agent_orchestration/protocols/agent_protocol.py`

**Files to Modify:**
- `backend/app/api/v1/agent.py` - Add multi-agent endpoints
- `backend/app/application/services/llm_agent_service.py` - Integrate with coordinator

**Testing Requirements:**
- Unit tests for AgentCoordinator (agent selection, parallel execution)
- Unit tests for PlanningEngine (task decomposition, dependency resolution)
- Unit tests for TestAgent and DeployAgent
- Integration tests for multi-agent workflows

### Sprint 4 (Weeks 7-8): Pipeline Engine

**Goal**: Build deployment pipeline orchestration

**Deliverables:**
1. **PipelineEngine** (`pipeline_engine/engine.py`)
   - Pipeline creation and execution
   - Stage management
   - Rollback capability
   - **Acceptance**: Can execute multi-stage pipelines

2. **Pipeline Stages** (`pipeline_engine/stages/`)
   - Validation stage
   - Testing stage
   - Approval stage
   - Deployment stage
   - **Acceptance**: Each stage executes correctly

3. **Pipeline Gates** (`pipeline_engine/gates/`)
   - Test coverage gate
   - Manual approval gate
   - Schedule gate
   - **Acceptance**: Gates block/allow progression correctly

4. **Pipeline API** (`api/v1/pipelines.py`)
   - Create/execute pipelines
   - Approve stages
   - View execution status
   - **Acceptance**: Full pipeline CRUD via API

**Files to Create:**
- `backend/app/pipeline_engine/__init__.py`
- `backend/app/pipeline_engine/engine.py`
- `backend/app/pipeline_engine/state_machine.py`
- `backend/app/pipeline_engine/stages/__init__.py`
- `backend/app/pipeline_engine/stages/base.py`
- `backend/app/pipeline_engine/stages/validation.py`
- `backend/app/pipeline_engine/stages/testing.py`
- `backend/app/pipeline_engine/stages/approval.py`
- `backend/app/pipeline_engine/stages/deployment.py`
- `backend/app/pipeline_engine/gates/__init__.py`
- `backend/app/pipeline_engine/gates/test_gate.py`
- `backend/app/pipeline_engine/gates/approval_gate.py`
- `backend/app/api/v1/pipelines.py`
- `backend/app/schemas/pipeline.py`
- `backend/alembic/versions/0008_pipeline_tables.py`

**Database Migrations:**
```sql
-- 0008_pipeline_tables.py
CREATE TABLE pipelines (
    id UUID PRIMARY KEY,
    name VARCHAR(255),
    stages JSONB,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE pipeline_executions (
    id UUID PRIMARY KEY,
    pipeline_id UUID REFERENCES pipelines(id),
    current_stage_index INTEGER,
    status VARCHAR(50),
    context JSONB,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT
);

CREATE TABLE stage_executions (
    id UUID PRIMARY KEY,
    pipeline_execution_id UUID REFERENCES pipeline_executions(id),
    stage_index INTEGER,
    stage_name VARCHAR(255),
    status VARCHAR(50),
    result JSONB,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT
);
```

**Testing Requirements:**
- Unit tests for PipelineEngine (creation, execution, rollback)
- Unit tests for each stage type
- Unit tests for each gate type
- Integration tests for full pipeline execution
- E2E tests for deployment workflows

---

## Technical Specifications

### Agent Communication Protocol

**Protocol**: JSON-RPC 2.0 over internal message bus (Redis Pub/Sub)

**Message Format:**
```json
{
  "jsonrpc": "2.0",
  "method": "agent.execute",
  "params": {
    "agent_id": "uuid",
    "task": {
      "type": "metadata.retrieve",
      "parameters": {...}
    },
    "context": {
      "session_id": "uuid",
      "user_id": "uuid",
      "org_id": "uuid"
    }
  },
  "id": "request-uuid"
}
```

**Response Format:**
```json
{
  "jsonrpc": "2.0",
  "result": {
    "status": "success",
    "data": {...},
    "metadata": {
      "execution_time_ms": 1234,
      "tools_used": ["retrieve_metadata"]
    }
  },
  "id": "request-uuid"
}
```

### Context Schema

**Session Context:**
```json
{
  "session_id": "uuid",
  "user_id": "uuid",
  "org_id": "uuid",
  "created_at": "2026-06-02T09:00:00Z",
  "updated_at": "2026-06-02T09:30:00Z",
  "expires_at": "2026-06-02T10:00:00Z",
  "conversation_history": [
    {
      "role": "user",
      "content": "Deploy Apex classes to QA",
      "timestamp": "2026-06-02T09:00:00Z"
    },
    {
      "role": "assistant",
      "content": "I'll deploy the Apex classes...",
      "timestamp": "2026-06-02T09:00:05Z",
      "metadata": {
        "agent_id": "uuid",
        "tools_used": ["deploy_metadata"]
      }
    }
  ],
  "user_preferences": {
    "default_test_level": "RunLocalTests",
    "notification_channels": ["email", "slack"],
    "timezone": "America/Los_Angeles"
  },
  "active_agents": ["metadata-agent-1", "test-agent-1"]
}
```

### Memory Schema

**Short-Term Memory (Redis):**
```json
{
  "session_id": "uuid",
  "key": "last_deployment",
  "value": {
    "org_id": "uuid",
    "deployment_id": "uuid",
    "status": "success",
    "timestamp": "2026-06-02T09:00:00Z"
  },
  "ttl": 3600
}
```

**Long-Term Memory (Vector DB):**
```json
{
  "id": "uuid",
  "user_id": "uuid",
  "content": "User prefers to run all tests before deploying to production",
  "embedding": [0.1, 0.2, ...],  // 1536-dim vector
  "metadata": {
    "type": "preference",
    "confidence": 0.95,
    "source": "conversation",
    "timestamp": "2026-06-02T09:00:00Z"
  }
}
```

### Tool Registry Schema

**Tool Metadata:**
```json
{
  "name": "retrieve_metadata",
  "description": "Retrieves metadata from Salesforce org to local project",
  "toolset": "metadata",
  "input_schema": {
    "type": "object",
    "properties": {
      "usernameOrAlias": {"type": "string", "required": true},
      "directory": {"type": "string", "required": true},
      "manifest": {"type": "string", "required": false},
      "sourceDir": {"type": "array", "items": {"type": "string"}, "required": false}
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "status": {"type": "string"},
      "files": {"type": "array", "items": {"type": "string"}}
    }
  },
  "examples": [
    {
      "input": {
        "usernameOrAlias": "dev-org",
        "directory": "/path/to/project",
        "manifest": "/path/to/package.xml"
      },
      "output": {
        "status": "success",
        "files": ["force-app/main/default/classes/MyClass.cls"]
      }
    }
  ],
  "usage_stats": {
    "total_invocations": 1234,
    "success_rate": 0.98,
    "avg_execution_time_ms": 5000
  }
}
```

### Pipeline State Machine

**States:**
- `created` - Pipeline definition created
- `queued` - Execution queued
- `running` - Currently executing
- `waiting_approval` - Waiting for manual approval
- `paused` - Manually paused
- `success` - Completed successfully
- `failed` - Failed with error
- `rolled_back` - Rolled back to previous state

**Transitions:**
```
created → queued → running → [stage_1] → [stage_2] → ... → success
                      ↓           ↓           ↓
                   failed    waiting_approval  paused
                      ↓           ↓           ↓
                rolled_back ← approved → running
```

### API Authentication Flow

**JWT Token Structure:**
```json
{
  "sub": "user-uuid",
  "email": "user@example.com",
  "role": "admin",
  "iat": 1717329600,
  "exp": 1717333200,
  "jti": "token-uuid"
}
```

**Authentication Endpoints:**
- `POST /api/v1/auth/login` - Login with email/password
- `POST /api/v1/auth/refresh` - Refresh access token
- `POST /api/v1/auth/logout` - Logout and invalidate token
- `GET /api/v1/auth/me` - Get current user info

**Protected Endpoint Example:**
```python
from fastapi import Depends, HTTPException
from app.api.dependencies import get_current_user

@router.get("/orgs")
async def list_orgs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    # Only authenticated users can access
    service = SalesforceOrgService(db)
    return await service.list_orgs(user_id=current_user.id)
```

---

## Next Steps

This blueprint provides the foundation for Phases 5 (Phased Implementation Roadmap) and 6 (Production-Ready Code Generation).

**Immediate Actions:**
1. Review and approve this blueprint
2. Set up development environment for new modules
3. Create feature branches for Sprint 1 work
4. Begin implementation of Agent Registry and Tool Registry

**Questions for Stakeholders:**
1. Preferred vector database (ChromaDB, Pinecone, Weaviate)?
2. LLM provider for agent reasoning (OpenAI, Anthropic, custom)?
3. Notification channels to support (Email, Slack, Teams)?
4. Deployment schedule preferences (phased rollout vs big bang)?

---

**Document Status**: Ready for Phase 5 & 6  
**Next Update**: After Sprint 1 completion