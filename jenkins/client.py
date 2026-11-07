#!/usr/bin/env python3
"""
Jenkins API Client for AutoOps - Handles user synchronization and Jenkins operations
"""
import requests
import json
from typing import Dict, List, Optional

class JenkinsClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.auth = (username, password)
        self._session_init()

    def _session_init(self):
        """Initialize session with Jenkins"""
        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.headers.update({
            'Content-Type': 'application/json'
        })

    def get_job(self, job_name: str) -> Dict:
        """Get job details"""
        response = self.session.get(f'{self.base_url}/job/{job_name}/api/json')
        response.raise_for_status()
        return response.json()

    def create_user(self, username: str, password: str, email: str, full_name: str) -> Dict:
        """
        Create new Jenkins user
        Note: In real Jenkins, you'd need Jenkins LTS + Email plugin
        """
        try:
            # Using Jenkins script console for user creation (security risk - limit to admin)
            script = f"""
import hudson.model.User
import jenkins.model.*
import hudson.security._

def createUser(username, password, fullName, email) {{
    def instance = Jenkins.getInstance()
    def user = new hudson.model.User(username)
    user.setFullName(fullName)
    user.setProperties(
        new hudson.tasks.Mailer.UserProperty(email)
    )

    // In production, you'd hash the password and use Credentials
    // For demo, we'll use credentials
    def credentialsManager = instance.getExtensionList(
        'hudson.security.SecurityRealm'
    )[0]

    def credentialImpl = new hudson.credentials.impl.UsernamePasswordCredentialsImpl(
        jenkins.util.Secret.fromString(password),
        fullName,
        email
    )

    // Store credentials
    def domain = hudson.security.GlobalMatrixAuthorizationStrategy.UNSECURED_ROLE_MAPPING
    credentialsManager.addCredentials(domain, credentialImpl)

    // Add user to default group (Jenkins users)
    def userGroup = instance.getGroup("users")
    if (userGroup != null) {{
        userGroup.add(user)
    }}

    return "User created successfully"
}}

createUser("{username}", "{password}", "{fullName}", "{email}")
"""
            response = self.session.post(
                f'{self.base_url}/scriptText',
                data={'script': script}
            )
            response.raise_for_status()
            return {
                'success': True,
                'message': f'User {username} created in Jenkins via script console',
                'raw_response': response.text
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to create Jenkins user (requires admin script console access)'
            }

    def delete_user(self, username: str) -> Dict:
        """Delete Jenkins user"""
        script = f"""
import hudson.model.*
def deleteUser(username) {{
    def user = User.getById(username, false)
    if (user != null) {{
        user.delete()
        return "User deleted"
    }}
    return "User not found"
}}

deleteUser("{username}")
"""
        try:
            response = self.session.post(
                f'{self.base_url}/scriptText',
                data={'script': script}
            )
            response.raise_for_status()
            return {'success': True, 'message': 'User deleted from Jenkins'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_user_to_group(self, job_name: str, username: str, group_name: str) -> Dict:
        """
        Add user to Jenkins group (via job-based security)
        This is a common workaround for user groups in Jenkins
        """
        try:
            # Use plugin-based group management if available
            script = f"""
import hudson.model.*
import jenkins.model.*
import hudson.security.*

def addUserToGroup(jobName, username, groupName) {{
    def job = Jenkins.getInstance().getJob(jobName)
    if (job == null) {{
        job = Jenkins.getInstance().createProject(hudson.model.FreeStyleProject, jobName)
    }}

    // Configure job-based ACL (simplified)
    def acl = job.getACL()
    acl.createPermission(job.CANCEL, username)
    acl.createPermission(job.EDIT, username)
    acl.createPermission(job.QUEUE_ITEM, username)

    return "Added {username} to {jobName} via job ACL"
}}

addUserToGroup("{job_name}", "{username}", "{group_name}")
"""
            response = self.session.post(
                f'{self.base_url}/scriptText',
                data={'script': script}
            )
            response.raise_for_status()
            return {'success': True, 'message': f'Added {username} to {job_name} group'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def list_jobs(self) -> List[Dict]:
        """List all Jenkins jobs"""
        try:
            response = self.session.get(f'{self.base_url}/api/json?depth=0')
            response.raise_for_status()
            jobs = response.json()['_json-class']['jobs'] if '_json-class' in response.json() else []
            return [{'name': j['name'], 'url': j['url']} for j in jobs]
        except Exception as e:
            return [{'error': str(e)}]

    def test_connection(self) -> Dict:
        """Test Jenkins connection"""
        try:
            response = self.session.get(f'{self.base_url}/api/json?depth=0')
            response.raise_for_status()
            info = response.json()
            return {
                'success': True,
                'jenkins_url': self.base_url,
                'jobs': len(info.get('jobs', [])),
                'version': info.get('_json-class', {}).get('version', 'Unknown')
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

# Configuration
JENKINS_CONFIG = {
    'base_url': 'http://localhost:8080/jenkins',  # Docker Desktop port
    'username': 'admin',  # Will be created during setup
    'password': 'admin'  # Default for demo
}

def main():
    """Test Jenkins client"""
    client = JenkinsClient(
        JENKINS_CONFIG['base_url'],
        JENKINS_CONFIG['username'],
        JENKINS_CONFIG['password']
    )

    # Test connection
    print("=== Testing Jenkins Connection ===")
    result = client.test_connection()
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()