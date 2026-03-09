# Security Documentation

This directory contains security policies, audit reports, and guidelines for the OpenClaw Backend project.

## Contents

### Audit Reports
- **[dependency-audit-2026-03-09.md](./dependency-audit-2026-03-09.md)** - Complete dependency security audit (March 2026)

### Security Policies
- Coming soon: Vulnerability disclosure policy
- Coming soon: Security incident response plan
- Coming soon: Access control guidelines

## Quick Reference

### Current Security Status
- **Last Audit:** March 9, 2026
- **Next Audit:** June 9, 2026
- **Risk Level:** MEDIUM
- **Known Issues:** 1 (ecdsa CVE-2024-23342 - risk accepted)

### Key Security Packages
| Package | Version | Status | Notes |
|---------|---------|--------|-------|
| cryptography | 46.0.5 | ✅ Current | Critical - Ed25519, TLS |
| fastapi | 0.135.1 | ✅ Current | Web framework |
| pydantic | 2.12.5 | ✅ Current | Data validation |
| sqlalchemy | 2.0.48 | ✅ Current | ORM layer |
| python-jose | 3.5.0 | ⚠️ Stable | Brings in ecdsa dependency |
| ecdsa | 0.19.1 | ⚠️ Known CVE | CVE-2024-23342 (no fix) |

### Vulnerability Summary
- **Total Packages:** 98
- **With CVEs:** 1 (ecdsa)
- **Outdated (>2 years):** 0
- **Security Updates Available:** 0

## Running Security Audits

### Manual Audit
```bash
# Install audit tools
pip install pip-audit safety

# Run pip-audit
pip-audit --requirement requirements.txt --desc on

# Run safety check
safety scan --json

# Check for outdated packages
pip list --outdated
```

### Automated CI/CD
Security audits run automatically:
- **On every PR:** Full security scan
- **Weekly:** Scheduled comprehensive audit
- **Daily:** Dependabot checks for updates

See `.github/workflows/security-audit.yml` for configuration.

## Dependency Management

### Update Policy
| Severity | Response Time | Process |
|----------|--------------|---------|
| CRITICAL | 24 hours | Emergency patch deployment |
| HIGH | 7 days | Expedited update + testing |
| MEDIUM | 30 days | Standard update cycle |
| LOW | Next release | Batched with routine updates |

### Version Pinning
All dependencies use exact version pins (`==`) in `requirements.txt`:
- Ensures reproducible builds
- Prevents unexpected breaking changes
- Facilitates security audit tracking

### Dependabot
Automated dependency updates via `.github/dependabot.yml`:
- Security updates: Daily checks, individual PRs
- Minor/patch updates: Weekly, grouped PRs
- Major updates: Ignored (require manual review)

## Known Security Issues

### 1. ecdsa CVE-2024-23342 (ACCEPTED RISK)
**Impact:** Minerva timing attack on ECDSA operations
**Status:** No fix available (maintainer considers out-of-scope)
**Mitigation:**
- Transitive dependency via python-jose
- Risk low for cloud deployments
- JWT operations over TLS only
- Rate limiting on auth endpoints

**Reevaluation:** Quarterly (next: June 2026)

See [full audit report](./dependency-audit-2026-03-09.md#critical-ecdsa-0191---minerva-timing-attack) for details.

## Security Best Practices

### For Developers
1. **Never commit secrets** - Use environment variables
2. **Review dependency changes** - Check Dependabot PRs carefully
3. **Run audits locally** before pushing: `pip-audit`
4. **Update security docs** when adding dependencies
5. **Test security updates** in staging before production

### For Operations
1. **Deploy over TLS/SSL** - All network traffic encrypted
2. **Rotate secrets regularly** - JWT keys, DB credentials, API tokens
3. **Monitor auth patterns** - Detect brute force and timing attacks
4. **Keep audit logs** - 90-day retention for security events
5. **Incident response plan** - Document and practice procedures

### For Security Team
1. **Quarterly audits** - Full dependency review every 90 days
2. **CVE monitoring** - Subscribe to security advisories
3. **Penetration testing** - Annual third-party assessment
4. **SBOM tracking** - Maintain software bill of materials
5. **Compliance reviews** - SOC2, GDPR, HIPAA as applicable

## Security Tools

### Installed in Development
- **pip-audit** 2.10.0 - OSV database vulnerability scanner
- **safety** 3.7.0 - Safety DB CVE checker
- **bandit** (optional) - Python code security analyzer
- **semgrep** (optional) - Static analysis security testing

### GitHub Integrations
- **Dependabot** - Automated dependency updates
- **CodeQL** (optional) - Code scanning for vulnerabilities
- **Secret Scanning** - Prevent credential leaks
- **Security Advisories** - Private vulnerability coordination

## Reporting Security Issues

### Internal Team
1. Create private security advisory on GitHub
2. Tag @security-team and @backend-team
3. Include reproduction steps and impact assessment
4. Follow incident response procedures

### External Researchers
Please report vulnerabilities responsibly:
- **Email:** security@ainative.studio
- **Response Time:** 48 hours acknowledgment
- **Disclosure:** 90-day coordinated disclosure

Do not publicly disclose until:
1. Issue is confirmed and patched
2. Security advisory is published
3. Affected deployments are updated

## Compliance & Attestation

### Security Attestations
- Dependencies audited quarterly
- SBOM generated for each release
- License compliance verified
- No GPL/AGPL in production dependencies

### Certifications
- TODO: SOC 2 Type II
- TODO: ISO 27001
- TODO: GDPR compliance documentation

## Resources

### External Links
- [NIST National Vulnerability Database](https://nvd.nist.gov/)
- [Python Security Advisories](https://github.com/pypa/advisory-database)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE/SANS Top 25](https://cwe.mitre.org/top25/)

### Internal Documentation
- [Architecture Documentation](../ARCHITECTURE.md)
- [Deployment Guide](../DEPLOYMENT.md)
- [CLAUDE.md](../../CLAUDE.md) - Project overview

## Change Log

| Date | Event | By |
|------|-------|-----|
| 2026-03-09 | Initial security audit and policy setup | AI DevOps |
| TBD | Next quarterly audit | TBD |

---

**Last Updated:** March 9, 2026
**Next Review:** June 9, 2026
**Maintained By:** Security Team & Backend Team
