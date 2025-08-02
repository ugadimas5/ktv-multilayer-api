"""
Earth Engine Authentication Module for EUDR Compliance Analysis
Supports 16 Google Service Accounts for parallel processing
"""

import os
import json
import ee
from typing import Optional

def auth_init_ee(account: str, auth_path: str = "authentication/", print_status: bool = True) -> bool:
    """
    Initialize Earth Engine with specified service account
    
    Args:
        account: Service account identifier (e.g., "eudr-0", "eudr-1")
        auth_path: Directory path containing authentication files
        print_status: Whether to print authentication status
    
    Returns:
        bool: True if authentication successful, False otherwise
        
    Raises:
        ValueError: If the account format is invalid or authentication fails
        FileNotFoundError: If the key file doesn't exist
    """
    if print_status:
        print(f"Authenticating with Earth Engine using account '{account}'")
        
    # Validate account format
    if not account.startswith('eudr-') or not account.split('-')[1].isdigit():
        raise ValueError(f"Invalid account format '{account}'. Expected format: 'eudr-n' where n is a number 0 to 15")
    
    # Construct key file path
    key_file = os.path.join(auth_path, f"{account}.json")
    
    # Check if file exists
    if not os.path.exists(key_file):
        raise FileNotFoundError(f"Service account key file not found at {key_file}")
    
    try:
        # Load and validate credentials
        with open(key_file) as f:
            credentials = json.load(f)
            email = credentials.get('client_email')
            
        if not email:
            raise ValueError(f"No client_email found in key file {key_file}")
        
        # Initialize Earth Engine
        ee.Initialize(ee.ServiceAccountCredentials(email, key_file))
        
        if print_status:
            print(f"✅ Successfully authenticated with Earth Engine using account '{account}'")
            print(f"   Email: {email}")
            
        return True
        
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON in key file at {key_file}")
    except ee.EEException as e:
        raise ValueError(f"Failed to authenticate with Earth Engine: {e}")
    except Exception as e:
        if print_status:
            print(f"❌ Authentication failed for account '{account}': {e}")
        return False

def test_all_accounts(auth_path: str = "authentication/", max_accounts: int = 16) -> dict:
    """
    Test authentication for all service accounts
    
    Args:
        auth_path: Directory path containing authentication files
        max_accounts: Maximum number of accounts to test (default 16)
        
    Returns:
        dict: Results of authentication tests
    """
    results = {
        'successful': [],
        'failed': [],
        'missing': []
    }
    
    print(f"Testing authentication for {max_accounts} service accounts...")
    print("=" * 60)
    
    for i in range(max_accounts):
        account = f"eudr-{i}"
        key_file = os.path.join(auth_path, f"{account}.json")
        
        # Check if file exists
        if not os.path.exists(key_file):
            results['missing'].append(account)
            print(f"❌ {account}: Key file not found")
            continue
            
        # Test authentication
        try:
            success = auth_init_ee(account, auth_path, print_status=False)
            if success:
                results['successful'].append(account)
                print(f"✅ {account}: Authentication successful")
            else:
                results['failed'].append(account)
                print(f"❌ {account}: Authentication failed")
        except Exception as e:
            results['failed'].append(account)
            print(f"❌ {account}: {str(e)}")
    
    print("=" * 60)
    print(f"Summary:")
    print(f"  ✅ Successful: {len(results['successful'])}")
    print(f"  ❌ Failed: {len(results['failed'])}")
    print(f"  📁 Missing: {len(results['missing'])}")
    
    return results

def get_available_accounts(auth_path: str = "authentication/") -> list:
    """
    Get list of available service account files
    
    Args:
        auth_path: Directory path containing authentication files
        
    Returns:
        list: List of available account identifiers
    """
    available = []
    
    if not os.path.exists(auth_path):
        return available
        
    for i in range(16):
        account = f"eudr-{i}"
        key_file = os.path.join(auth_path, f"{account}.json")
        if os.path.exists(key_file):
            available.append(account)
    
    return available

# Usage example:
if __name__ == "__main__":
    # Test single account
    try:
        auth_init_ee("eudr-0")
        print("Single account test successful!")
    except Exception as e:
        print(f"Single account test failed: {e}")
    
    # Test all accounts
    results = test_all_accounts()
    
    # Get available accounts
    available = get_available_accounts()
    print(f"\nAvailable accounts: {available}")
