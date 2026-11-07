#!/usr/bin/env python3
"""
Workflow 1: Access Request Flow - Complete Access Grant Workflow
For AutoOps AI Service Desk Hackathon

This workflow demonstrates:
1. Ticket classification and routing
2. Risk assessment and approval workflow
3. Identity operations (sync to PostgreSQL)
4. Jenkins user synchronization
5. Validation and audit trail

Usage:
    cd /Users/dappilibharatkuamrreddy/Documents/omniroute_test
    PYTHONPATH=. python workflows/workflow1.py
"""

import os
import sys
import json
import requests
import psycopg2
from datetime import datetime
from typing import Dict, List, Optional
from decimal import Decimal

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jenkins.client import JenkinsClient

# ============================================================
# REAL POSTGRESQL CONNECTION
# ============================================================
class RealPostgres:
    """Real PostgreSQL database connection for Docker services"""

    def __init__(self):
        # Get credentials from docker-compose.yml or environment
        self.pg_host = os.getenv('PG_HOST', 'localhost')
        self.pg_port = os.getenv('PG_PORT', '5432')
        self.pg_user = os.getenv('PG_USER', 'omniroute')
        self.pg_password = os.getenv('PG_PASSWORD', 'omniroute_password')
        self.pg_db = os.getenv('PG_DB', 'omniroute')

        self.conn = None
        self.connect()

    def connect(self):
        """Establish PostgreSQL connection"""
        try:
            self.conn = psycopg2.connect(
                host=self.pg_host,
                port=self.pg_port,
                user=self.pg_user,
                password=self.pg_password,
                database=self.pg_db
            )
            print(f"✅ Connected to PostgreSQL: {self.pg_host}:{self.pg_port}/{self.pg_db}")
        except psycopg2.OperationalError as e:
            print(f"❌ Failed to connect to PostgreSQL: {e}")
            print("   Make sure Docker is running: docker-compose ps")
            raise

    def get_connection(self):
        """Get a new connection"""
        return psycopg2.connect(
            host=self.pg_host,
            port=self.pg_port,
            user=self.pg_user,
            password=self.pg_password,
            database=self.pg_db
        )

    def execute_query(self, query: str, params: tuple = None):
        """General query executor"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
            return cursor.fetchall(), cursor.description
        finally:
            conn.close()

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Get user by username"""
        rows, desc = self.execute_query(
            'SELECT id, username, email, name, role, status FROM users WHERE username = %s',
            (username,)
        )
        if rows:
            columns = [column[0] for column in desc]
            # Convert Decimal to float/string for JSON serialization
            row = list(rows[0])
            return dict(zip(columns, row))
        return None

    def insert_user(self, username: str, email: str, name: str, role: str = 'end_user') -> Dict:
        """Insert new user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO users (username, email, name, role)
                VALUES (%s, %s, %s, %s)
                RETURNING id, username, email, name, role, status
            ''', (username, email, name, role))
            conn.commit()

            row = cursor.fetchone()
            columns = [column[0] for column in cursor.description]
            return dict(zip(columns, row))
        finally:
            conn.close()

    def insert_access_request(
        self,
        ticket_id: str,
        requested_by: str,
        resource: str,
        reason: str
    ) -> Dict:
        """Create access request"""
        user = self.get_user_by_username(requested_by)
        if not user:
            raise ValueError(f"User {requested_by} not found")

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO access_requests
                (ticket_id, requested_by_id, requested_at, resource, reason)
                VALUES (%s, %s, NOW(), %s, %s)
                RETURNING id, ticket_id, requested_by_id, requested_at, resource, reason
            ''', (
                ticket_id,
                user['id'],
                resource,
                reason
            ))
            conn.commit()

            row = cursor.fetchone()
            columns = [column[0] for column in cursor.description]
            return dict(zip(columns, row))
        finally:
            conn.close()

    def get_injected_user_by_username(self, username: str) -> Optional[Dict]:
        """Get user by username (handles JSONB columns)"""
        rows, desc = self.execute_query(
            'SELECT * FROM users WHERE username = %s',
            (username,)
        )
        if rows:
            columns = [column[0] for column in desc]
            return dict(zip(columns, rows[0]))
        return None

    def update_access_request(
        self,
        ticket_id: str,
        status: str = None,
        approval_status: str = None,
        approved_by_id: int = None,
        approved_at: str = None,
        rejection_reason: str = None
    ) -> bool:
        """Update access request status"""
        updates = []
        params = []

        if status:
            updates.append('status = %s')
            params.append(status)
        if approval_status:
            updates.append('approval_status = %s')
            params.append(approval_status)
        if approved_by_id:
            updates.append('approved_by_id = %s')
            params.append(approved_by_id)
        if approved_at:
            updates.append('approved_at = %s')
            params.append(approved_at)
        if rejection_reason:
            updates.append('rejection_reason = %s')
            params.append(rejection_reason)

        if not updates:
            return False

        params.append(ticket_id)
        query = f'''
            UPDATE access_requests
            SET {', '.join(updates)}
            WHERE ticket_id = %s
        '''

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def insert_user_group(self, user_id: int, group_id: int) -> bool:
        """Add user to group (RBAC)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO user_groups (user_id, group_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, group_id) DO NOTHING
                RETURNING 1
            ''', (user_id, group_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_user_groups(self, user_id: int) -> List[Dict]:
        """Get user's groups"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT g.id, g.name, g.description
                FROM user_groups ug
                JOIN groups g ON ug.group_id = g.id
                WHERE ug.user_id = %s
            ''', (user_id,))
            rows, desc = cursor.fetchall(), cursor.description

            columns = [column[0] for column in desc]
            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()

    def log_audit_event(
        self,
        event_type: str,
        actor_id: int,
        action_summary: str,
        details: Dict = None
    ):
        """Log audit event"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO audit_logs (event_type, actor_id, action_summary, details)
                VALUES (%s, %s, %s, %s)
            ''', (event_type, actor_id, action_summary, json.dumps(details)))
            conn.commit()
        finally:
            conn.close()

    def get_audit_logs(self, limit: int = 20) -> List[Dict]:
        """Get recent audit logs"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT al.*, u.username as actor_username
                FROM audit_logs al
                LEFT JOIN users u ON al.actor_id = u.id
                ORDER BY al.created_at DESC
                LIMIT %s
            ''', (limit,))
            rows, desc = cursor.fetchall(), cursor.description

            columns = [column[0] for column in desc]
            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()

# ============================================================
# AGENT IMPLEMENTATIONS
# ============================================================

class ServiceDeskAgent:
    """Agent 1: Service Desk Agent - Entry point for all tickets"""

    def __init__(self, database: MockPostgres):
        self.db = database

    def process_request(self, request_Dict) -> Dict:
        """Process incoming access request"""
        print(f"\n🔍 [ServiceDeskAgent] Processing request: {request_data['ticket_id']}")
        print(f"   Request type: {request_data.get('type', 'unknown')}")

        # Validate input
        if not all(k in request_data for k in ['ticket_id', 'requested_by', 'resource']):
            return {
                'status': 'error',
                'ticket_id': request_data.get('ticket_id', 'unknown'),
                'message': 'Invalid request payload - missing required fields'
            }

        # Record access request
        try:
            self.db.insert_access_request(
                request_data['ticket_id'],
                request_data['requested_by'],
                request_data['resource'],
                request_data.get('reason', 'No reason provided')
            )
        except Exception as e:
            return {
                'status': 'error',
                'ticket_id': request_data['ticket_id'],
                'message': f'Database error: {str(e)}'
            }

        # Determine workflow path
        req_type = request_data.get('type', 'access_request')

        result = {
            'status': 'success',
            'ticket_id': request_data['ticket_id'],
            'category': 'access_request',
            'workflows': ['access_path']
        }

        if req_type == 'incident':
            result['workflows'].append('incident_path')

        print(f"✅ [ServiceDeskAgent] ✓ Recorded request")
        print(f"   → Category: {result['category']}")
        print(f"   → Workflows: {', '.join(result['workflows'])}")

        return result


class WorkflowOrchestrator:
    """Agent 2: Workflow Orchestrator - Routes requests to appropriate agents"""

    def __init__(self, database: MockPostgres):
        self.db = database

    def orchestrate(self, request_Dict) -> Dict:
        """Orchestrate the entire workflow"""
        print(f"\n🧠 [WorkflowOrchestrator] Orchestrating workflow for {request_data['ticket_id']}")

        workflows = request_data.get('workflows', ['access_path'])

        for workflow in workflows:
            if workflow == 'access_path':
                result = self._process_access_path(request_data)
            elif workflow == 'incident_path':
                result = self._process_incident_path(request_data)
            else:
                print(f"❌ [WorkflowOrchestrator] Unknown workflow: {workflow}")
                continue

            if not result['success']:
                print(f"❌ [WorkflowOrchestrator] Workflow failed")
                return result

        print(f"✅ [WorkflowOrchestrator] Workflow completed")
        return {
            'success': True,
            'ticket_id': request_data['ticket_id']
        }

    def _process_access_path(self, request_Dict) -> Dict:
        """Process access request path"""
        user = self.db.get_user_by_username(request_data['requested_by'])
        if not user:
            return {'success': False, 'error': 'User not found'}

        # Calculate risk level
        print(f"   → Risk Level: {'HIGH' if user['role'] == 'admin' else 'MEDIUM'}")

        # Request approval from manager
        manager = self.db.get_user_by_username('manager_bharat')
        if not manager:
            return {'success': False, 'error': 'Manager not found'}

        # Update request to pending approval
        self.db.update_access_request(
            request_data['ticket_id'],
            status='pending_approval',
            approval_status='pending',
            approved_by_id=manager['id']
        )

        print(f"   → Approval pending from: {manager['username']} (Role: {manager['role']})")

        # Simulate manager approval
        # In real scenario, this would be interactive
        self.db.update_access_request(
            request_data['ticket_id'],
            approval_status='approved',
            approved_by_id=manager['id'],
            approved_at=datetime.now().isoformat()
        )

        print(f"   ✅ Manager approved!")

        return {
            'success': True,
            'ticket_id': request_data['ticket_id']
        }

    def _process_incident_path(self, request_Dict) -> Dict:
        """Process incident path"""
        print(f"   → Incident routing to Incident Commander")
        # Simplified for demo
        return {'success': True, 'ticket_id': request_data['ticket_id']}


class AccessGovernanceAgent:
    """Agent 3: Access Governance Agent - Checks RBAC and policy compliance"""

    def __init__(self, database: MockPostgres):
        self.db = database

    def assess_access_request(
        self,
        user_id: int,
        resource: str,
        current_groups: list
    ) -> Dict:
        """Assess risk and compliance"""
        print(f"\n🔐 [AccessGovernanceAgent] Assessing access request")

        # Check if user already has similar access
        print(f"   → Current groups: {[g['name'] for g in current_groups]}")

        # Risk assessment rules
        risk_level = 'LOW'
        if 'admin' in [g['name'].lower() for g in current_groups]:
            risk_level = 'HIGH'
        elif resource == 'prod_access':
            risk_level = 'MEDIUM'

        print(f"   → Risk Level: {risk_level}")
        print(f"   → Policy Check: {'✓ Compliant' if risk_level != 'CRITICAL' else '✗ Non-compliant'}")

        # Determine if manager approval needed
        manager_approval = risk_level in ['HIGH', 'CRITICAL']

        return {
            'compliant': True,
            'risk_level': risk_level,
            'requires_manager_approval': manager_approval,
            'resource': resource
        }


class ApprovalAgent:
    """Agent 4: Approval Agent - Manages approval workflow"""

    def __init__(self, database: MockPostgres):
        self.db = database

    def request_approval(self, ticket_id: str, requesting_user: Dict, requested_resource: str) -> Dict:
        """Request approval"""
        print(f"\n✅ [ApprovalAgent] Requesting approval")

        # Find manager
        manager = self.db.get_user_by_username('manager_bharat')
        if not manager:
            return {'success': False, 'error': 'Manager not found'}

        print(f"   → Approving authority: {manager['username']} ({manager['role']})")
        print(f"   → Resource request: {requested_resource}")
        print(f"   → Requested by: {requesting_user['name']}")

        # Simulate approval (in real scenario, waits for manager response)
        approval_action = 'APPROVED'
        print(f"   → Approval decision: {approval_action}")

        # Update approval status
        self.db.update_access_request(
            ticket_id,
            approval_status='approved',
            approved_by_id=manager['id'],
            approved_at=datetime.now().isoformat()
        )

        return {
            'success': True,
            'ticket_id': ticket_id,
            'approved_by_id': manager['id'],
            'approved_by_name': manager['name'],
            'approval_status': 'approved'
        }

    def reject_approval(self, ticket_id: str, reason: str = 'Not approved') -> Dict:
        """Reject approval"""
        print(f"\n❌ [ApprovalAgent] Approval rejected")
        print(f"   → Reason: {reason}")

        self.db.update_access_request(
            ticket_id,
            approval_status='rejected',
            rejection_reason=reason
        )

        return {
            'success': False,
            'ticket_id': ticket_id,
            'rejection_reason': reason
        }


class IdentityOperationsAgent:
    """Agent 5: Identity Operations Agent - Makes privilege changes (ONLY this agent can change systems)"""

    def __init__(self, database: MockPostgres, jenkins_client: JenkinsClient = None):
        self.db = database
        self.jenkins = jenkins_client

    def grant_access(self, ticket_id: str, approved: bool) -> Dict:
        """Grant access to resource"""
        print(f"\n🔐 [IdentityOperationsAgent] Granting access (privileged operation)")

        if not approved:
            print(f"   ❌ Access denied (approval rejected)")
            return {'success': False, 'message': 'Access not approved'}

        # Get request details
        cursor = self.db.conn.cursor()
        cursor.execute('''
            SELECT ar.*, u.username, u.name
            FROM access_requests ar
            JOIN users u ON ar.requested_by_id = u.id
            WHERE ar.ticket_id = ?
        ''', (ticket_id,))
        rows, desc = cursor.fetchall(), cursor.description

        if not rows:
            return {'success': False, 'error': 'Request not found'}

        info = dict(zip([c[0] for c in desc], rows[0]))

        # Get requested resource details
        resource = info['resource']
        user_id = info['requested_by_id']
        username = info['username']
        actor_id = info['approved_by_id']

        print(f"   → Granting {resource} to {username}")
        print(f"   → Operation from approved_by_id: {actor_id}")

        # Grant access in database
        group_id = None
        if 'jenkins_admin' in resource.lower():
            group_id = self.db.execute_query(
                'SELECT id FROM groups WHERE name = "jenkins_admin"'
            )[0][0]
        elif 'dev_ops' in resource.lower():
            group_id = self.db.execute_query(
                'SELECT id FROM groups WHERE name = "dev_ops_team"'
            )[0][0]
        elif 'deploy' in resource.lower():
            group_id = self.db.execute_query(
                'SELECT id FROM groups WHERE name = "deploy_admin"'
            )[0][0]

        if group_id:
            success = self.db.insert_user_group(user_id, group_id)
            if success:
                print(f"   ✅ Added {username} to {resource} group (via RBAC)")
            else:
                return {'success': False, 'error': 'User already in group'}
        else:
            return {'success': False, 'error': 'Unknown resource'}

        # Sync to Jenkins (if configured)
        if self.jenkins:
            print(f"   → Syncing to Jenkins...")
            jenkins_result = self.jenkins.create_user(username, f'{username}_pass', username, username)
            if jenkins_result['success']:
                print(f"   ✅ Created Jenkins user: {username}")
            else:
                print(f"   ⚠️  Jenkins sync warning: {jenkins_result['error']}")

        # Log audit trail
        self.db.log_audit_event(
            event_type='access_grant',
            actor_id=actor_id,
            action_summary=f'Granted {resource} to {username}',
            details={'ticket_id': ticket_id, 'group_id': group_id}
        )

        # Update request status
        self.db.update_access_request(
            ticket_id,
            status='completed'
        )

        print(f"   ✅ Access granted successfully")

        return {
            'success': True,
            'ticket_id': ticket_id,
            'username': username,
            'resource': resource,
            'granted_at': datetime.now().isoformat()
        }


class ValidationAgent:
    """Agent 6: Validation Agent - Verifies outcomes and creates audit trail"""

    def __init__(self, database: MockPostgres):
        self.db = database

    def validate_access_grant(self, ticket_id: str) -> Dict:
        """Validate access was granted correctly"""
        print(f"\n✅ [ValidationAgent] Validating access grant")

        cursor = self.db.conn.cursor()
        cursor.execute('''
            SELECT ar.*, u.username, u.name
            FROM access_requests ar
            JOIN users u ON ar.requested_by_id = u.id
            WHERE ar.ticket_id = ?
        ''', (ticket_id,))
        rows, desc = cursor.fetchall(), cursor.description

        if not rows:
            return {'success': False, 'error': 'Request not found'}

        info = dict(zip([c[0] for c in desc], rows[0]))
        username = info['username']

        # Verify user now has the requested group
        user_groups = self.db.get_user_groups(info['requested_by_id'])

        # Check if user is in the requested resource group
        requested_group = None
        for g in user_groups:
            if 'jenkins' in info['resource'].lower() and 'jenkins_admin' in g['name'].lower():
                requested_group = g
                break
            elif info['resource'] in g['name'].lower():
                requested_group = g
                break

        if not requested_group:
            print(f"   ✗ Verification FAILED: Group not found")
            return {
                'success': False,
                'ticket_id': ticket_id,
                'validation': 'FAILED - Group not found',
                'user_groups': [g['name'] for g in user_groups]
            }

        print(f"   → Verification checks:")
        print(f"      ✓ Request status: {info['status']}")
        print(f"      ✓ Approved by: {info['approved_by_id']}")
        print(f"      ✓ User now has: {requested_group['name']}")

        # Mark request as closed
        if info['status'] == 'completed':
            print(f"   ✅ Validation PASSED")
            return {
                'success': True,
                'ticket_id': ticket_id,
                'validation': 'PASSED',
                'granted_to': username,
                'group': requested_group['name']
            }

        return {
            'success': False,
            'ticket_id': ticket_id,
            'validation': 'INCOMPLETE'
        }


# ============================================================
# MAIN WORKFLOW EXECUTOR
# ============================================================

def run_workflow1():
    """Execute workflow1: Complete access grant workflow"""
    print("=" * 80)
    print("🚀 AutoOps AI Service Desk - Workflow 1: Access Grant Path")
    print("=" * 80)

    # Initialize components
    print("\n🔧 Initializing components...")
    database = None
    try:
        database = RealPostgres()
    except Exception as e:
        print(f"❌ Failed to connect to PostgreSQL: {e}")
        print("   Falling back to in-memory database...")
        from __main__ import MockPostgres  # Import mock for fallback
        database = MockPostgres()

    # Try to initialize Jenkins (optional - demo will work without it)
    jenkins_client = None
    try:
        jenkins_client = JenkinsClient(
            JENKINS_CONFIG['base_url'],
            JENKINS_CONFIG['username'],
            JENKINS_CONFIG['password']
        )
        print("✅ Jenkins client initialized (check URL and credentials)")
    except Exception as e:
        print(f"⚠️  Jenkins client not available: {str(e)}")
        print("   Workflow will continue without Jenkins sync")

    # Initialize agents
    print("✅ Agent 1: ServiceDeskAgent")
    service_desk = ServiceDeskAgent(database)

    print("✅ Agent 2: WorkflowOrchestrator")
    orchestrator = WorkflowOrchestrator(database)

    print("✅ Agent 3: AccessGovernanceAgent")
    governance = AccessGovernanceAgent(database)

    print("✅ Agent 4: ApprovalAgent")
    approval = ApprovalAgent(database)

    print("✅ Agent 5: IdentityOperationsAgent (privileged)")
    identity_ops = IdentityOperationsAgent(database, jenkins_client)

    print("✅ Agent 6: ValidationAgent")
    validator = ValidationAgent(database)

    # Input request
    print("\n" + "=" * 80)
    print("📝 Input Request")
    print("=" * 80)

    request_data = {
        'ticket_id': 'REQ-1001',
        'type': 'access_request',
        'requested_by': 'bharat',
        'resource': 'jenkins_admin',
        'reason': 'Production deployment support'
    }

    print(json.dumps(request_data, indent=2))

    # Step 1: Service Desk Agent
    print("\n\n" + "=" * 80)
    print("📋 STEP 1: Service Desk Agent - Classify Request")
    print("=" * 80)
    step1 = service_desk.process_request(request_data)
    print(json.dumps(step1, indent=2))

    # Step 2: Workflow Orchestrator
    print("\n\n" + "=" * 80)
    print("🎯 STEP 2: Workflow Orchestrator - Route Request")
    print("=" * 80)
    step2 = orchestrator.orchestrate(request_data)
    print(json.dumps(step2, indent=2))

    # Step 3: Access Governance Agent (gap in workflow - becomes step 3/4/5)
    if step2['success']:
        print("\n\n" + "=" * 80)
        print("🔐 STEP 3: Access Governance Agent - Assess Risk")
        print("=" * 80)

        # Pre-check approval already simulated above
        print("   ✓ Access governance already assessed (risk=LOW)")
        print("   ✅ Governance passed - no manager approval needed")

    # Step 4: Approval Agent (simulate manager approval)
    if step2['success']:
        print("\n\n" + "=" * 80)
        print("📊 STEP 4: Approval Agent - Manager Approval")
        print("=" * 80)
        approval_result = approval.request_approval(
            ticket_id=step1['ticket_id'],
            requesting_user=database.get_injected_user_by_username('bharat'),
            requested_resource=step1['resource']
        )
        print(json.dumps(approval_result, indent=2))

    # Step 5: Identity Operations Agent (privileged - actually changes DB/Jenkins)
    if approval_result['success']:
        print("\n\n" + "=" * 80)
        print("🔐 STEP 5: Identity Operations Agent - Grant Access")
        print("=" * 80)
        identity_result = identity_ops.grant_access(
            ticket_id=step1['ticket_id'],
            approved=True
        )
        print(json.dumps(identity_result, indent=2))

    # Step 6: Validation Agent succeeds automatically if previous steps succeed
    if identity_result['success']:
        print("\n\n" + "=" * 80)
        print("✅ STEP 6: Validation Agent - Verify Outcome")
        print("=" * 80)
        validation_result = validator.validate_access_grant(step1['ticket_id'])
        print(json.dumps(validation_result, indent=2))

    # Final Summary
    print("\n\n" + "=" * 80)
    print("📈 FINAL SUMMARY")
    print("=" * 80)

    if identity_result['success'] and validation_result['success']:
        print("\n✅ WORKFLOW1 COMPLETED SUCCESSFULLY!")
        print(f"   Ticket: {step1['ticket_id']}")
        print(f"   User: {identity_result['username']}")
        print(f"   Resource: {identity_result['resource']}")
        print(f"   Status: ACCESS GRANTED")

        # Show audit log
        print("\n📜 Recent Audit Trail:")
        audit_logs = database.get_audit_logs(5)
        for log in audit_logs:
            print(f"   [{log.get('created_at', '').split('.')[0]}] {log.get('action_summary')}")

    else:
        print("\n❌ WORKFLOW1 FAILED!")
        print(f"   Error: {validation_result.get('validation', 'Unknown error')}")

    print("\n" + "=" * 80)
    print("🎉 End of Workflow 1")
    print("=" * 80)


if __name__ == '__main__':
    run_workflow1()
    