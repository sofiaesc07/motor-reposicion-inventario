# Rules for programming agents
- Python business logic belongs in `src/inventory/`; DAGs only orchestrate.
- Never edit or delete `source_inbox/`; it is an external read-only source.
- Never use observations after the logical cutoff for features or training.
- All configuration changes live in versioned YAML files.
- Never commit datasets, trained models, published forecasts, or secrets into Git.
- Preserve deterministic outputs and atomic writes; do not append duplicate daily results.
- Require pytest before pull requests and review changes before merging.
- Do not claim reproducibility without a successful clean clone, DVC pull, and rerun.
