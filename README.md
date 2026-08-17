# PRWitness benchmark lab

> **Synthetic benchmark fixture.** This repository contains no customer data and no
> production application. It exists to measure the public PRWitness Free Action and
> the installed PRWitness Pro Beta behavior on GitHub-hosted Actions.

## Scope

- deterministic static HTML fixture with real Playwright browser execution;
- `kurtyang66/prwitness-action@v1` at the immutable release SHA
  `c8b691b2af0299c28436a89f35450cc24e0cff9e`;
- real screenshots, before/after comparisons, manifests, logs, and GitHub Actions artifacts;
- 1-, 3-, 10-, and 25-flow pull-request scenarios on `ubuntu-latest`;
- separate benchmark-only negative fixtures and a customer-owned DIY substitute.

The Pro App installation is intended for this repository only. No repository-wide
installation or customer repository access is required. The hosted workflows forward
the exact `github.event.pull_request.base.sha` through the reusable benchmark workflow
to the Free Action's `base-ref` input. Each flow prints non-secret PR identity
diagnostics and verifies that `manifest.baseSha` matches the PR base SHA and
`manifest.headSha` matches the workflow checkout SHA before the hosted Pro Check is
read back.

## Reproduce the fixture locally

```bash
pnpm install --frozen-lockfile
pnpm exec playwright install chromium
pnpm start
```

The page is a static synthetic page. The normal benchmark is executed by GitHub-hosted
Actions so that workflow, artifact, webhook, and Check timestamps can be read from the
real platform. The benchmark workflow selects flows from the pull-request branch name:
`bench-1`, `bench-3`, `bench-10`, or `bench-25`.

## What is measured

- workflow and Free Action step duration;
- artifact count and real ZIP `size_in_bytes`;
- binary image evidence inside extracted artifacts;
- workflow completion to Pro Check creation/completion where observable;
- READY, HOLD, INCOMPLETE, IGNORED, and redelivery behavior.

The published `diy-substitute/` directory is a separate red-team implementation built
from public documentation. It contains BASIC, ARTIFACT, and HARDENED levels and is not
copied from private Pro code.

## What is not measured

- customer traffic, customer source code, or production business behavior;
- multi-installation concurrency without a legitimate second installation;
- fork-PR behavior without a legitimate independent fork;
- market demand, conversion, retention, or willingness to pay.

No secret, private key, webhook secret, installation token, or PAT belongs in this
repository. Do not execute files from downloaded evidence artifacts.

## Related systems

- Free Action: https://github.com/kurtyang66/prwitness-action
- Pro Beta App: https://github.com/apps/prwitness-pro-beta
- Pro Beta backend: https://prwitness-github-app-beta.vercel.app/healthz
- DIY comparison: `diy-substitute/`
