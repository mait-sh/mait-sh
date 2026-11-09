# Beta notice

MAIT is in beta. By using the beta builds you accept the following.

## Things change

Features, commands, options and settings can change or disappear without notice, between any two builds. Configuration, data formats and command output can change in ways that are not backwards compatible.

## Agents act on your behalf

MAIT starts environments in which agents run commands and handle credentials, such as the Git, Docker and cloud sign-ins you share into a project container.

- Do not use MAIT on machines, accounts or data you cannot afford to lose.
- Review what you share into a container (folders, credentials, network access) before you start an agent there.
- Review what an agent did before you rely on it. Discarding a container does not undo what was already done outside it, such as a change pushed to a remote system.

## Some documented features are not available yet

Some features in the documentation are marked as in progress. They may be missing, incomplete or available only to some accounts.

## No guarantee

There is no guarantee of availability, support or response time. Issues and messages are handled on a best-effort basis. The beta builds are provided as is, without warranty of any kind; see [LICENSE](LICENSE).

## Supported platforms

- Linux
- macOS on Apple Silicon
- Windows with WSL 2

Intel Macs are not supported.

The MAIT Team
