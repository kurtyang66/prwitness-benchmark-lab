# PRWitness Pro customer-owned DIY substitute

This is an independent adversarial red-team implementation under
`/tmp/prwitness-diy-redteam`. It was designed from zero using only the public
PRWitness Free Action README/action metadata/distribution contract and public
GitHub Actions/API semantics. It does not read, copy, import, or infer private
Pro implementation code.

## Three layers

| Layer | Input | Security boundary | Output |
| --- | --- | --- | --- |
| BASIC | local DIY `free-result.json` | schema and expected-SHA checks | `READY` / `HOLD` / `INCOMPLETE` |
| ARTIFACT | GitHub-shaped metadata plus ZIP | digest, size, ZIP safety, exact member | `READY` / `HOLD` / `INCOMPLETE` |
| HARDENED | completed `workflow_run` plus Actions API | exact repo/run/PR/SHA/workflow/artifact binding; read-only API | `READY` / `HOLD` / `INCOMPLETE` / `IGNORED` |

The explicit DIY contract is intentionally small because the public Free Action
docs identify `free-result.json`, the artifact name, `flow`, and PASS/FAIL, but
do not publish a complete JSON schema. This project never claims that its
schema is an undocumented PRWitness schema.

## Run locally

```bash
cd /tmp/prwitness-diy-redteam
python3 -m unittest discover -s tests -v
python3 -m diy.metrics --json
```

The test suite is standard-library-only and builds synthetic ZIPs in memory.
It covers READY, HOLD, INCOMPLETE, IGNORED, malformed, missing, SHA conflict,
duplicate, ZIP traversal/symlink safety, API failure, oversize, digest/size
conflict, pagination, and the “artifact script is never executed” property.

## Workflow boundary

`workflows/diy-hardened.yml` is a `workflow_run` consumer. It has no
`pull_request_target`, no write permissions, no secrets, and no checkout of
`workflow_run.head_sha`. The only checkout is the trusted default branch so
the evaluator itself is available. The PR head is never executed. The API
client lists every artifact page, requires exact `prwitness-<run_id>`, verifies
the GitHub-provided digest and archive size, and parses only
`free-result.json`. The only workflow action is `actions/checkout` pinned to a
full commit SHA (annotated as v4.2.2); update that pin only after reviewing the
official action repository.

The producer workflow is intentionally outside this substitute: a customer
may use the public Free Action or another trusted producer to upload the
artifact. The consumer does not treat a failed producer or untrusted artifact
as permission to merge or release.

## Official public references used

- [PRWitness Free Action distribution README](https://github.com/kurtyang66/prwitness/blob/main/distribution/github-action/README.md)
- [PRWitness Free Action metadata](https://github.com/kurtyang66/prwitness/blob/main/distribution/github-action/action.yml)
- [GitHub secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)
- [GitHub Actions artifact REST API](https://docs.github.com/en/rest/actions/artifacts)
- [GitHub workflow-run REST API](https://docs.github.com/en/rest/actions/workflow-runs)
- [GitHub artifact storage and validation](https://docs.github.com/en/actions/tutorials/store-and-share-data)

## Explicit non-claims

This repository measures engineering surface and synthetic security behavior.
It does not claim buyer willingness, product-market fit, hosted Pro parity,
or production safety beyond the tested contract and stated assumptions.
