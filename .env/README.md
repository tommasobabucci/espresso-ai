# .env — Secrets & API Keys

> ⚠️ NEVER commit this folder to version control. Add `.env/` to `.gitignore`.

This folder contains all API keys and secrets required by the espresso.ai pipeline.
Store each service's credentials in its own file for modularity.

---

## Required Keys

### `anthropic.env`
```
ANTHROPIC_API_KEY=sk-ant-...
```
Used by: All Claude API calls in the pipeline
Get yours: https://console.anthropic.com/

### `news_sources.env`
```
NEWSAPI_KEY=...
PERPLEXITY_API_KEY=pplx-...
GDELT_API_KEY=...       # If applicable
```
Used by: `news-collector` agent
Get yours:
- NewsAPI: https://newsapi.org/
- Perplexity: https://www.perplexity.ai/settings/api

### `linkedin.env`
```
LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=...
LINKEDIN_ACCESS_TOKEN=...
```
Used by: Future LinkedIn auto-posting feature
Get yours: https://developer.linkedin.com/

### `storage.env`
```
# If using cloud storage for research_db backups
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
S3_BUCKET_NAME=espresso-ai-research
```

---

## Usage in Pipeline

Reference env variables in scripts like:
```python
import os
api_key = os.getenv("ANTHROPIC_API_KEY")
```

Or load from file:
```python
from dotenv import load_dotenv
load_dotenv(".env/anthropic.env")
```

---

## Security Notes

- Never log or print API keys
- Rotate keys if you suspect exposure
- Use environment-specific keys (dev vs. prod)
- Consider using a secrets manager for production (AWS Secrets Manager, 1Password)
