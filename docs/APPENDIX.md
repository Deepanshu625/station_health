# Station Health Service — Appendix

Extended answers on scaling, extensibility, security, testing, CI/CD, the AWS mapping, and how AI tools were used to build this service. Continues from [DESIGN.md](DESIGN.md).

---

## 1. Scaling to 100K+ stations

At one report per station per minute, 100K stations means about 1,700 writes per second and roughly 144M report rows a day.

Put a queue in front of ingestion. The API validates the payload, sends it to SQS, and returns 202. Workers pull a few hundred reports at a time and write them with one multi-row insert (`ON CONFLICT DO NOTHING`), then update the affected station rows. After a regional outage, thousands of stations reconnect at once and flush their buffered reports, often ten times normal load; with a queue, that becomes a backlog instead of database overload. I don't rely on the queue for ordering or exactly-once delivery: the unique constraint makes redelivery harmless, the newer-wins check handles late reports.

Reads stay fast. The dashboard reads from the `stations` table, which holds one row per station (100K rows) no matter how much history builds up. At scale, I'd serve reads from a replica and refresh the fleet metrics once a minute instead of on every request.

## 2. Extending the system

**Proactive alerting**

The service already knows when a station crosses the poor threshold; alerting is about acting on that without flooding the on-call.

- Alert on changes (healthy to poor, poor to recovered), not on every bad report.
- Add hysteresis: flag below 60, but only clear above 70, so a station hovering around the line doesn't page repeatedly.
- Include silent stations. A scheduled job flags any station that hasn't reported for 15 minutes, since a station that stops talking is often the most urgent case.
- Group before paging. If 30% of a region's stations degrade within a few minutes, that's one incident (probably a carrier or upstream issue), not thousands of station alerts.

**Anomaly detection**

I'd start simple and only add complexity once the simple version proves its false-positive rate.

- Per-station baselines. Track a moving average of latency and error rate for each station and flag readings far outside its own normal range.
- Firmware cohorts. Compare error rates for stations on a newly rolled-out firmware version against those still on the previous one. This turns the service into an early warning for bad releases, which is probably its most valuable extension.
- Models later. Once there's history in S3 and operators have been labelling alerts as real or noise, train something like Isolation Forest offline. Without labels, it's hard to know whether a model is actually better than the baseline.

**Multi-region redundancy**

- Use Aurora Global Database: one writer region, replicas elsewhere with about a second of lag, and managed failover if the primary region goes down.
- Run the ingestion API in two or more regions behind a global load balancer that sends each station to the nearest healthy region and fails over automatically if one goes down.
- Stations already buffer and retry, and ingestion is idempotent, so replaying reports after a failover can't create duplicates.

## 3. Security

- Device identity. Each station gets its own certificate and connects over mutual TLS, for example through AWS IoT Core. The key rule is that the authenticated identity must match the `station_id` in the payload, so a compromised charger can't report on behalf of others.
- Operator access. The read APIs and dashboard sit behind company SSO, with tokens validated at API Gateway and role-based access if write or admin operations are added.
- Abuse limits. WAF and API Gateway usage plans for rate limiting per station and per client.
- Data protection. TLS everywhere, encryption at rest with KMS, secrets in Secrets Manager rather than environment files, and a narrowly scoped IAM role per service.
- The exercise has no authentication; that's a deliberate simplification. In production I'd add the controls above.

## 4. Testing strategy

- Unit tests for the scoring logic and config. They run without a database and check the edge cases: latency at 200 and 2000 ms, a score of exactly 60, and old or unreadable firmware versions.
- Integration tests against a real Postgres. They cover ingestion, duplicate reports, bad input, late reports, the poor-hygiene list and metrics. I used Postgres instead of SQLite because the two handle constraints and locking differently.
- CI checks: at least 85% test coverage (100% for scoring), no missing migrations, and a valid API spec.

Next steps:

- Test two reports for the same station arriving at the same time.
- Load test a reconnect storm with Locust.
- Flag any change to the API spec in pull requests.
- Add a simple browser test for the dashboard.

## 5. CI/CD

CI runs on every push and pull request using GitHub Actions. It lints the code, checks migrations, runs the tests against Postgres, validates the API spec, and builds the Docker image.

Next steps:

- Build the image once, store it in ECR, and promote that same image from dev to staging to production, with a manual approval before production.
- Deploy to ECS Fargate with blue/green releases, rolling back automatically if errors or latency spike.
- Run database migrations before each release, and keep them backward compatible so the old and new versions can run side by side.
- Define the infrastructure as code using Terraform or CDK.

## 6. AWS mapping

