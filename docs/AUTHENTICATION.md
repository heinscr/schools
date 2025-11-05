# Authentication Setup

This application uses AWS Cognito for user authentication and authorization. Only authenticated administrators can create, update, or delete school districts.

## Overview

- **Authentication Provider**: AWS Cognito User Pools
- **Authentication Method**: JWT (JSON Web Tokens) via OAuth 2.0
- **Protected Operations**: POST, PUT, DELETE on `/api/districts` endpoints
- **Public Operations**: GET requests (browse districts, view salary data)

## Architecture

### Backend Authentication

The backend FastAPI application validates JWT tokens from AWS Cognito:

1. **Token Validation**: The `cognito_auth.py` module fetches Cognito public keys and validates JWT signatures
2. **User Extraction**: Extracts user information and groups from validated tokens
3. **Role-Based Access**: Checks if user belongs to the "admins" group
4. **Protected Endpoints**: POST/PUT/DELETE operations require `require_admin_role()` dependency

### Frontend Authentication

The frontend React application handles user login and token management:

1. **Cognito Hosted UI**: Redirects users to AWS Cognito for login
2. **Token Storage**: Stores JWT tokens in localStorage
3. **Automatic Headers**: Includes `Authorization: Bearer <token>` header in write operations
4. **Conditional UI**: Shows/hides edit buttons based on admin status

## Terraform Infrastructure

The Cognito resources are defined in `infrastructure/terraform/cognito.tf`:

- **User Pool**: Manages user accounts with email-based authentication
- **User Pool Client**: Frontend application client configuration
- **User Pool Domain**: Hosted UI domain for login/logout
- **Admin Group**: Group for users with write permissions

## Setting Up Authentication

### 1. Deploy Cognito Infrastructure

```bash
cd infrastructure/terraform
terraform init
terraform apply
```

This creates:
- Cognito User Pool
- Frontend application client
- Hosted UI domain
- Admin user group

### 2. Get Cognito Configuration

After deployment, get the configuration values:

```bash
terraform output cognito_user_pool_id
terraform output cognito_client_id
terraform output cognito_domain
terraform output cognito_issuer
```

### 3. Create Admin Users

Create user accounts via AWS Console or CLI:

```bash
# Create a user
aws cognito-idp admin-create-user \
  --user-pool-id <USER_POOL_ID> \
  --username admin@example.com \
  --user-attributes Name=email,Value=admin@example.com Name=email_verified,Value=true \
  --temporary-password "TempPassword123!" \
  --message-action SUPPRESS

# Add user to admins group
aws cognito-idp admin-add-user-to-group \
  --user-pool-id <USER_POOL_ID> \
  --username admin@example.com \
  --group-name admins
```

### 4. Local Development Setup

For local development, create a `.env` file in the backend directory:

```bash
# backend/.env
COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
COGNITO_REGION=us-east-1
```

For the frontend, create a `.env` file:

```bash
# frontend/.env
VITE_API_URL=http://localhost:8000
VITE_COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
VITE_COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
VITE_COGNITO_REGION=us-east-1
VITE_COGNITO_DOMAIN=your-app-xxxxx.auth.us-east-1.amazoncognito.com
```

## User Login Flow

1. User clicks "Login" button in the upper right corner
2. Redirected to Cognito Hosted UI
3. Enters credentials (email/password)
4. Cognito validates credentials and redirects back with JWT token in URL fragment
5. Frontend extracts token from URL and stores in localStorage
6. Frontend displays user email and admin badge (if applicable)
7. Edit buttons (wrench icons) appear for admin users

## API Usage

### Authenticated Requests

Include the JWT token in the Authorization header:

```bash
# Get current user info
curl -H "Authorization: Bearer <JWT_TOKEN>" \
  http://localhost:8000/api/auth/me

# Update a district (admin only)
curl -X PUT \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Updated District Name"}' \
  http://localhost:8000/api/districts/{district_id}
```

### Response to Unauthenticated Requests

```json
{
  "detail": "Authentication required. Please log in."
}
```

### Response to Non-Admin Requests

```json
{
  "detail": "Admin role required for this operation"
}
```

## Token Security

- **JWT Validation**: All tokens are validated using Cognito's public keys
- **Expiration**: ID tokens expire after 60 minutes
- **Refresh**: Access tokens can be refreshed using refresh tokens (valid for 30 days)
- **HTTPS Only**: Tokens should only be transmitted over HTTPS in production

## Troubleshooting

### "Invalid token" errors

- Check that COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID match between frontend and backend
- Verify token hasn't expired (60-minute lifetime)
- Ensure Cognito public keys are accessible from backend

### "Admin role required" errors

- Verify user is in the "admins" group:
  ```bash
  aws cognito-idp admin-list-groups-for-user \
    --user-pool-id <USER_POOL_ID> \
    --username user@example.com
  ```

### User can't log in

- Check user status: `CONFIRMED` vs `FORCE_CHANGE_PASSWORD`
- Verify email is verified
- Check password policy requirements

## Security Best Practices

1. **Use HTTPS**: Always use HTTPS in production to protect tokens
2. **Token Storage**: Tokens are stored in localStorage (consider httpOnly cookies for enhanced security)
3. **Token Refresh**: Implement token refresh logic to avoid frequent re-authentication
4. **Group Management**: Regularly audit admin group membership
5. **MFA**: Enable multi-factor authentication for admin accounts (optional but recommended)
6. **Rate Limiting**: Write operations are rate-limited to prevent abuse

## References

- [AWS Cognito Documentation](https://docs.aws.amazon.com/cognito/)
- [JWT.io](https://jwt.io/) - Decode and inspect JWT tokens
- [OAuth 2.0 Specification](https://oauth.net/2/)
