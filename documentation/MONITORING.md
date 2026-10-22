# Monitoring runbook (ship checklist C9)

Two tools, both on free plans: **Sentry** for crashes inside the API, **UptimeRobot** for "is the site
answering". Neither is wired to a real account yet; this is what to set up after the first deploy.

## Sentry (code done, off until a DSN is set)

- Set `SENTRY_DSN` on the Cloud Run service, plus `SENTRY_ENVIRONMENT=production` and
  `SENTRY_RELEASE=<git commit>`. With no DSN nothing is sent.
- It reports unhandled exceptions with their stack traces. It does **not** send request bodies (a body
  is a SMILES), cookies, auth headers, the worker secret, local variables in stack frames, or a user
  identity. `app/observability.py` sets the SDK switches and `scrub_event` strips the rest;
  `api/tests/test_observability.py` sends a real crash through the SDK and checks the wire payload.
- Performance tracing is off (`SENTRY_TRACES_SAMPLE_RATE=0`) so the free quota is spent on errors.
- Only the API reports. The browser is not instrumented: a frontend error shows in the console and is
  not collected. Add the browser SDK only if that becomes a real gap, and then check it against
  AGENTS.md never-do #7 (no animation) and the privacy rules above.
- In Sentry, create one alert rule: notify by email on a new issue in `production`.

## UptimeRobot (nothing to deploy; this is the settings to enter)

| Monitor | Type | URL | Check | Interval |
|---|---|---|---|---|
| MARS API | HTTP(s) keyword | `https://<service-url>/api/health` | body contains `"status":"ok"` | 5 min (free plan) |
| MARS site | HTTP(s) | `https://<service-url>/` | status 200 | 5 min |

- Point it at `/api/health`, **not** `/api/health/ready`. Readiness opens a Postgres and a Redis
  connection on every call; every five minutes that would keep Neon's database awake all month and spend
  the Upstash command quota on nothing. Liveness touches neither.
- Add your email as the alert contact. The blueprint expects a Cloud Run cold start of 1-3 s; confirm in
  UptimeRobot's settings that its request timeout and its "alert after N failures" setting are loose
  enough that a cold start does not page you (not checked here).
- A request every five minutes also keeps an instance warm. With Cloud Run's request-based billing an
  idle instance is not billed, but that is unverified for this project: look at the billing page after
  a week and drop to a coarser interval if it shows a cost.

## What each signal means

| Signal | Likely cause | First look |
|---|---|---|
| UptimeRobot: API down | instance crashed on start, bad env var, Redis or Neon unreachable at boot | Cloud Run logs; the start-up warnings in `app/main.py` name missing config |
| UptimeRobot: site up, API keyword fails | the bundle is served but the API is not | `/api/health` in a browser |
| Sentry: spike of one issue | a bad molecule class reaching the model, or a dependency change | the issue's stack trace and release |
| Batch job stuck at `running` | worker endpoint unreachable or secret mismatch | Cloud Tasks queue page; `api/README.md` "Batch worker deploy" |