| Concern | Local | AWS |
|---|---|---|
| API and workers | Django + gunicorn | ECS Fargate |
| Database | PostgreSQL | Aurora PostgreSQL (Global Database for multi-region) |
| Connection pooling | None | RDS Proxy |
| History archive | None | S3 (Parquet) + Athena |
| Scheduled jobs | None | EventBridge Scheduler |
| Alerting | None | EventBridge, PagerDuty / Slack |
| Observability | JSON logs to stdout | CloudWatch Logs and metrics, Splunk |
| Secrets | `.env` file | AWS Secrets Manager |
| Infrastructure | Docker Compose | Terraform |
| Queue | None | AWS Simple Queue Service |

## 7. How I validated AI-generated code

I treated AI output the way I'd treat a pull request from a new teammate: nothing went in that I couldn't explain line by line.

- Spec first, code second. Before generating any code, I wrote a low-level design with every endpoint, field, validation rule and formula. That gave me something concrete to check the output against, instead of judging whether it just "looked right".
- Most review time on the risky parts. Transactions, duplicate handling, out-of-order reports and timezone handling are where plausible-looking code can be subtly wrong, so I read those most carefully. Boilerplate (settings, serializers, Dockerfile, CI config) got a lighter pass.
- Ran it myself. I ran the test suite, exercised every endpoint with curl, and clicked through the dashboard with real data.
- Checked the tests, not just the code. An AI writing both the code and its tests can make a bug look covered, so I made sure the tests described behaviour I'd defined rather than whatever the code happened to do.
- Verified against the docs. Library calls I wasn't sure about, particularly in Django and drf-spectacular, I checked against the documentation.

## 8. How AI tools influenced the architecture

I used Claude as a design partner and Claude Sonnet to implement from my spec.

The biggest influence was actually a correction. The first design that came out of those sessions was more than this brief needed: rolling-window scoring, a state-transition event log, cursor pagination, rebuild commands and a data simulator. Each piece was defensible on its own, but together they didn't fit "a working day, don't over-engineer."

So I cut it back. I kept the things that matter for correctness (idempotent ingestion, out-of-order handling, a pure scoring function, fail-fast config) and moved the rest into future scope with a note on how each would be added.

AI was most useful for widening the options quickly, such as Django versus FastAPI, Postgres versus MySQL, and single-report versus windowed scoring, and for pressure-testing my reasoning. The final calls came down to things the tools don't weigh: the time box, what I can confidently defend, and what fits the team's stack.

## 9. Trade-offs: AI assistance vs writing it myself

**Tools and how I used them**

- Claude (chat): I started with a short problem statement and a rough design of my own, and used Claude to discuss it and shape it into an architecture.
- Claude Sonnet: I took that architecture to Sonnet and worked through the details: database fields and constraints, API parameters and responses, the dashboard mockup, test scenarios, and which features to include.
- GitHub Copilot (in the IDE): I implemented the service with Copilot, working from that detailed design.

**Where AI saved real time:**

- project structuring;
- Django and DRF boilerplate;
- the Dockerfile and CI workflow;
- listing/writing test cases;
- drafting documentation and the architecture diagram.

For this kind of work it was several times faster than typing it myself.

**Where it needed a human:**

- It leans towards completeness. Left alone, it builds more than the problem asks for, and deciding what to leave out was my job.
- Concurrency and time handling. A review pass found a race where two simultaneous reports for the same station could leave the older one as the "latest" state, and a clock-skew window that was far too loose. Both looked fine at a glance and were one-line fixes once spotted.
- Review has a cost. Reading and understanding generated code takes real time. Skipping that step is where the risk is.

**AI suggestions vs writing from scratch**

Without AI, I would have worked through this the usual way:

1. Write a high-level design of the problem.
2. Choose the tech stack from my own experience and by reading up on the options online.
3. Define the APIs and the key constraints.
4. Design the database schema.
5. Write test scenarios and test cases, mainly for the happy path of each API.
6. Implement it all by hand.

With AI, the steps stayed the same, but each one went faster and covered more ground:

1. High-level design: I wrote a short problem statement and a rough design myself, then discussed it with Claude to shape it into an architecture.
2. Tech stack: instead of researching each option separately, I compared Django with FastAPI and Flask, PostgreSQL with MySQL with Claude, then made the final calls myself.
3. APIs and constraints: worked through the endpoints, parameters, validation rules and responses with Claude Sonnet.
4. Database schema: defined the tables, constraints and indexes the same way, including how to handle duplicate and out-of-order reports.
5. Test scenarios: beyond the happy path, AI helped list the edge cases: duplicates, late reports, bad timestamps, score boundaries, invalid input. On my own I'd probably have covered fewer of these.
6. Implementation: wrote the code in the IDE with Copilot, accepting suggestions for standard code and writing the tricky parts myself, then tested everything end to end.

What changed and what didn't. AI didn't change how I approach a problem; the steps are the ones I'd follow anyway. It made each step faster, brought up options and edge cases I might have missed, and handled most of the repetitive typing. The decisions stayed mine: what to build, what to leave out, and whether the code was correct.

About 90% of the code was AI-generated and then reviewed and edited by me. I wrote or rewrote by hand the row-locking fix, timestamp validation, logging, and parts of the ingestion logic.
