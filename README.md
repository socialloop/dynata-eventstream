# Dynata Event Stream Forwarder

Connects to the Dynata respondent event broadcaster (gRPC server stream at
`events.rex.dynata.com`, docs: https://docs.rex.dynata.com/broadcaster/) and
forwards each event via HTTP POST to a Cloud Function.

Note: the stream is **not durable** — events that occur while disconnected are
lost. The service runs with `min-instances=1` and reconnects aggressively.

## Configuration

All via environment variables (no defaults for secrets — the service fails
fast if they are missing):

- `DYNATA_AUTH` (required): Dynata access key
- `DYNATA_SECRET` (required): Dynata secret key
- `CLOUD_FUNCTION_URL` (required): endpoint that receives forwarded events
- `UNHEALTHY_AFTER_SECONDS` (optional, default 300): how long the stream may be
  down before `/healthz` reports 503

In production the Dynata credentials come from Secret Manager
(`dynata-auth`, `dynata-secret`) — see `deploy.sh`. Never commit credential
values to this repo.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Generate protobuf files (the proto file is in `protos/event_stream.proto`):
```bash
./generate_protos.sh
```

The Dockerfile generates these automatically during the build.

## Local Development

```bash
export DYNATA_AUTH=...
export DYNATA_SECRET=...
export CLOUD_FUNCTION_URL=...   # point at a dev endpoint, not production
python src/main.py
```

## Deployment to Cloud Run

```bash
./deploy.sh [PROJECT_ID] [REGION]
```

This builds from source and deploys with secrets mounted from Secret Manager.
To rotate credentials, add new secret versions and redeploy:

```bash
printf '%s' "NEW_VALUE" | gcloud secrets versions add dynata-auth --data-file=-
printf '%s' "NEW_VALUE" | gcloud secrets versions add dynata-secret --data-file=-
./deploy.sh
```

## Health endpoints

- `/` — always 200 while the process is up (startup probe)
- `/healthz` — 503 if the stream has been disconnected longer than
  `UNHEALTHY_AFTER_SECONDS` (usable as a liveness probe)
