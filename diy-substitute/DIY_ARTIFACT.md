# DIY ARTIFACT

DIY ARTIFACT adds a read-only, local GitHub-shaped artifact adapter:

```bash
python3 -m diy.cli artifact \
  --metadata path/to/artifact-metadata.json \
  --zip path/to/prwitness-artifact.zip
```

It requires one exact artifact name, one workflow-run ID, matching
`workflow_run.head_sha`, a non-expired artifact, a bounded size, and a
`sha256:` digest. The ZIP scanner rejects absolute paths, parent traversal,
symlinks, duplicates, oversize members, compression bombs, and missing or
duplicate `free-result.json` entries. It reads one bounded JSON member in
memory; it never extracts or executes artifact files.

The metadata shape mirrors the public GitHub Actions artifact API surface. It
does not infer “the first artifact” and does not treat a sample or first page
as the whole population.
