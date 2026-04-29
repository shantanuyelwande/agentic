---
name: data-extraction
description: Extract structured data from text - emails, phone numbers, URLs, company info, pricing. Use when you've scraped content and need to parse it into structured data.
---

# Data Extraction Skill

Use this skill when you need to extract emails, phone numbers, URLs, company information, or pricing data from text content you've scraped from websites.

## Available Functions

### extract_emails
Extracts email addresses from text using pattern matching.

```bash
python3 - <<'EOF'
import re
def extract_emails(text: str) -> list[str]:
    pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(pattern, text)
    return list(set(emails))

# Usage
text = "Contact: hello@example.com or support@example.io"
print(extract_emails(text))
EOF
```

### extract_urls
Finds all URLs (http/https) in text.

```bash
python3 - <<'EOF'
import re
def extract_urls(text: str) -> list[str]:
    pattern = r'https?://[^\s]+'
    urls = re.findall(pattern, text)
    return list(set(urls))

# Usage
text = "Visit https://example.com or https://docs.example.com"
print(extract_urls(text))
EOF
```

### extract_company_info
Combines multiple extraction patterns to get company details: emails, phones, URLs, company names.

```bash
python3 - <<'EOF'
import re
def extract_company_info(text: str) -> dict:
    info = {
        "emails": [],
        "phone_numbers": [],
        "urls": [],
    }
    
    # Emails
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    info["emails"] = list(set(re.findall(email_pattern, text)))
    
    # URLs
    url_pattern = r'https?://[^\s]+'
    info["urls"] = list(set(re.findall(url_pattern, text)))
    
    # Company names
    company_pattern = r'(?:Company|Inc|LLC|Corp):?\s+([A-Z][A-Za-z\s&,.-]*)'
    matches = re.findall(company_pattern, text)
    if matches:
        info["company_names"] = matches
    
    return info

# Usage
text = "Contact TechCorp Inc at hello@techcorp.com or visit https://techcorp.com"
print(extract_company_info(text))
EOF
```

### parse_pricing
Extracts pricing information: tiers, prices, and currency.

```bash
python3 - <<'EOF'
import re
def parse_pricing(text: str) -> dict:
    pricing = {
        "tiers": [],
        "prices": [],
        "currency": "USD",
    }
    
    # Find dollar amounts
    amounts = re.findall(r'\$[\d,]+(?:\.\d{2})?', text)
    if amounts:
        pricing["prices"] = list(set(amounts))
    
    # Find tier keywords
    tier_keywords = ["starter", "basic", "pro", "enterprise", "premium", "free"]
    found_tiers = []
    for keyword in tier_keywords:
        if keyword.lower() in text.lower():
            found_tiers.append(keyword.capitalize())
    
    if found_tiers:
        pricing["tiers"] = found_tiers
    
    return pricing

# Usage
text = "Pricing: Free plan, Starter $99/month, Pro $299/month, Enterprise custom"
print(parse_pricing(text))
EOF
```

## Example Workflow

1. **Scrape content** from a website using browser tools
2. **Run extraction** functions on the scraped text
3. **Return structured data** for further processing

```bash
# Get text from a file
TEXT=$(cat company_data.txt)

# Extract all contact info
python3 - <<'EOF'
import re
text = """$TEXT"""

emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
urls = re.findall(r'https?://[^\s]+', text)

print(f"Found {len(emails)} emails: {emails}")
print(f"Found {len(urls)} URLs: {urls}")
EOF
```

## When to Use

- ✅ After scraping a website and need structured data
- ✅ Parsing contact information from text
- ✅ Extracting pricing from pricing pages
- ✅ Finding company websites and contact methods
- ❌ For live interaction with pages (use browser tools instead)
- ❌ For executing JavaScript (use browser tools instead)
