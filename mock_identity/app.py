#!/usr/bin/env python3
"""
Mock Identity Service - Simulates Azure AD/LDAP for AutoOps
Serves as FastAPI demo component for hackathon

This service demonstrates:
- User authentication simulation
- RBAC group queries
- LDAP-style attribute retrieval
- No real Azure AD required

Usage:
    docker-compose up -d mock-identity
    curl http://localhost:8000/users/bharat/profile
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, List, Optional
import json

# Mock database
MOCK_DB = {
    "users": {
        "bharat": {
            "username": "bharat",
            "email": "bharat@company.com",
            "name": "Bharat Kumar",
            "department": "Engineering",
            "title": "Developer",
            "manager": "manager_bharat",
            "phone": "+1234567890",
            "employee_id": "EMP001"
        },
        "manager_bharat": {
            "username": "manager_bharat",
            "email": "manager@company.com",
            "name": "Manager Bharat",
            "department": "Engineering",
            "title": "Engineering Manager",
            "manager": None,
            "phone": "+1234567891",
            "employee_id": "MGR001"
        },
        "admin_user": {
            "username": "admin_user",
            "email": "admin@company.com",
            "name": "System Admin",
            "department": "IT",
            "title": "System Administrator",
            "manager": "manager_bharat",
            "phone": "+1234567892",
            "employee_id": "ADMIN001"
        }
    },
    "groups": {
        "jenkins_admin": {
            "name": "jenkins_admin",
            "description": "Jenkins Admin Access",
            "members": ["admin_user"]
        },
        "dev_ops_team": {
            "name": "dev_ops_team",
            "description": "Development and Operations Team",
            "members": ["bharat", "admin_user"]
        },
        "deploy_admin": {
            "name": "deploy_admin",
            "description": "Deployment Admin",
            "members": ["admin_user"]
        }
    }
}

app = FastAPI(
    title="Mock Identity Service",
    description="Simulates Azure AD/LDAP for AutoOps AI Service Desk",
    version="1.0.0"
)


# Pydantic models
class UserProfile(BaseModel):
    username: str
    email: str
    name: str
    department: str
    title: str
    manager: Optional[str] = None
    groups: List[str] = []


class GroupInfo(BaseModel):
    name: str
    description: str
    members: List[str]


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return JSONResponse({
        "status": "healthy",
        "service": "Mock Identity Service",
        "version": "1.0.0",
        "timestamp": __import__('datetime').datetime.utcnow().isoformat()
    })


# Get all users
@app.get("/users", response_model=List[Dict])
async def list_users():
    """List all users (mock)"""
    return [
        {
            "username": user["username"],
            "email": user["email"],
            "name": user["name"],
            "title": user["title"],
            "department": user["department"],
            "employee_id": user["employee_id"]
        }
        for user in MOCK_DB["users"].values()
    ]


# Get user profile
@app.get("/users/{username}/profile", response_model=Dict)
async def get_user_profile(username: str):
    """Get user profile (mock Azure AD)"""
    if username not in MOCK_DB["users"]:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")

    user = MOCK_DB["users"][username]

    # Get user's groups
    user_groups = []
    for group_name, group_info in MOCK_DB["groups"].items():
        if username in group_info["members"]:
            user_groups.append(group_name)

    return {
        "username": user["username"],
        "email": user["email"],
        "name": user["name"],
        "department": user["department"],
        "title": user["title"],
        "manager": user["manager"],  # Optional: could be true/false for access management
        "phone": user["phone"],
        "employee_id": user["employee_id"],
        "groups": user_groups
    }


# Get user groups
@app.get("/users/{username}/groups", response_model=List[str])
async def get_user_groups(username: str):
    """Get user's groups (mock LDAP attributes)"""
    if username not in MOCK_DB["users"]:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")

    groups = []
    for group_name, group_info in MOCK_DB["groups"].items():
        if username in group_info["members"]:
            groups.append(group_name)

    return groups


# Get group info
@app.get("/groups/{group_name}", response_model=GroupInfo)
async def get_group_info(group_name: str):
    """Get group information"""
    if group_name not in MOCK_DB["groups"]:
        raise HTTPException(status_code=404, detail=f"Group '{group_name}' not found")

    group = MOCK_DB["groups"][group_name]
    return {
        "name": group["name"],
        "description": group["description"],
        "members": group["members"]
    }


# List all groups
@app.get("/groups", response_model=List[GroupInfo])
async def list_groups():
    """List all groups"""
    return [
        {
            "name": group["name"],
            "description": group["description"],
            "members": group["members"]
        }
        for group in MOCK_DB["groups"].values()
    ]


# Check if user is in group (LDAP-style access check)
@app.get("/users/{username}/groups/{group_name}", response_model=Dict)
async def check_group_membership(username: str, group_name: str):
    """Check if user is member of group"""
    if username not in MOCK_DB["users"]:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")

    if group_name not in MOCK_DB["groups"]:
        raise HTTPException(status_code=404, detail=f"Group '{group_name}' not found")

    group = MOCK_DB["groups"][group_name]
    is_member = username in group["members"]

    return {
        "user": username,
        "group": group_name,
        "member": is_member,
        "access_level": "GRANTED" if is_member else "DENIED"
    }


# Authenticate user (mock)
@app.post("/auth/login")
async def authenticate_user(username: str, password: str):
    """Mock login endpoint"""
    if username not in MOCK_DB["users"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # For demo, any password works if username exists
    user = MOCK_DB["users"][username]

    return {
        "user": username,
        "name": user["name"],
        "email": user["email"],
        "department": user["department"],
        "title": user["title"],
        "authenticated": True,
        "token": f"mock-token-{username}-{int(__import__('datetime').datetime.utcnow().timestamp())}"
    }


# Simulate RBAC check (like Azure AD)
@app.post("/auth/rbac-check")
async def rbac_check(username: str, resource: str, action: str):
    """
    Simulate Azure AD RBAC check
    Returns if granted/denied
    """
    user_profile = get_user_profile(username)

    if not user_profile:
        raise HTTPException(status_code=404, detail="User not found")

    # Simple role-based access check (demo)
    is_authenticated = True  # In real system, validate JWT token
    has_permission = False

    # Check if user has group with required permissions
    for group_name in user_profile["groups"]:
        group_permissions = {
            "jenkins_admin": ["build:run", "job:configure", "user:create"],
            "dev_ops_team": ["build:run", "job:view"],
            "deploy_admin": ["pipeline:run", "build:stop"]
        }

        if group_name in group_permissions:
            for perm in group_permissions[group_name]:
                # Simple permission matching (demo)
                if action in perm or any(action.startswith(p) for p in [f"{perm}:*" if ":" in perm else perm]):
                    has_permission = True
                    break

            if has_permission:
                break

    return {
        "user": username,
        "resource": resource,
        "action": action,
        "authenticated": is_authenticated,
        "granted": has_permission,
        "reason": "User has required group membership" if has_permission else "User lacks required permissions"
    }


# API information
@app.get("/api-info")
async def api_info():
    """Return API information for discovery"""
    return {
        "service": "Mock Identity Service",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "users": "/users",
            "user_profile": "/users/{username}/profile",
            "user_groups": "/users/{username}/groups",
            "group_info": "/groups/{group_name}",
            "groups": "/groups",
            "access_check": "/users/{username}/groups/{group_name}",
            "login": "/auth/login",
            "rbac_check": "/auth/rbac-check"
        },
        "documentation": "FastAPI auto-generated at /docs"
    }


# Main entry point
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)