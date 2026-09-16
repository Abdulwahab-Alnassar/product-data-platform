# Security and privacy boundaries

This repository is a local educational application. Keep its ports on loopback.
HTTP readers do not authenticate. `/events` requires a configured API key and
rejects writes when the key is empty. It is not a multi-user authorization system.

- Database queries use bound parameters for user values; SQL templates are internal.
- API validation errors do not echo submitted payloads; recommended commands disable
  access logging to avoid query text in logs.
- No uploaded model pickle is executed. Model artifacts are local JSON weights.
- `.env`, raw data, databases, model artifacts, logs, and backups are ignored by Git.
- Images and product links are not fetched by the server. There is no arbitrary URL fetch endpoint.
- Optional local generation receives redacted product records, not review/customer fields.
- Default Compose publishes API/UI only on 127.0.0.1; PostgreSQL is internal.

The PostgreSQL demo uses one database role. Read-only transactions limit normal
application reads, but a production installation needs separate database roles.
There is no internet-facing TLS gateway, per-user rate limiting, secrets vault,
or automatic audit retention. Request field lengths are bounded; a deployment
proxy must also enforce total body size, concurrency, and authentication.

The curated sample removes customer identifier columns and blanks reviews.
Earlier commits may still contain the older sample; this change does not erase
repository history. Local raw data can still contain personal information.
Email/phone masking is heuristic and cannot guarantee full anonymization.

Do not paste credentials or private data into issues. Report a vulnerability
privately to the repository owner rather than publishing a working credential.
