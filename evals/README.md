# Eval cases

Each child directory containing `case.json` is one Sindie evaluation case. Keep the visual attachments beside the manifest so a designer can inspect the exact material being evaluated.

The included `smoke/` case is only a transport and schema smoke test. The `grida/` directory contains four static GPT-Image-2 design fixtures with host-only provenance and visually grounded hard-constraint expectations. Add other real design cases as separate directories and keep designer annotations outside the model-visible request.

See [`EVALS.md`](../EVALS.md) for setup, commands, and the case contract.
