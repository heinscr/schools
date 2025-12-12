# Migration to AWS Cognito Authentication

## Summary

This document summarizes the migration from API key authentication to AWS Cognito JWT authentication for the MA Teachers Contracts application.

## What Changed

### 1. Infrastructure (Terraform)

**New File**: `infrastructure/terraform/cognito.tf`
- Created Cognito User Pool for user management
- Created User Pool Client for frontend application
- Created Hosted UI domain for login/logout
- Created "admins" user group for write permissions
- Configured OAuth 2.0 flows and JWT settings

**Updated**: `infrastructure/terraform/main.tf`
- Added Cognito environment variables to Lambda function
- Kept API_KEY for backward compatibility during migration

**Updated**: `infrastructure/terraform/frontend_config.tf`
- Added Cognito configuration to runtime config.json
- Frontend can now discover Cognito settings dynamically

### 2. Backend Changes

**New File**: `backend/cognito_auth.py`
- JWT token validation using Cognito public keys
- User information extraction from JWT claims
- Role-based access control (admin vs regular users)
- Three dependency functions:
  - `require_cognito_auth()` - Requires valid authentication
  - `require_admin_role()` - Requires admin group membership
  - `get_current_user_optional()` - Optional authentication

**Updated**: `backend/main.py`
- Replaced `require_api_key` with `require_admin_role` on write endpoints
- Added `/api/auth/me` endpoint to check current user status
- Kept API key support for backward compatibility

**Updated**: `backend/requirements.txt`
- Added `python-jose[cryptography]==3.3.0` for JWT validation
- Added `requests==2.31.0` for fetching Cognito public keys

**Updated**: `backend/.env.example`
- Added Cognito configuration variables

### 3. Frontend Changes

**New File**: `frontend/src/services/auth.js`
- Authentication service for Cognito integration
- Token storage and management (localStorage)
- OAuth callback handling
- Login/logout functions
- Admin status checking

**New File**: `frontend/src/components/Login.jsx`
- User login button component
- User menu with email and admin badge
- Dropdown with logout option
- Handles OAuth redirect flow

**New File**: `frontend/src/components/Login.css`
- Styling for login button and user menu

**Updated**: `frontend/src/App.jsx`
- Added Login component to header
- Pass user authentication state to DistrictBrowser
- Positioned login button in upper right corner

**Updated**: `frontend/src/App.css`
- Positioned authentication UI in header

**Updated**: `frontend/src/components/DistrictBrowser.jsx`
- Accept `user` prop
- Calculate `isAdmin` from user data
- Conditionally show wrench icon only for admins
- Pass `user` to DistrictEditor

**Updated**: `frontend/src/services/api.js`
- Import auth service
- Add `_getAuthHeaders()` method
- Include Authorization header in write operations
- Better error messages for auth failures

**Updated**: `frontend/.env.example`
- Added Cognito configuration for local development

### 4. Documentation

**New File**: `docs/AUTHENTICATION.md`
- Comprehensive authentication documentation
- Setup instructions
- User management guide
- API usage examples
- Troubleshooting guide

**New File**: `docs/COGNITO_MIGRATION.md` (this file)
- Migration summary and deployment steps

## Deployment Steps

### Step 1: Deploy Infrastructure

```bash
cd infrastructure/terraform

# Review changes
terraform plan

# Deploy Cognito resources
terraform apply
```

Expected new resources:
- `aws_cognito_user_pool.main`
- `aws_cognito_user_pool_client.frontend`
- `aws_cognito_user_pool_domain.main`
- `aws_cognito_user_group.admins`

### Step 2: Create Admin Users

```bash
# Get Cognito User Pool ID
USER_POOL_ID=$(terraform output -raw cognito_user_pool_id)

# Create your admin user
aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username your-email@example.com \
  --user-attributes Name=email,Value=your-email@example.com Name=email_verified,Value=true \
  --temporary-password "TempPassword123!" \
  --message-action SUPPRESS

# Add to admins group
aws cognito-idp admin-add-user-to-group \
  --user-pool-id $USER_POOL_ID \
  --username your-email@example.com \
  --group-name admins
```

### Step 3: Deploy Backend

The backend code will be deployed automatically via the existing deployment pipeline:

```bash
# From project root
./infrastructure/scripts/deploy.sh
```

The Lambda function will receive Cognito configuration via environment variables set by Terraform.

### Step 4: Deploy Frontend

The frontend will receive Cognito configuration from the runtime `config.json`:

```bash
cd frontend
npm run build

# Deploy to S3 (via existing deployment script)
cd ../infrastructure/scripts
./deploy.sh
```

### Step 5: Test Authentication

1. Visit your CloudFront URL
2. Click "Login" button in upper right
3. Login with your admin credentials
4. Change temporary password if prompted
5. You should see:
   - Your email displayed
   - Red "Admin" badge
   - Wrench icons on district items

6. Test editing a district to verify authentication works

## Rollback Plan

If issues arise, you can rollback by:

1. **Revert Backend Code**:
   ```bash
   git revert <commit-hash>
   ./infrastructure/scripts/deploy.sh
   ```

2. **Revert Frontend Code**:
   ```bash
   git revert <commit-hash>
   cd frontend && npm run build
   # Deploy frontend
   ```

3. **Keep Cognito Resources**: Cognito resources don't interfere with API key authentication, so they can remain deployed


## Monitoring

After deployment, monitor:

1. **CloudWatch Logs** for authentication errors
2. **Cognito Metrics** for login failures
3. **API Gateway Metrics** for 401/403 responses
4. **User Feedback** for login issues

## Security Considerations

✅ **Implemented**:
- JWT signature validation
- Token expiration checking
- Role-based access control (admin group)
- HTTPS for token transmission (via CloudFront)
- Rate limiting on write endpoints

🔜 **Future Enhancements**:
- httpOnly cookies instead of localStorage
- Refresh token rotation
- Multi-factor authentication (MFA)
- Session management and revocation

## Support

For issues or questions:

1. Check [AUTHENTICATION.md](./AUTHENTICATION.md) for detailed docs
2. Review CloudWatch logs for error messages
3. Test with `terraform output` values to verify configuration
4. Use AWS Cognito console to inspect user pool settings

## Validation Checklist

After deployment, verify:

- [ ] Terraform apply completed successfully
- [ ] Admin user created and added to admins group
- [ ] Backend deployed with Cognito environment variables
- [ ] Frontend deployed with updated code
- [ ] Can access application homepage
- [ ] Login button appears in upper right
- [ ] Can click login and redirect to Cognito
- [ ] Can login with admin credentials
- [ ] User email and badge display after login
- [ ] Wrench icons appear on districts
- [ ] Can edit a district successfully
- [ ] Wrench icons hidden when not logged in
- [ ] GET endpoints work without authentication
- [ ] POST/PUT/DELETE endpoints require authentication

## Estimated Downtime

**Zero downtime migration**:
- Cognito resources created independently
- Backend supports both auth methods
- Frontend gracefully handles missing Cognito config
- Existing API functionality unchanged

## Cost Impact

New AWS costs:
- Cognito User Pool: $0.0055 per MAU (Monthly Active User)
- First 50,000 MAUs free
- Expected cost: ~$0-5/month for typical usage

## Questions?

Contact the development team or refer to:
- [AWS Cognito Pricing](https://aws.amazon.com/cognito/pricing/)
- [AWS Cognito Documentation](https://docs.aws.amazon.com/cognito/)
