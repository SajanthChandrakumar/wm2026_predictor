# Security Audit Report — WM 2026 Predictor

**Date:** June 22, 2026  
**Status:** Pre-deployment Security Hardening

## Summary

Comprehensive security audit completed. **15 issues identified** across critical, high, medium, and informational severity levels.

### Issues Fixed in This Branch

✅ **CRITICAL (2/2 Fixed)**
- Added missing `fastapi` and `uvicorn` dependencies to requirements.txt
- Added `timeout=10` to all external API requests (odds_engine.py)

✅ **HIGH (2/2 Fixed)**
- Generic error messages instead of exposing internal exception details
- All error details now logged server-side only

✅ **MEDIUM (5 items — 3/5 Fixed)**
- Rate limiting added: 20/min on `/api/predict`, 30/min on `/api/archive/user_tip`, 5/hour on `/api/sync_elo`
- CORS origins now environment-configurable via `CORS_ORIGINS` env var
- Security headers added: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy, CSP
- ⚠️ CSRF protection: still needs implementation (add CSRF token validation)
- ⚠️ Input validation: score ranges not enforced (recommended enhancement)

## Remaining Issues (Before Production)

### Medium Priority
- **CSRF Protection:** Implement CSRF token validation on POST endpoints
  - Use `fastapi-csrf-protect` library or validate custom headers
  
- **Score Validation:** Enforce reasonable limits (e.g., max 20 goals per team)
  - Check user_tip values in `/api/archive/user_tip` endpoint

### Low Priority
- **XSS in onclick attributes:** Consider migrating from inline onclick to addEventListener
- **Unvalidated match_id:** Add format validation on archive operations
- **Archive backup:** Implement backup/version control for prediction_archive.json

### Informational
- Add structured logging with timestamps and event types
- Lock dependency versions in requirements.lock
- Consider database (SQLite) instead of JSON files for archive

## Environment Variables

For production deployment, set:

```bash
CORS_ORIGINS=https://yourdomain.com
```

Default (development):
```bash
CORS_ORIGINS=http://localhost:3000
```

## Deployment Checklist

- [ ] Set appropriate `CORS_ORIGINS` for production domain
- [ ] Implement CSRF protection (optional but recommended)
- [ ] Add score validation limits (optional)
- [ ] Run dependency security check: `pip-audit`
- [ ] Enable HTTPS in production
- [ ] Set up proper error logging and monitoring
- [ ] Implement backup strategy for prediction_archive.json
- [ ] Review FastAPI security docs: https://fastapi.tiangolo.com/deployment/concepts/https/

## Testing

After deployment, verify:

1. Security headers present in response:
   ```bash
   curl -I https://yourdomain.com
   ```

2. Rate limiting working:
   ```bash
   for i in {1..25}; do curl -X POST https://yourdomain.com/api/predict; done
   ```

3. CORS properly restricted:
   ```bash
   curl -H "Origin: https://evil.com" https://yourdomain.com
   ```
