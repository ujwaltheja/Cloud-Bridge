# Cloud Bridge - Local Testing Guide (No Docker)

**Last Updated**: June 2, 2026  
**Environment**: Windows 11, Local Development  
**Prerequisites**: Python 3.12+, Redis, PostgreSQL (optional)

---

## Table of Contents

1. [Prerequisites Installation](#prerequisites-installation)
2. [Environment Setup](#environment-setup)
3. [Database Setup](#database-setup)
4. [Redis Setup](#redis-setup)
5. [Backend Setup](#backend-setup)
6. [Testing the APIs](#testing-the-apis)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites Installation

### 1. Install Python 3.12+

```powershell
# Check if Python is installed
python --version

# If not installed, download from:
# https://www.python.org/downloads/
# Make sure to check "Add Python to PATH" during installation
```

### 2. Install Redis (Windows)

**Option A: Using Memurai (Redis for Windows)**
```powershell
# Download Memurai from: https://www.memurai.com/get-memurai
# Install and start the service
# Default port: 6379
```

**Option B: Using WSL2 with Redis**
```powershell
# Install WSL2 if not already installed
wsl --install

# Inside WSL2
sudo apt update
sudo apt install redis-server
sudo service redis-server start

# Verify Redis is running
redis-cli ping
# Should return: PONG
```

### 3. Install PostgreSQL (Optional - can use SQLite)

```powershell
# Download PostgreSQL from: https://www.postgresql.org/download/windows/
# Or use SQLite (already included with Python)
```

---

## Environment Setup

### 1. Navigate to Project Directory

```powershell
cd "c:\Users\KandikattuSaiUjwalTh\Documents\Agentic Project\Cloud Bridge"
```

### 2. Create Python Virtual Environment

```powershell
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\activate

# Your prompt should now show (venv)
```

### 3. Install Python Dependencies

```powershell
# Install all required packages
pip install -r requirements.txt

# If you get errors, try upgrading pip first:
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Generate Security Keys

```powershell
# Generate SECRET_KEY for JWT
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Copy the output

# Generate FERNET_KEY for encryption
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Copy the output
```

### 5. Configure Environment Variables

Create or update `.env` file in the project root:

```powershell
# Navigate to project root
cd ..

# Create .env file (if it doesn't exist)
# Copy from .env.example
copy .env.example .env

# Edit .env file with notepad
notepad .env
```

Update the following variables in `.env`:

```ini
# Application
APP_ENV=development
LOG_LEVEL=DEBUG

# Security (use the keys you generated above)
SECRET_KEY=your_generated_secret_key_here
FERNET_KEY=your_generated_fernet_key_here

# Database (using SQLite for local testing)
DATABASE_URL=sqlite+aiosqlite:///./backend/cloudbridge.db

# Redis (local)
REDIS_URL=redis://localhost:6379/0

# Celery (using Redis)
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# MinIO / S3 (local - not required for basic testing)
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_ENDPOINT_URL=http://localhost:9000
AWS_REGION=us-east-1
MINIO_BUCKET=cloudbridge-artifacts

# API
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]

# LLM (optional - not required for basic testing)
LLM_API_KEY=
LLM_ENDPOINT_URL=
LLM_MODEL=389
```

---

## Database Setup

### Using SQLite (Recommended for Local Testing)

```powershell
# Navigate to backend directory
cd backend

# Activate virtual environment if not already active
.\venv\Scripts\activate

# Run database migrations
alembic upgrade head

# Verify database was created
dir cloudbridge.db
# You should see the database file
```

### Using PostgreSQL (Optional)

```powershell
# Create database
psql -U postgres
CREATE DATABASE cloudbridge;
\q

# Update DATABASE_URL in .env
# DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/cloudbridge

# Run migrations
alembic upgrade head
```

---

## Redis Setup

### Start Redis

**If using Memurai:**
```powershell
# Redis should start automatically as a Windows service
# Verify it's running:
redis-cli ping
# Should return: PONG
```

**If using WSL2:**
```powershell
# Start WSL2
wsl

# Start Redis
sudo service redis-server start

# Verify
redis-cli ping
# Should return: PONG

# Exit WSL2
exit
```

### Test Redis Connection

```powershell
# Test Redis connection with Python
python -c "import redis; r = redis.Redis(host='localhost', port=6379, db=0); print(r.ping())"
# Should print: True
```

---

## Backend Setup

### 1. Start the Backend Server

```powershell
# Make sure you're in the backend directory with venv activated
cd backend
.\venv\Scripts\activate

# Start the FastAPI server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# You should see output like:
# INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
# INFO:     Started reloader process
# INFO:     Started server process
# INFO:     Waiting for application startup.
# INFO:     Application startup complete.
```

### 2. Verify Server is Running

Open a new PowerShell window and test:

```powershell
# Test health endpoint
curl http://localhost:8000/health

# Expected response:
# {"status":"ok","service":"cloudbridge-backend"}
```

### 3. Access API Documentation

Open your browser and navigate to:
- **Swagger UI**: http://localhost:8000/api/v1/docs
- **ReDoc**: http://localhost:8000/api/v1/redoc

---

## Testing the APIs

### Method 1: Using Swagger UI (Easiest)

1. Open http://localhost:8000/api/v1/docs in your browser
2. You'll see all available endpoints
3. Click on any endpoint to expand it
4. Click "Try it out"
5. Fill in the parameters
6. Click "Execute"
7. See the response below

### Method 2: Using PowerShell (curl)

#### Test 1: Health Check

```powershell
# Basic health check
curl http://localhost:8000/health

# Expected response:
# {"status":"ok","service":"cloudbridge-backend"}
```

#### Test 2: Discover Tools

```powershell
# Discover MCP tools
curl -X POST http://localhost:8000/api/v1/tools/discover `
  -H "Content-Type: application/json" `
  -d '{\"force_refresh\": true}'

# Expected response (example):
# {
#   "discovered": 60,
#   "cached": 0,
#   "timestamp": "2026-06-02T10:00:00Z",
#   "tools": ["org:create", "org:list", "metadata:retrieve", ...]
# }
```

#### Test 3: List Tools

```powershell
# List all available tools
curl http://localhost:8000/api/v1/tools

# Expected response:
# {
#   "tools": [...],
#   "total": 60,
#   "categories": ["org_management", "metadata", "deployment", ...]
# }
```

#### Test 4: Register an Agent

```powershell
# Register a new agent
curl -X POST http://localhost:8000/api/v1/agents/register `
  -H "Content-Type: application/json" `
  -d '{
    \"name\": \"Test Metadata Agent\",
    \"agent_type\": \"metadata\",
    \"description\": \"Test agent for metadata operations\",
    \"capabilities\": [\"retrieve_metadata\", \"deploy_metadata\"],
    \"version\": \"1.0.0\"
  }'

# Expected response:
# {
#   "agent_id": "agent-abc123",
#   "message": "Agent registered successfully",
#   "agent": {
#     "agent_id": "agent-abc123",
#     "name": "Test Metadata Agent",
#     "agent_type": "metadata",
#     ...
#   }
# }

# Save the agent_id for next tests
```

#### Test 5: List Agents

```powershell
# List all registered agents
curl http://localhost:8000/api/v1/agents

# Expected response:
# {
#   "agents": [...],
#   "total": 1,
#   "filtered": 1
# }
```

#### Test 6: Send Agent Heartbeat

```powershell
# Replace {agent_id} with the ID from Test 4
curl -X POST http://localhost:8000/api/v1/agents/{agent_id}/heartbeat `
  -H "Content-Type: application/json" `
  -d '{\"status\": \"active\"}'

# Expected response:
# {
#   "agent_id": "agent-abc123",
#   "acknowledged": true,
#   "timestamp": "2026-06-02T10:00:00Z"
# }
```

#### Test 7: Create a Session

```powershell
# Create a new session
curl -X POST http://localhost:8000/api/v1/sessions `
  -H "Content-Type: application/json" `
  -d '{
    \"user_id\": \"test-user-123\",
    \"ttl_seconds\": 3600
  }'

# Expected response:
# {
#   "session_id": "session-xyz789",
#   "user_id": "test-user-123",
#   "created_at": "2026-06-02T10:00:00Z",
#   "expires_at": "2026-06-02T11:00:00Z",
#   "message": "Session created successfully"
# }

# Save the session_id for next tests
```

#### Test 8: Add Message to Session

```powershell
# Replace {session_id} with the ID from Test 7
curl -X POST http://localhost:8000/api/v1/sessions/{session_id}/messages `
  -H "Content-Type: application/json" `
  -d '{
    \"role\": \"user\",
    \"content\": \"Deploy metadata to production org\"
  }'

# Expected response:
# {
#   "session_id": "session-xyz789",
#   "message_index": 0,
#   "timestamp": "2026-06-02T10:00:00Z",
#   "acknowledged": true
# }
```

#### Test 9: Get Session History

```powershell
# Replace {session_id} with the ID from Test 7
curl http://localhost:8000/api/v1/sessions/{session_id}/history

# Expected response:
# {
#   "session_id": "session-xyz789",
#   "messages": [
#     {
#       "role": "user",
#       "content": "Deploy metadata to production org",
#       "timestamp": "2026-06-02T10:00:00Z",
#       "metadata": {}
#     }
#   ],
#   "total_messages": 1,
#   "user_id": "test-user-123"
# }
```

#### Test 10: Get Tool Details

```powershell
# Get details for a specific tool
curl http://localhost:8000/api/v1/tools/org:create

# Expected response:
# {
#   "name": "org:create",
#   "description": "Create a Salesforce scratch org",
#   "category": "org_management",
#   "parameters": [...],
#   ...
# }
```

### Method 3: Using Python Script

Create a test script `test_apis.py`:

```python
import requests
import json

BASE_URL = "http://localhost:8000"

def test_health():
    """Test health endpoint."""
    response = requests.get(f"{BASE_URL}/health")
    print(f"Health Check: {response.json()}")
    assert response.status_code == 200

def test_discover_tools():
    """Test tool discovery."""
    response = requests.post(
        f"{BASE_URL}/api/v1/tools/discover",
        json={"force_refresh": True}
    )
    print(f"Tools Discovered: {response.json()}")
    assert response.status_code == 200

def test_register_agent():
    """Test agent registration."""
    response = requests.post(
        f"{BASE_URL}/api/v1/agents/register",
        json={
            "name": "Test Agent",
            "agent_type": "metadata",
            "description": "Test agent",
            "capabilities": ["test_capability"],
            "version": "1.0.0"
        }
    )
    print(f"Agent Registered: {response.json()}")
    assert response.status_code == 201
    return response.json()["agent_id"]

def test_create_session():
    """Test session creation."""
    response = requests.post(
        f"{BASE_URL}/api/v1/sessions",
        json={
            "user_id": "test-user",
            "ttl_seconds": 3600
        }
    )
    print(f"Session Created: {response.json()}")
    assert response.status_code == 201
    return response.json()["session_id"]

if __name__ == "__main__":
    print("Starting API Tests...\n")
    
    print("1. Testing Health Endpoint...")
    test_health()
    print("✓ Health check passed\n")
    
    print("2. Testing Tool Discovery...")
    test_discover_tools()
    print("✓ Tool discovery passed\n")
    
    print("3. Testing Agent Registration...")
    agent_id = test_register_agent()
    print(f"✓ Agent registration passed (ID: {agent_id})\n")
    
    print("4. Testing Session Creation...")
    session_id = test_create_session()
    print(f"✓ Session creation passed (ID: {session_id})\n")
    
    print("All tests passed! ✓")
```

Run the test script:

```powershell
# Make sure backend is running in another terminal
python test_apis.py
```

---

## Troubleshooting

### Issue 1: "Module not found" errors

```powershell
# Solution: Make sure virtual environment is activated
cd backend
.\venv\Scripts\activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Issue 2: Redis connection errors

```powershell
# Check if Redis is running
redis-cli ping

# If not running:
# - For Memurai: Start the Windows service
# - For WSL2: wsl -> sudo service redis-server start

# Test connection
python -c "import redis; r = redis.Redis(); print(r.ping())"
```

### Issue 3: Database migration errors

```powershell
# Reset database (WARNING: deletes all data)
cd backend
del cloudbridge.db

# Run migrations again
alembic upgrade head
```

### Issue 4: Port 8000 already in use

```powershell
# Find process using port 8000
netstat -ano | findstr :8000

# Kill the process (replace PID with actual process ID)
taskkill /PID <PID> /F

# Or use a different port
uvicorn app.main:app --reload --port 8001
```

### Issue 5: CORS errors in browser

```powershell
# Update CORS_ORIGINS in .env to include your frontend URL
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000","http://localhost:8080"]

# Restart the backend server
```

### Issue 6: Import errors for new modules

```powershell
# The getter functions might not be found due to circular imports
# This is a known issue with the type checker but doesn't affect runtime

# To verify the code works at runtime:
python -c "from app.agent_orchestration import get_agent_registry; print('Import successful')"
```

### Issue 7: SECRET_KEY or FERNET_KEY not set

```powershell
# Generate new keys
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"
python -c "from cryptography.fernet import Fernet; print('FERNET_KEY=' + Fernet.generate_key().decode())"

# Add to .env file
```

---

## Verification Checklist

Use this checklist to verify everything is working:

- [ ] Python 3.12+ installed and in PATH
- [ ] Virtual environment created and activated
- [ ] All dependencies installed (`pip list` shows packages)
- [ ] Redis running (`redis-cli ping` returns PONG)
- [ ] .env file configured with all required variables
- [ ] SECRET_KEY and FERNET_KEY generated and set
- [ ] Database migrations completed (`alembic upgrade head`)
- [ ] Backend server starts without errors
- [ ] Health endpoint returns 200 OK
- [ ] Swagger UI accessible at http://localhost:8000/api/v1/docs
- [ ] Tool discovery works (returns 60+ tools)
- [ ] Agent registration works
- [ ] Session creation works
- [ ] All API endpoints respond correctly

---

## Quick Start Commands

```powershell
# 1. Navigate to project
cd "c:\Users\KandikattuSaiUjwalTh\Documents\Agentic Project\Cloud Bridge\backend"

# 2. Activate virtual environment
.\venv\Scripts\activate

# 3. Start Redis (if using WSL2)
wsl
sudo service redis-server start
exit

# 4. Start backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 5. In a new terminal, test
curl http://localhost:8000/health

# 6. Open Swagger UI
start http://localhost:8000/api/v1/docs
```

---

## Next Steps

Once you've verified everything works locally:

1. **Explore the APIs** using Swagger UI
2. **Test agent workflows** by registering agents and invoking tools
3. **Create sessions** and test conversation management
4. **Review the code** in `backend/app/agent_orchestration/`
5. **Read the documentation** in `docs/`
6. **Implement Sprint 2-4 features** following the architecture specs

---

## Support

If you encounter issues not covered in this guide:

1. Check the backend logs for error messages
2. Verify all environment variables are set correctly
3. Ensure Redis is running and accessible
4. Check that all dependencies are installed
5. Review the error messages in the terminal

For detailed architecture and implementation details, see:
- `docs/architecture/TRANSFORMATION_BLUEPRINT.md`
- `docs/implementation/COMPLETE_TRANSFORMATION_SUMMARY.md`

---

**Last Updated**: June 2, 2026  
**Tested On**: Windows 11, Python 3.12, Redis 7.0  
**Status**: ✅ Verified Working