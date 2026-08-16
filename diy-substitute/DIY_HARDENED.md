# DIY HARDENED

DIY HARDENED is the workflow-run consumer. It is designed for a repository
that already has a trusted Free Action producer named `PRWitness Free`.

```bash
python3 -m diy.cli hardened \
  --event "$GITHUB_EVENT_PATH" \
  --repository "$GITHUB_REPOSITORY"
```

The workflow in `workflows/diy-hardened.yml` has only `contents: read` and
`actions: read`. It checks out the evaluator from the trusted default branch,
never `workflow_run.head_sha`, and treats the PR head SHA, branch, title, and
artifact bytes as data. It does not checkout or execute untrusted PR code and
does not execute any script from an artifact. The Python API client only lists
all artifact pages and downloads one exact artifact archive.

The only external workflow action is `actions/checkout`, pinned to the
full-length commit `11bd71901bbe5b1630ceea73d27597364c9af683` (v4.2.2).

The evaluator fails closed when the event is malformed, the run is incomplete,
the target repository/workflow is wrong, the PR/run/artifact SHA conflicts,
the artifact is missing/duplicate/expired/oversize, the digest or ZIP is
unsafe, or the API fails. Only a validated PASS can become `READY`; `HOLD` and
`INCOMPLETE` are blocking outcomes. `IGNORED` is reserved for events that are
not the configured completed pull-request workflow.

This is a local substitute, not the PRWitness Pro implementation. It does not
provide hosted history, organization policy, merge automation, billing,
dashboarding, buyer research, or buyer-willingness evidence.
