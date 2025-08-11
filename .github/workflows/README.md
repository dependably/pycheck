# GitHub Actions CI/CD Workflows

This directory contains the GitHub Actions workflows for the Python Library Checker project.

## Workflows Overview

### 🔄 CI Workflow (`ci.yml`)

**Triggers:** Push to main/develop, Pull Requests, Manual dispatch

**Jobs:**
- **Test Matrix**: Tests across Python 3.8-3.12 on Ubuntu, Windows, and macOS
- **Linting**: Code formatting (Black), linting (flake8), type checking (mypy)  
- **Security**: Dependency scanning (safety), security linting (bandit)
- **Build**: Package building and validation
- **Test Install**: Validates package installation across platforms

**Features:**
- Comprehensive test coverage with Codecov integration
- Dependency caching for faster builds
- Artifact upload for debugging
- Cross-platform compatibility testing

### 🚀 Release Workflow (`release.yml`)

**Triggers:** Git tags matching `v*.*.*`, Manual dispatch

**Process:**
1. Run full test suite and linting
2. Build and validate packages
3. Create GitHub release with assets
4. Publish to PyPI automatically
5. Test installation from PyPI across platforms

**Features:**
- Automatic release notes generation
- Pre-release detection for alpha/beta/rc versions
- PyPI publishing with trusted publishing (OIDC)
- Post-release validation testing

### 🛡️ Security Workflow (`security.yml`)

**Triggers:** Push to main, Pull Requests, Weekly schedule, Manual dispatch

**Scans:**
- **Safety**: Dependency vulnerability scanning
- **Bandit**: Python security linting
- **Semgrep**: Static analysis security scanning
- **CodeQL**: Advanced semantic code analysis

**Features:**
- Weekly automated security scans
- Security report artifacts
- GitHub Security Advisories integration

## Configuration Files

### `.codecov.yml`
- Coverage reporting configuration
- Target thresholds: 80% project, 80% patch
- Comment formatting and behavior settings

### `.github/dependabot.yml`
- Automated dependency updates
- Weekly schedule for Python packages and GitHub Actions
- Automatic PR creation with proper labeling

### Issue and PR Templates
- Structured bug reports with environment details
- Feature request templates with priority levels
- Pull request checklists for code quality

## Status Badges

The following badges are available for the README:

```markdown
[![CI](https://github.com/yourusername/python-library-checker/workflows/CI/badge.svg)](https://github.com/yourusername/python-library-checker/actions/workflows/ci.yml)
[![Release](https://github.com/yourusername/python-library-checker/workflows/Release/badge.svg)](https://github.com/yourusername/python-library-checker/actions/workflows/release.yml)
[![Security](https://github.com/yourusername/python-library-checker/workflows/Security/badge.svg)](https://github.com/yourusername/python-library-checker/actions/workflows/security.yml)
[![codecov](https://codecov.io/gh/yourusername/python-library-checker/branch/main/graph/badge.svg)](https://codecov.io/gh/yourusername/python-library-checker)
[![PyPI version](https://badge.fury.io/py/python-library-checker.svg)](https://badge.fury.io/py/python-library-checker)
[![Python versions](https://img.shields.io/pypi/pyversions/python-library-checker.svg)](https://pypi.org/project/python-library-checker/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
```

## Setup Requirements

### Repository Settings

1. **Secrets Configuration:**
   - No PyPI token needed (uses trusted publishing)
   - Codecov token (optional, for private repos)

2. **Branch Protection:**
   - Require status checks to pass
   - Require CI workflow completion
   - Require up-to-date branches

3. **Permissions:**
   - Contents: write (for releases)
   - Security-events: write (for CodeQL)
   - ID-token: write (for PyPI publishing)

### External Services

1. **Codecov.io:**
   - Sign up and connect repository
   - No token needed for public repos

2. **PyPI Trusted Publishing:**
   - Configure at https://pypi.org/manage/account/publishing/
   - Add GitHub Actions as trusted publisher

## Usage

### Running Workflows

**Manual CI run:**
```bash
gh workflow run ci.yml
```

**Manual release:**
```bash
# Create and push tag
git tag v1.0.1
git push origin v1.0.1

# Or trigger manually
gh workflow run release.yml -f version=v1.0.1
```

### Monitoring

- Check workflow status in Actions tab
- Monitor security alerts in Security tab
- Review coverage reports on Codecov
- Track dependency updates from Dependabot

## Troubleshooting

### Common Issues

**Failed PyPI publishing:**
- Verify trusted publishing configuration
- Check version conflicts on PyPI
- Ensure proper tagging format (v1.0.0)

**Test failures:**
- Check Python version compatibility
- Verify dependency installations
- Review platform-specific issues

**Security scan failures:**
- Update vulnerable dependencies
- Review security findings in artifacts
- Configure security policy if needed

### Getting Help

1. Review workflow logs in Actions tab
2. Check individual job outputs
3. Download workflow artifacts for detailed reports
4. Open issue with workflow run URL and error details