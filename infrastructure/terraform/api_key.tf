# API Key Generation
# Generates a secure API key using Terraform's random provider
# The key is stored in Terraform state and passed to Lambda as an environment variable

# Generate a random API key
resource "random_password" "api_key" {
  length  = 32
  special = true
  # Use URL-safe characters similar to secrets.token_urlsafe()
  override_special = "-_"

  # Ensure the key is recreated if it's manually tainted
  keepers = {
    # Change this value to force regeneration
    version = "1"
  }
}

# Output the key (marked as sensitive)
# To view: terraform output -raw api_key
output "api_key" {
  description = "Generated API key for write operations (sensitive)"
  value       = random_password.api_key.result
  sensitive   = true
}
