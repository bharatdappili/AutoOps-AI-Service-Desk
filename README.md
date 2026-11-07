# AutoOps AI Service Desk - Hackathon Workflow 1

An enterprise IT operations platform built on Switch with 6 specialized agents, PostgreSQL backend, and Jenkins integration.

## 🚀 Quick Start

```bash
# Navigate to project directory
cd /Users/dappilibharatkuamrreddy/Documents/omniroute_test

# Install dependencies
pip install -r requirements.txt

# Run Workflow 1 (Access Grant)
python workflows/workflow1.py
```

## 📂 Project Structure

```
omniroute_test/
├── hack.txt                           # Original hackathon requirements
├── schema.sql                         # PostgreSQL database schema
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
│
├── jenkins/
│   └── client.py                     # Jenkins API client
│
├── databases/
│   └── postgresdb.py                 # PostgreSQL connection wrapper
│
└── workflows/
    └── workflow1.py                  # Access Grant Workflow (main demo)
```

## 🏗️ Architecture

### Backend Systems

1. **PostgreSQL** - User management and audit trails
2. **Jenkins Container** - Build system integration
3. **Mock Identity Service** - Simulated Azure AD/LDAP (FastAPI)

### Agent Architecture (6 Agents)

```
User Request
    │
    ▼
┌──────────────────────────────────┐
│ 1. ServiceDeskAgent (Entry Point)  │
│    - Classifies incoming tickets   │
│    - Validates JSON payload        │
│    - Determines severity           │
└───────────────┬──────────────────┘
                │
                ▼
┌──────────────────────────────────┐
│ 2. WorkflowOrchestrator           │
│    - Routes to appropriate path   │
│    - Coordinates agents           │
│    - Tracks workflow progress      │
└───────────────┬──────────────────┘
                │
                ▼
┌──────────────────────────────────┐
│ 3. AccessGovernanceAgent (Policy)  │
│    - Checks RBAC compliance        │
│    - Calculates risk level         │
│    - Determines approval needed   │
└───────────────┬──────────────────┘
                │
                ▼
┌──────────────────────────────────┐
│ 4. ApprovalAgent (Approval Flow)  │
│    - Requests manager approval     │
│    - Waits for response            │
│    - Records approval              │
└───────────────┬──────────────────┘
                │
                ▼
┌──────────────────────────────────┐
│ 5. IdentityOperationsAgent        │
│    (ONLY privileged agent)         │
│    - Creates database users        │
│    - Syncs to Jenkins              │
│    - Writes audit logs             │
└───────────────┬──────────────────┘
                │
                ▼
┌──────────────────────────────────┐
│ 6. ValidationAgent (Verification) │
│    - Verifies access granted       │
│    - Confirms compliance           │
│    - Generates audit trail         │
└──────────────────────────────────┘
```

## 📊 Database Schema

### Key Tables

- `users` - User accounts (replaces Azure AD)
- `groups` - RBAC groups (jenkins_admin, dev_ops_team, etc.)
- `user_groups` - User-to-group membership
- `access_requests` - Access request tracking
- `audit_logs` - Complete audit trail (compliance)

### Sample Data

```sql
-- Default users
INSERT INTO users (username, email, name, role) VALUES
('bharat', 'bharat@company.com', 'Bharat Kumar', 'end_user'),
('manager_bharat', 'manager@company.com', 'Manager Bharat', 'manager'),
('admin_user', 'admin@company.com', 'System Admin', 'admin');
```

## 🤖 Jenkins Integration

### Features

1. **User Synchronization** - Create users in Jenkins via API
2. **Group Management** - Add users to Jenkins groups
3. **Job Operations** - List jobs, get job details
4. **Shell Commands** - Run script console commands

### Connection Configuration

```python
# jenkins/client.py
JENKINS_CONFIG = {
    'base_url': 'http://localhost:8080',  # Your Jenkins URL
    'username': 'admin',                  # Jenkins admin
    'password': 'your_password'           # Jenkins password
}
```

### Important Notes

⚠️ **Security Warning**: For hackathon demo, we use script console for user creation. In production:
- Use Jenkins Credentials API
- Hash passwords properly
- Enable anti-CSRF
- Limit script console access

## 🎭 Demo Second: Access Grant Flow

### Input Request

```json
{
  "ticket_id": "REQ-1001",
  "type": "access_request",
  "requested_by": "bharat",
  "resource": "jenkins_admin",
  "reason": "Production deployment support"
}
```

### Workflow Steps

#### Step 1: Service Desk Agent
- Validates JSON payload
- Classifies as `access_request`
- Determines severity: P2 (normal access)
- Routes to access_path workflow

#### Step 2: Workflow Orchestrator
- Executes access_path
- Calls AccessGovernanceAgent (pre-check passed)
- Updates ticket to `pending_approval`

#### Step 3: Access Governance Agent
- Checks current RBAC groups
- Risk assessment: LOW (end_user requesting admin access → alwaysrequires manager approval)
- **RISK MATCH**: Added manager approval step

#### Step 4: Approval Agent
- Requests approval from `manager_bharat`
- Simulates approval (in demo, auto-approved)
- Updates ticket: `approved_by_id=manager_bharat.id`
- Status: `approved`

#### Step 5: Identity Operations Agent (PRIVILEGED)
- **Checks approval status**: ✅ Approved
- **Database operation**:
  ```sql
  INSERT INTO user_groups (user_id, group_id)
  VALUES (bharat.id, jenkins_admin.id)
  ```
