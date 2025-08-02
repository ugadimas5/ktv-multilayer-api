"""
Configuration module for EUDR Compliance Analysis API
Handles Earth Engine authentication and multi-account settings
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Earth Engine Service Accounts Configuration
EE_SERVICE_ACCOUNT_PATH = os.getenv("EE_SERVICE_ACCOUNT_PATH", "authentication/")
TOTAL_SERVICE_ACCOUNTS = int(os.getenv("TOTAL_SERVICE_ACCOUNTS", "16"))
ENABLE_PARALLEL_PROCESSING = os.getenv("ENABLE_PARALLEL_PROCESSING", "true").lower() == "true"
DEFAULT_PARALLEL_ACCOUNTS = int(os.getenv("DEFAULT_PARALLEL_ACCOUNTS", "16"))
FALLBACK_TO_SINGLE_ACCOUNT = os.getenv("FALLBACK_TO_SINGLE_ACCOUNT", "true").lower() == "true"

# Parallel Processing Configuration
MAX_PARALLEL_WORKERS = int(os.getenv("MAX_PARALLEL_WORKERS", "8"))
SERVICE_ACCOUNT_PREFIX = "eudr"  # Accounts named: eudr-0.json, eudr-1.json, etc.

# Google Cloud Configuration
GOOGLE_CLOUD_PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT_ID", "")

# Earth Engine Quota Settings
EE_DAILY_QUOTA_PER_ACCOUNT = int(os.getenv("EE_DAILY_QUOTA_PER_ACCOUNT", "25000"))
EE_REQUESTS_PER_MINUTE = int(os.getenv("EE_REQUESTS_PER_MINUTE", "1000"))

# Database Configuration (for batch processing)
DATABASE_CONFIG = {
    "host": os.getenv("postgisHost", "localhost"),
    "port": int(os.getenv("postgisPort", "5432")),
    "database": os.getenv("postgisDatabase", "eudr_compliance"),
    "username": os.getenv("postgisUsername", "postgres"),
    "password": os.getenv("postgisPassword", "")
}

# API Configuration
API_CONFIG = {
    "version": "2.0.0",
    "title": "EUDR Forest Compliance Analysis API",
    "description": "Professional EUDR compliance monitoring using satellite data",
    "max_buffer_km": 50.0,
    "default_buffer_km": 5.0,
    "supported_datasets": [
        "JRC EUFO 2020",
        "SBTN Natural Lands 2020",
        "GLAD Primary Forests",
        "GFC Hansen 2024"
    ]
}

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
ENABLE_EE_QUOTA_MONITORING = os.getenv("ENABLE_EE_QUOTA_MONITORING", "true").lower() == "true"

# Security Configuration
ROTATE_CREDENTIALS_DAYS = int(os.getenv("ROTATE_CREDENTIALS_DAYS", "90"))
ENABLE_IP_WHITELIST = os.getenv("ENABLE_IP_WHITELIST", "false").lower() == "true"

def get_service_account_path(account_id: int) -> str:
    """
    Get the full path to a specific service account file
    
    Args:
        account_id: Service account number (0-15)
        
    Returns:
        str: Full path to the service account JSON file
    """
    if not (0 <= account_id < TOTAL_SERVICE_ACCOUNTS):
        raise ValueError(f"Invalid account_id {account_id}. Must be 0-{TOTAL_SERVICE_ACCOUNTS-1}")
    
    filename = f"eudr-{account_id}.json"
    return os.path.join(EE_SERVICE_ACCOUNT_PATH, filename)

def validate_config() -> dict:
    """
    Validate configuration and return status
    
    Returns:
        dict: Configuration validation results
    """
    issues = []
    warnings = []
    
    # Check service account path
    if not os.path.exists(EE_SERVICE_ACCOUNT_PATH):
        issues.append(f"Service account path does not exist: {EE_SERVICE_ACCOUNT_PATH}")
    
    # Check for service account files
    missing_accounts = []
    for i in range(TOTAL_SERVICE_ACCOUNTS):
        account_path = get_service_account_path(i)
        if not os.path.exists(account_path):
            missing_accounts.append(f"eudr-{i}.json")
    
    if missing_accounts:
        if len(missing_accounts) == TOTAL_SERVICE_ACCOUNTS:
            issues.append("No service account files found")
        else:
            warnings.append(f"Missing {len(missing_accounts)} service account files: {missing_accounts[:5]}...")
    
    # Check Google Cloud Project ID
    if not GOOGLE_CLOUD_PROJECT_ID:
        warnings.append("GOOGLE_CLOUD_PROJECT_ID not set")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "total_accounts_configured": TOTAL_SERVICE_ACCOUNTS - len(missing_accounts),
        "parallel_processing_enabled": ENABLE_PARALLEL_PROCESSING
    }

# Configuration summary
def print_config_summary():
    """Print configuration summary for debugging"""
    print("=== EUDR API Configuration ===")
    print(f"Service Account Path: {EE_SERVICE_ACCOUNT_PATH}")
    print(f"Total Service Accounts: {TOTAL_SERVICE_ACCOUNTS}")
    print(f"Parallel Processing: {ENABLE_PARALLEL_PROCESSING}")
    print(f"Default Parallel Accounts: {DEFAULT_PARALLEL_ACCOUNTS}")
    print(f"Google Cloud Project: {GOOGLE_CLOUD_PROJECT_ID or 'Not set'}")
    print(f"Daily Quota per Account: {EE_DAILY_QUOTA_PER_ACCOUNT:,}")
    print(f"Log Level: {LOG_LEVEL}")
    
    validation = validate_config()
    print(f"\nConfiguration Status: {'✅ Valid' if validation['valid'] else '❌ Issues Found'}")
    print(f"Accounts Configured: {validation['total_accounts_configured']}/{TOTAL_SERVICE_ACCOUNTS}")
    
    if validation['issues']:
        print("\nIssues:")
        for issue in validation['issues']:
            print(f"  ❌ {issue}")
    
    if validation['warnings']:
        print("\nWarnings:")
        for warning in validation['warnings']:
            print(f"  ⚠️  {warning}")
    
    print("=" * 35)

if __name__ == "__main__":
    print_config_summary()
