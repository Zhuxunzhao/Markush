# Outputs

- `examples/`: checked-in sample results and debug logs.
- `results/molpatent-240/final/`: current full MolPatent-240 experiment outputs.
- `results/molpatent-240/comparisons/`: comparison runs and analysis reports.
- `results/molpatent-240/legacy/`: older or timestamped full-pipeline outputs kept for reference.
- `runtime/`: git-ignored ad-hoc local outputs, smoke tests, dry runs, PID files, logs, and checkpoints.

The CLI still defaults to writing `result.json` in the current working directory
for backward compatibility. Move or override `--output` when you want a stable path.