- **Jenkins sync** (if configured):
  ```bash
  # Via script console
  create_user("bharat", "password", "Bharat Kumar", "bharat@company.com")
  ```
- **Audit log**:
  ```sql
  INSERT INTO audit_logs (
    event_type='access_grant',
    actor_id=manager_bharat.id,
    action_summary='Granted jenkins_admin to Bharat Kumar'
  )
  ```
- Status: `completed`

#### Step 6: Validation Agent
- Verifies request status: `completed`
- Queries user groups: `SELECT ... FROM user_groups WHERE user_id = bharat.id`
- Confirms: `jenkins_admin` group now exists
- **Result**: ✅ **PASSED**

### Output

```json
{
  "success": true,
  "ticket_id": "REQ-1001",
  "validation": "PASSED",
  "granted_to": "bharat",
  "group": "jenkins_admin"
}
```

## 🔧 Running the Demo

### Prerequisites

1. **PostgreSQL** (running locally or Docker)
2. **Python 3.8+** with `requests` library
3. **Jenkins** (optional - for full sync)

### Setup PostgreSQL

```bash
# Using Docker
docker run -d \
  --name omniroute-postgres \
  -e POSTGRES_USER=omniroute \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=omniroute \
  -p 5432:5432 \
  postgres:15

# Run schema
docker exec -i omniroute-postgres psql -U omniroute -d omniroute < schema.sql
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run Workflow 1

```bash
# Simple demo (uses MockPostgres)
python workflows/workflow1.py

# Full demo with real PostgreSQL
PG_HOST=localhost PG_PORT=5432 PG_USER=omniroute PG_PASSWORD=password PG_DB=omniroute python workflows/workflow1.py
```

### Run Full Stack (Postgres + Jenkins)

```bash
# Start services
docker-compose up -d postgres jenkins

# Run workflow
python workflows/workflow1.py
```

## 📜 Workflow 2: Incident Response Flow

### Structure

```bash
# Coming soon: workflow2.py
# - P1 Incident Detection
# - Diagnostics Agent
# - Root Cause Analysis
# - Remediation Agent
# - RCA Report Generation
```

## 🎯 Key Features

### 1. **Permission-Scoped Agents**
- ApprovalAgent: Cannot modify systems
- DiagnosticsAgent: Cannot grant access
- IdentityOperationsAgent: Cannot restart Jenkins
- **Enforces separation of duties**

### 2. **Audit Trail Compliance**
- Every action logged to `audit_logs` table
- Records actor, timestamp, and details
- Draggable for timeline analysis
- User-Space: Each agent has independent memory

### 3. **Mock Identity Service**
- Simulates Azure AD behavior
- FastAPI-based (show in real demo)
- Supports LDAP-style authentication
- No real AD required

### 4. **RBAC by Design**
- Users → Groups → Permissions
- Graceful denials (not just crashes)
- Clear audit trail for policy violations

## 🔍 Troubleshooting

### Jenkins Sync Fails

**Symptom**: "Jenkins client not available"

**Solution**:
1. Ensure Jenkins is running: `docker ps | grep jenkins`
2. Check credentials in `jenkins/client.py`
3. Ensure `localhost:8080` is accessible

### PostgreSQL Connection Fails

**Symptom**: "Database error"

**Solution**:
1. Start PostgreSQL: `docker start omniroute-postgres`
2. Verify connection: `docker exec -i omniroute-postgres psql -U omniroute -d omniroute -c "SELECT * FROM users"`
3. Check environment variables

### User Already in Group

**Symptom**: IntegrityError during insert

**Solution**:
- This is expected! User exists in database
- Agent handles gracefully: returns success
- Check `user_groups` table for membership

## 📝 Expected Demo Output

```
================================================================================
🚀 AutoOps AI Service Desk - Workflow 1: Access Grant Path
================================================================================

🔧 Initializing components...
✅ Jenkins client initialized (check URL and credentials)
✅ Agent 1: ServiceDeskAgent
✅ Agent 2: WorkflowOrchestrator
✅ Agent 3: AccessGovernanceAgent
✅ Agent 4: ApprovalAgent
✅ Agent 5: IdentityOperationsAgent (privileged)
✅ Agent 6: ValidationAgent

================================================================================
📝 Input Request
================================================================================
{
  "ticket_id": "REQ-1001",
  "type": "access_request",
  "requested_by": "bharat",
  "resource": "jenkins_admin",
  "reason": "Production deployment support"
}

================================================================================
📋 STEP 1: Service Desk Agent - Classify Request
================================================================================
🔍 [ServiceDeskAgent] Processing request: REQ-1001
   Request type: access_request
✅ [ServiceDeskAgent] ✓ Recorded request
   → Category: access_request
   → Workflows: access_path

================================================================================
───── END OF WORKFLOW 1 ─────

🎉 End of Workflow 1 (success!)
```

## 🎓 Learning Objectives

From this hackathon project, you demonstrate:

1. ✅ **Multi-Agent Systems** - 6 specialized agents with independent contexts
2. ✅ **Enterprise Architecture** - Service desk, identity governance, incident management
3. ✅ **Privilege Separation** - Agents cannot perform unauthorized operations
4. ✅ **Audit Compliance** - Complete log trail for all actions
5. ✅ **Integration Architecture** - Postgres + Jenkins + Mock Identity Service
6. ✅ **Real Enterprise Flow** - Unlike "chatbots", looks like real ITSM platform

---

**Next Steps**:
- Build Workflow 2 (Incident Response)
- Add real Jenkins job synchronization
- Implement auto-remediation
- Create Docker Compose setup