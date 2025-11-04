"""
Pytest configuration and fixtures for backend tests
"""
import os
import sys
from pathlib import Path

# Set environment variables before any modules are imported
# Use test-specific table names that don't conflict with real tables
os.environ["DYNAMODB_DISTRICTS_TABLE"] = "test-districts"
os.environ["SALARIES_TABLE_NAME"] = "test-salaries"
os.environ["SCHEDULES_TABLE_NAME"] = "test-schedules"
os.environ["DISTRICTS_TABLE_NAME"] = "test-districts"
os.environ["API_KEY"] = "test-api-key-for-unit-tests"

# Set high rate limits for testing to avoid hitting limits during test runs
os.environ["RATE_LIMIT_GENERAL"] = "1000/minute"
os.environ["RATE_LIMIT_SEARCH"] = "1000/minute"
os.environ["RATE_LIMIT_WRITE"] = "1000/minute"

# Set mock Cognito configuration for testing
# These values won't be used for actual authentication (we override the dependency)
# but they prevent errors when Cognito auth module is imported
os.environ["COGNITO_USER_POOL_ID"] = "us-east-1_TEST123456"
os.environ["COGNITO_CLIENT_ID"] = "test-client-id-123456789"
os.environ["COGNITO_REGION"] = "us-east-1"

# Add backend directory to path
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
