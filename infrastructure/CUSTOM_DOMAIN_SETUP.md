# Custom Domain Setup for CloudFront

This guide explains how to configure a custom domain with SSL certificate for your CloudFront distribution.

## Prerequisites

1. **A domain name** that you own (e.g., `example.com`)
2. **An SSL certificate in AWS Certificate Manager (ACM)** in the **us-east-1 region**
   - CloudFront requires certificates to be in us-east-1, regardless of where your other resources are
3. **Access to your domain's DNS settings** (to create CNAME records)

## Step 1: Get or Create an ACM Certificate

### If you already have a certificate:

1. Go to AWS Certificate Manager in the **us-east-1** region
2. Find your certificate
3. Copy the ARN (it looks like: `arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012`)

### If you need to create a new certificate:

```bash
# Make sure you're in us-east-1
aws acm request-certificate \
  --domain-name www.example.com \
  --subject-alternative-names example.com \
  --validation-method DNS \
  --region us-east-1
```

Then validate the certificate by adding the DNS records shown in ACM console.

## Step 2: Update terraform.tfvars

Edit your `terraform.tfvars` file and add:

```hcl
# CloudFront Custom Domain
cloudfront_domain_name     = "www.example.com"
cloudfront_certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/xxxxx"
cloudfront_aliases         = ["example.com"]  # Optional: additional domains
```

### Examples:

**Single domain (www only):**
```hcl
cloudfront_domain_name     = "www.example.com"
cloudfront_certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/xxxxx"
cloudfront_aliases         = []
```

**Multiple domains (www and apex):**
```hcl
cloudfront_domain_name     = "www.example.com"
cloudfront_certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/xxxxx"
cloudfront_aliases         = ["example.com"]  # Apex domain
```

**Subdomain:**
```hcl
cloudfront_domain_name     = "app.example.com"
cloudfront_certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/xxxxx"
cloudfront_aliases         = []
```

## Step 3: Apply Terraform

```bash
cd infrastructure/terraform
terraform plan   # Review changes
terraform apply  # Apply changes
```

Terraform will output the CloudFront domain name (e.g., `d111111abcdef8.cloudfront.net`)

## Step 4: Update DNS Records

Add CNAME records in your DNS provider pointing to the CloudFront domain:

### Example DNS Records:

**Route 53:**
```hcl
# If using Route 53, you can add this to your Terraform:
resource "aws_route53_record" "www" {
  zone_id = "Z1234567890ABC"  # Your hosted zone ID
  name    = "www.example.com"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id               = aws_cloudfront_distribution.frontend.hosted_zone_id
    evaluate_target_health = false
  }
}
```

**Other DNS Providers (Cloudflare, Namecheap, etc.):**
```
Type: CNAME
Name: www
Value: d111111abcdef8.cloudfront.net
TTL: 3600
```

**For apex domain (example.com without www):**
- Some DNS providers support ALIAS or ANAME records (Cloudflare, Route 53)
- Otherwise, use URL redirect from apex to www

## Step 5: Test

1. Wait for DNS propagation (can take 5-48 hours, usually < 1 hour)
2. Test your domain:
   ```bash
   curl -I https://www.example.com
   ```
3. Visit in browser: `https://www.example.com`

## Troubleshooting

### Error: "Certificate ARN is required"
- Make sure you set both `cloudfront_domain_name` and `cloudfront_certificate_arn`

### Error: "Certificate must be in us-east-1"
- CloudFront only works with certificates in the us-east-1 region
- Create a new certificate in us-east-1 or copy your existing one

### DNS not resolving
- Check DNS propagation: `dig www.example.com` or use https://dnschecker.org
- Verify CNAME points to the correct CloudFront domain
- Wait longer (DNS can take time)

### SSL Certificate Error
- Ensure the certificate includes all domains in `cloudfront_aliases`
- Certificate must be validated (Status: Issued in ACM)
- Certificate must include the exact domain names you're using

### CloudFront Access Denied
- Check CloudFront distribution status (must be "Deployed")
- Verify S3 bucket policy allows CloudFront access
- Check origin settings

## Reverting to Default CloudFront Domain

To remove custom domain and use default CloudFront domain:

```hcl
cloudfront_domain_name     = ""
cloudfront_certificate_arn = ""
cloudfront_aliases         = []
```

Then run:
```bash
terraform apply
```

## Cost Implications

- ACM certificates are **FREE**
- CloudFront pricing is the same whether using custom domain or default domain
- Route 53 hosted zone: ~$0.50/month (if using Route 53)

## Security Notes

1. Always use HTTPS (SSL/TLS)
2. Certificate must be validated and active
3. Use TLS 1.2 or higher (already configured)
4. CloudFront automatically handles SSL/TLS termination
