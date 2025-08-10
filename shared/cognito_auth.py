#!/usr/bin/env python3
"""
Cognito Authentication Module for AgentCore Gateway
Handles OAuth2 client credentials flow to obtain access tokens
"""
import requests
import json
import logging
import os
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import time

logger = logging.getLogger(__name__)

class CognitoAuthenticator:
    """Handles Cognito OAuth2 authentication for AgentCore Gateway"""
    
    def __init__(self, client_id: str, client_secret: str, token_url: str):
        """
        Initialize the Cognito authenticator
        
        Args:
            client_id: Cognito app client ID
            client_secret: Cognito app client secret
            token_url: Cognito OAuth2 token endpoint URL
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self.access_token = None
        self.token_expires_at = None
        
    def fetch_access_token(self) -> str:
        """
        Fetch a new access token using client credentials flow
        
        Returns:
            str: The access token
            
        Raises:
            Exception: If token fetch fails
        """
        try:
            logger.info("Fetching new access token from Cognito...")
            
            # Prepare the request data
            data = {
                'grant_type': 'client_credentials',
                'client_id': self.client_id,
                'client_secret': self.client_secret
            }
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            # Make the request
            response = requests.post(
                self.token_url,
                data=data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"Token request failed with status {response.status_code}: {response.text}")
                raise Exception(f"Token request failed: {response.status_code}")
            
            token_data = response.json()
            
            if 'access_token' not in token_data:
                logger.error(f"Token response missing access_token: {token_data}")
                raise Exception("Token response missing access_token")
            
            # Store token and expiration
            self.access_token = token_data['access_token']
            
            # Calculate expiration time (default to 1 hour if not provided)
            expires_in = token_data.get('expires_in', 3600)
            self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
            
            logger.info(f"Successfully obtained access token, expires at {self.token_expires_at}")
            return self.access_token
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching token: {e}")
            raise Exception(f"Network error: {e}")
        except Exception as e:
            logger.error(f"Error fetching access token: {e}")
            raise
    
    def get_valid_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary
        
        Returns:
            str: A valid access token
        """
        # Check if we have a valid token
        if (self.access_token and self.token_expires_at and 
            datetime.now() < self.token_expires_at - timedelta(minutes=5)):
            # Token is still valid (with 5-minute buffer)
            return self.access_token
        
        # Token is expired or doesn't exist, fetch a new one
        return self.fetch_access_token()
    
    def get_auth_headers(self) -> Dict[str, str]:
        """
        Get headers with valid authorization token
        
        Returns:
            Dict[str, str]: Headers with Authorization Bearer token
        """
        token = self.get_valid_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def is_token_valid(self) -> bool:
        """
        Check if current token is still valid
        
        Returns:
            bool: True if token is valid, False otherwise
        """
        return (self.access_token and self.token_expires_at and 
                datetime.now() < self.token_expires_at - timedelta(minutes=5))

def create_cognito_authenticator_from_env() -> Optional[CognitoAuthenticator]:
    """
    Create a CognitoAuthenticator instance from environment variables
    
    Returns:
        CognitoAuthenticator or None if required env vars are missing
    """
    client_id = os.getenv("COGNITO_CLIENT_ID")
    client_secret = os.getenv("COGNITO_CLIENT_SECRET")
    token_url = os.getenv("COGNITO_TOKEN_URL")
    
    if not all([client_id, client_secret, token_url]):
        logger.warning("Missing required Cognito environment variables")
        return None
    
    return CognitoAuthenticator(client_id, client_secret, token_url)

def create_cognito_authenticator_from_config(config: Dict[str, Any]) -> Optional[CognitoAuthenticator]:
    """
    Create a CognitoAuthenticator instance from configuration dictionary
    
    Args:
        config: Configuration dictionary with cognito_client_info
        
    Returns:
        CognitoAuthenticator or None if required config is missing
    """
    cognito_info = config.get("cognito_client_info", {})
    
    client_id = cognito_info.get("client_id")
    client_secret = cognito_info.get("client_secret")
    token_url = cognito_info.get("token_url")
    
    if not all([client_id, client_secret, token_url]):
        logger.warning("Missing required Cognito configuration")
        return None
    
    return CognitoAuthenticator(client_id, client_secret, token_url)

# Example usage function for testing
def test_cognito_auth():
    """Test function for Cognito authentication"""
    try:
        # Try to create authenticator from environment
        auth = create_cognito_authenticator_from_env()
        
        if auth:
            logger.info("Testing Cognito authentication...")
            token = auth.get_valid_token()
            logger.info(f"Successfully obtained token: {token[:20]}...")
            
            headers = auth.get_auth_headers()
            logger.info(f"Auth headers: {headers}")
            
            return True
        else:
            logger.warning("Cognito authenticator not available")
            return False
            
    except Exception as e:
        logger.error(f"Authentication test failed: {e}")
        return False

if __name__ == "__main__":
    # Configure logging for standalone testing
    logging.basicConfig(level=logging.INFO)
    
    # Test the authentication
    success = test_cognito_auth()
    if success:
        print("✅ Cognito authentication test passed")
    else:
        print("❌ Cognito authentication test failed") 