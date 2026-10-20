# Archived Fig A/B/C and attack figure

Run these commands from the repository root, using Python with Matplotlib and
NumPy installed (`venv/bin/python` in the local environment):

```bash
python3 paper_data/graph_generated_code/experiment2/plot_fig_abc.py
python3 paper_data/graph_generated_code/experiment2/plot_attack_latency_fig10_style.py
```

`plot_style.py` is the shared canvas and styling module. It does not load data or
draw figures on its own. `plot_fig_abc.py` calls the per-figure drawing functions
to produce all eight archived GEO/LAN panels, each as PDF and PNG:

| Panel | Output stem |
| --- | --- |
| A GEO/LAN | `fig_a_{geo,lan}_latency_vs_ref_by_sigma` |
| B GEO/LAN | `fig_b_{geo,lan}_latency_vs_cov_by_kappa` |
| C GEO/LAN latency | `fig_c_{geo,lan}_latency_vs_sigma_kappa_by_cov` |
| C GEO/LAN throughput | `fig_c_{geo,lan}_tps_vs_sigma_kappa_by_cov` |

The attack command produces
`attack_latency_timeseries_overlay_mean_send_time_fig10ab_style.{pdf,png}`.
Both commands write to `results/regenerate_graphs/experiment2_fig_abc/` by default.
The copied original PDFs/PNGs remain in `paper_data/paper_graph/experiment2/`.

To draw a subset or choose another destination:

```bash
python3 paper_data/graph_generated_code/experiment2/plot_fig_abc.py \
  --figure c --network lan --output-dir /tmp/fig_c_lan
```

## Data and provenance

Original Fig A/C runs are in `paper_data/original_data/Figure10abc/`, under
`fig_{a,c}/{geo,lan}/`. Committed original run artifacts are
`run_metadata.json`, `summary.txt`, and the run-level `latency.csv`.
Local `logs/*.log` files are excluded from Git.
Generated means, combined summaries, figure exports, and unrelated analysis
results are excluded. Source paths, axis settings, and the original Fig A LAN
exclusion are recorded in `fig_abc_settings.json` beside the plotting code.

| Local directory | Original directory under `new_experiment2/` |
| --- | --- |
| `fig_a/geo` | `sigma_spill_boundary_final0909/geo` |
| `fig_a/lan` | `new0903/new0908/geo_latest3_spill_on_bound_on_lan` |
| `fig_b/geo/fig_b_runs.csv` | `with_coin/geo/fig_b_runs.csv` |
| `fig_b/lan/fig_b_runs.csv` | `with_coin/lan/fig_b_runs.csv` |
| `fig_c/geo` | `figure_c/geo` |
| `fig_c/lan` | `figure_c/lan` |

The original sized panels came from `new_experiment2/paper_figs_sized/`.
Plot functions were brought over from `plot_fig_a_latency_vs_ref_by_sigma.py`,
`plot_fig_b_latency_vs_kappa_by_cov.py`, and `new0903/plot_fig_c.py`, with the
shared `plot_style.py` and `dataset_config.py`. Fig C's entry point was adapted
to accept a mean CSV, and the unified runner resolves all inputs inside this
repository. No sibling checkout is required.

`fig_abc_data.py` reads the original run summaries and metadata. Fig A averages
all original runs, preserving the existing LAN exclusion via settings; the
excluded original run remains in the archive. Some LAN metadata retains the
source's GEO naming and has been preserved as recorded. Fig C keeps up to three
lowest-latency runs per configuration, as in its original plotting code.

No original logs or run summaries were found for Fig B. Its two available
per-run input CSVs are kept at
`paper_data/original_data/Figure10abc/fig_b/{geo,lan}/fig_b_runs.csv`.
The runner recomputes Fig B means, including the original rounding to 1 ms.

All regenerated run/mean tables are written under
`results/processed_data/Figure10abc/fig_{a,b,c}/{geo,lan}/`, never original_data.
Use `--processed-data-root` to change this output location.

Attack inputs are in `paper_data/original_data/Figure10_attack/`, copied
from `ForArtifact/ae_error/10c/Fig10c/`. The four configurations retain
`latency.csv`, `summary.txt`, and `run_metadata.json` in Git.
`plot_attack_latency_fig10_style.py` calls this repository's existing
`plot_attack_latency_timeseries.py` to align client send times and compute the
cumulative mean. Its attack window is 60–120 seconds.

Individual send samples needed for the attack plot are exported separately to
`paper_data/processed_data/Figure10_attack/{configuration}/{run}/send_samples.csv`.
The attack runner joins these with the original records in a temporary directory
and reads the primary-start timestamp from metadata when logs are absent.
This preserves the plotted values without committing raw logs or storing derived
samples in original_data. Raw logs remain local and are ignored by Git.
The runners read the archives without modifying them. Regenerated figures
preserve the plotted values and shared canvas; originals remain available for
comparison of typography and layout.
