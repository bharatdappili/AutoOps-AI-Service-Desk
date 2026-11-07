-- AutoOps AI Service Desk - PostgreSQL Schema

-- Users table (replaces Azure AD)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'end_user', -- end_user, admin, manager
    status VARCHAR(50) DEFAULT 'active', -- active, disabled, pending
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) DEFAULT 'system'
);

-- Groups table
CREATE TABLE groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User-Group membership (RBAC)
CREATE TABLE user_groups (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    group_id INTEGER REFERENCES groups(id) ON DELETE CASCADE,
    granted_by VARCHAR(255), -- who added this user to group
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Access Requests table
CREATE TABLE access_requests (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(100) UNIQUE NOT NULL,
    requested_by INTEGER REFERENCES users(id),
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resource VARCHAR(255), -- e.g., "jenkins_admin"
    reason TEXT,
    status VARCHAR(50) DEFAULT 'pending_approval', -- pending_approval, approved, rejected, completed
    approval_status VARCHAR(50), -- pending, approved, rejected
    approved_by_id INTEGER REFERENCES users(id),
    approved_at TIMESTAMP,
    rejection_reason TEXT
);

-- Audit Trail (for compliance)
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL, -- access_granted, access_revoked, approval_requested, etc.
    actor_id INTEGER REFERENCES users(id),
    action_summary TEXT,
    details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default users
INSERT INTO users (username, email, name, role) VALUES
('bharat', 'bharat@company.com', 'Bharat Kumar', 'end_user'),
('manager_bharat', 'manager@company.com', 'Manager Bharat', 'manager'),
('admin_user', 'admin@company.com', 'System Admin', 'admin');

-- Insert default groups
INSERT INTO groups (name, description) VALUES
('jenkins_admin', 'Jenkins Admin Access'),
('dev_ops_team', 'Development and Operations Team'),
('prod_access', 'Production Environment Access');

-- Add Bharat to Dev Ops team by default
INSERT INTO user_groups (user_id, group_id, granted_by, granted_at)
SELECT
    (SELECT id FROM users WHERE username = 'bharat'),
    (SELECT id FROM groups WHERE name = 'dev_ops_team'),
    'system',
    CURRENT_TIMESTAMP;

-- Functions to track changes
CREATE OR REPLACE FUNCTION log_access_grant(
    p_user_id INTEGER,
    p_group_id INTEGER,
    p_actor_id INTEGER,
    p_summary TEXT
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO audit_logs (event_type, actor_id, action_summary, details)
    VALUES (
        'access_grant',
        p_actor_id,
        p_summary,
        jsonb_build_object(
            'user_id', p_user_id,
            'group_id', p_group_id,
            'group_name', (SELECT name FROM groups WHERE id = p_group_id),
            'granted_at', CURRENT_TIMESTAMP
        )
    );
END;
$$ LANGUAGE plpgsql;