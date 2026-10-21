# Pull Request

## Summary

<!-- Briefly explain what this pull request changes. -->

## Related issue

<!-- Link the issue, for example: Closes #12 -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Pi-hole version compatibility improvement
- [ ] Refactoring or code quality improvement
- [ ] Documentation update
- [ ] Other

## Changes made

<!-- Describe the important changes and their impact. -->

-
-
-

## Testing performed

- [ ] `make check` passes (tests, flake8, Python 3.7 compatibility).
- [ ] Tests added or updated for the change.
- [ ] Plugin startup tested in Domoticz, where possible.
- [ ] Existing devices (units 1-10, lists from 100, groups from 200) still update correctly, where applicable.
- [ ] Error handling and logging reviewed.
- [ ] `CHANGELOG.md` updated under `Unreleased`; documentation updated, where necessary.

### Test environment

- **Plugin version / branch:**
- **Pi-hole version (core, FTL, web):**
- **Domoticz version:**
- **Operating system / Python:**

### Test results

<!-- Describe what you tested and the results. If testing was not possible, explain why. -->

## Compatibility and limitations

<!-- Describe Pi-hole version differences, migration considerations, or untested functionality. -->

## Security and privacy

- [ ] No passwords, app passwords, session ids, or other secrets are included.
- [ ] No private host names, IP addresses, client names or block-list contents are included.
- [ ] Logs, screenshots, and test data have been reviewed and redacted.

## Checklist

- [ ] This pull request targets the `development` branch.
- [ ] I followed the rules in `CONTRIBUTING.md` (only `plugin.py` imports `Domoticz`, only `devices.py` calls the device API, no third-party packages, device model unchanged).
- [ ] My changes are focused and do not contain unrelated modifications.
- [ ] I have not included generated files or temporary development artifacts unnecessarily.
- [ ] I have documented any tests I could not perform.

## Additional notes

<!-- Anything else the maintainer should know before reviewing this pull request? -->
