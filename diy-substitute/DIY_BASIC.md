# DIY BASIC

DIY BASIC is the smallest customer-owned gate. It reads one local
`free-result.json`-shaped object and emits one of `READY`, `HOLD`, or
`INCOMPLETE`. It has no GitHub API client and no ZIP handling.

```bash
python3 -m diy.cli basic --input path/to/free-result.json
```

The adapter requires the explicit `prwitness-diy-free-result/v1` contract in
`diy/core.py`. The public Free Action documentation identifies the artifact
name and PASS/FAIL surface, but it does not publish a complete JSON schema;
this contract is therefore deliberately labelled DIY and is not presented as
an internal PRWitness schema.

`READY` means a complete PASS result was validated. `HOLD` means a complete
result explicitly failed or conflicted with an expected SHA. `INCOMPLETE` means
there is not enough trustworthy evidence. A non-`READY` state must not be used
to authorize merge or release.
