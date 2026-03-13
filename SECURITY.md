# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Draft, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please email security concerns to: **amirdor@gmail.com**

Include:
- A description of the vulnerability
- Steps to reproduce the issue
- Potential impact
- Suggested fix (if any)

## Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial assessment**: Within 1 week
- **Fix timeline**: Depends on severity, typically within 2 weeks for critical issues

## Scope

The following are in scope:
- Authentication and authorization bypasses
- SQL injection or command injection
- Cross-site scripting (XSS)
- Sensitive data exposure
- Privilege escalation

The following are out of scope:
- Issues in third-party dependencies (report upstream)
- Denial of service attacks
- Social engineering

## Security Best Practices for Deployment

- Always set `AUTH_SECRET_KEY` to a strong random value in production
- Set `APP_ENV=production` to disable debug endpoints
- Use HTTPS in production (configure via reverse proxy)
- Keep dependencies up to date
