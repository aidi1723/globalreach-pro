# Client SDK

Shared client SDK responsibilities:

- device fingerprint normalization
- activation request helpers
- validation request helpers
- cached token structure
- release flow helpers
- normalized error mapping

The email tool can be the first consumer and later move from local app-specific code to this shared SDK.
