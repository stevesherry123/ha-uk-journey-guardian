# Security Policy

## Reporting a vulnerability

Please do not publish credentials, calendar contents, addresses, entity IDs, or
other private installation details in a public issue.

Use GitHub's private vulnerability reporting feature when it is enabled for the
repository. Otherwise, open a public issue containing no sensitive information
and ask the maintainer for a private contact route.

## Credential handling

UK Journey Guardian stores provider credentials in Home Assistant config entries.
The integration must not expose credentials through entity state, logs, service
responses, tests, fixtures, or downloaded diagnostics.
