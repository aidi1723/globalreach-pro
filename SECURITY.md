# Security Policy

## Supported Status

This project has been published as GPLv3 open source. The current released sending-governance stage is tagged `v0.2.0`.

## Sensitive Data

Do not commit:

- SMTP usernames, passwords, or app passwords
- AI API keys
- License keys or activation tokens
- Local SQLite runtime databases
- Customer, lead, recipient, or send-history data
- Private `.env` files

The desktop app stores local runtime state in SQLite. Current SMTP account-pool passwords are stored in the local app database as application data. For shared or production use, prefer OS keychain/keyring storage before distributing builds to users who expect encrypted credential storage.

## Licensing Security

The open-source desktop app defaults to open-source mode when no server license endpoint is configured. Legacy local licensing is disabled by default because its algorithm is visible in source releases. Use the server-license flow for commercial deployments.

## Responsible Use

This tool sends email through user-provided SMTP accounts. Operators are responsible for:

- recipient consent and lawful basis
- suppression and unsubscribe handling
- rate limits and provider terms
- avoiding spam, deceptive identity, or unauthorized sending
- protecting imported lead lists and send history

## Reporting Issues

Report security issues privately to the repository owner. Use GitHub private vulnerability reporting if it is enabled for the repository; otherwise contact the owner privately before opening a public issue. Do not file public issues containing secrets, credentials, customer data, or exploit details.
