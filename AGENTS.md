# Working on Video Overlay Pipeline

- Read README.md, docs/contract.md and workflow/status.md before changing the workflow.
- Preserve v4 routing unless a versioned change is explicitly requested. OCR/rules propose locations; they never establish overlay or occlusion truth.
- Keep source footage read-only. No automatic deletion. Preserve technical failures and raw model answers.
- Keep same-source clips in one evaluation split. Assistant screening and model labels are not human ground truth.
- Personal cloud paths, credentials, quota IDs, job IDs, media and weights do not belong in this repository.
- Write all real-run artifacts to the operator's cloud run root. Use a new root when code/config/model/input identity changes.
- Before committing: run PYTHONPATH=src python3 -m unittest discover -s tests -v; compileall; CLI help; inspect git diff and staged files.
- No automatic cloud job submission, destructive publishing or deployment cutover during tests.
