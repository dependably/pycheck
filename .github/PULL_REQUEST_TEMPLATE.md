# Pull Request

## Summary

Brief description of the changes made in this PR.

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Performance improvement
- [ ] Code refactoring

## Description

Provide a more detailed explanation of your changes and the reasoning behind them.

## Related Issues

Closes #(issue number)
Relates to #(issue number)

## Technical Changes

### Code Changes
- [ ] Modified existing functionality
- [ ] Added new functions/classes
- [ ] Changed CLI interface
- [ ] Updated configuration handling
- [ ] Modified AST analysis logic

### Files Modified
List the key files that were changed and why:

- `src/checker.py`: Brief description of changes
- `tests/test_*.py`: Brief description of test updates

## Testing

### Test Coverage
- [ ] I have added unit tests for new functionality
- [ ] I have added integration tests for end-to-end workflows  
- [ ] I have updated existing tests to reflect changes
- [ ] All new and existing tests pass locally

### Manual Testing
Describe the testing you performed:

```bash
# Commands used for testing
python src/checker.py --check tests/
python src/checker.py --cleanup tests/test_basic_unused.py
```

### Test Results
- [ ] Tested on Python 3.7
- [ ] Tested on Python 3.8+
- [ ] Tested on Linux
- [ ] Tested on macOS
- [ ] Tested on Windows
- [ ] Tested with various file types and import patterns

## Code Quality

### Formatting and Linting
- [ ] Code follows PEP 8 style guidelines
- [ ] `black src/ tests/` passes without changes
- [ ] `flake8 src/ tests/` passes without errors
- [ ] `mypy src/` passes without errors
- [ ] All functions have appropriate type hints
- [ ] All public functions have docstrings

### Code Review Checklist
- [ ] Code is self-documenting with clear variable names
- [ ] Functions follow single responsibility principle
- [ ] Error handling is appropriate and informative
- [ ] No hardcoded values (use constants or configuration)
- [ ] Performance impact is acceptable
- [ ] Security implications have been considered

## Documentation

- [ ] README.md updated if CLI interface changed
- [ ] CONTRIBUTING.md updated if development process changed
- [ ] Code comments added for complex logic
- [ ] Docstrings updated for modified functions
- [ ] CHANGELOG.md updated (if applicable)

## Backward Compatibility

- [ ] Changes are backward compatible
- [ ] If breaking changes exist, they are documented
- [ ] Migration path provided for breaking changes
- [ ] Version number updated appropriately

## Performance Impact

Describe any performance implications:

- [ ] No performance impact
- [ ] Performance improved
- [ ] Performance regression (justified and documented)
- [ ] Performance impact unknown/not measured

## Security Considerations

- [ ] No security implications
- [ ] Security implications reviewed and addressed
- [ ] No new external dependencies introduced
- [ ] Input validation added where appropriate

## Additional Notes

Any additional information that reviewers should know:

### Screenshots (if applicable)

### Testing Instructions for Reviewers

Specific instructions for testing this PR:

1. Clone the PR branch
2. Run: `python src/checker.py --check tests/`
3. Verify: Expected output matches...
4. Test edge case: ...

### Areas for Special Review

Please pay special attention to:

- [ ] AST parsing logic changes
- [ ] Import analysis accuracy
- [ ] Error handling improvements
- [ ] CLI interface modifications
- [ ] Configuration file handling

---

**Checklist Summary:**
- [ ] All tests pass
- [ ] Code quality checks pass (black, flake8, mypy)
- [ ] Documentation updated
- [ ] Backward compatibility maintained
- [ ] Security considerations addressed
- [ ] Performance impact assessed