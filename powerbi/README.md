# Power BI project

Open `BathLab.pbip` in Power BI Desktop with project/enhanced-report support enabled. The adjacent report and semantic-model folders are part of the project; keep them together.

1. In Power Query, set the `Server` and `Database` parameters. The generated defaults are `127.0.0.1:55433` and `bath_lab_spc` for the current native installation. Docker's example host port is **55434**.
2. Supply PostgreSQL credentials in Desktop's data-source settings. Use a login granted `role_readonly`; credentials are deliberately absent from the files. Match SSL/encryption settings to your local PostgreSQL configuration.
3. Refresh. Confirm 130 rows in Nickel, 450 in the NIST summary's `n`, 590 SECOM sensor rows, and 426 total ETL rows for the latest example workbook.
4. Check the L1-T05 page: nickel individuals chart and MR chart, capability table (Cpk, Ppk, small-sample flag and stability label), ETL status table (per file name, so two workbooks never merge into one row) and daily dosing table. The other pages show NIST results and SECOM sensor comparisons.
   The nickel chart has a fifth series, `signal_value`, which is only filled at individuals-limit breaches and Rule 4 signals. The visual definition asks Power BI to draw that series as markers without a line (`lineStyles`: `showMarker` true, `strokeWidth` 0). In Desktop it renders as dots without a line, as intended; if another Desktop version draws it differently, set the marker in the series format pane. `spc_status` in the same table shows `NO_BASELINE` or `INSUFFICIENT_BASELINE` when the chart limits cannot be computed.
5. Save the project after confirming rendering. If hosting later, configure a gateway and credentials for the PostgreSQL source separately.

This is an import-mode model with seven independent database-view tables. No table reads Excel or local CSV files. No relationships are needed for the independent visuals. Dates are supplied as Berlin-local timestamps where required. The example has one bath tank; to add tanks, generalize the tank-specific reporting views and add page filters.

`scripts/build_powerbi.py` generates the PBIP, PBIR visual definitions and TMSL `model.bim`. Rebuilding overwrites generated report files; keep manual Desktop customizations in version control before regenerating. `scripts/validate_powerbi.py` validates structural report files against the cached official Microsoft schemas. It does **not** validate the model with the Analysis Services engine.

**Current verification:** On 2026-10-11 I opened `BathLab.pbip` in Power BI Desktop, refreshed the model from my local PostgreSQL 17 database with a login granted `role_readonly`, and checked the three pages against the SQL results. Screenshots: `docs/results/powerbi_l1t05.png`, `powerbi_nist.png` and `powerbi_secom.png`. The `desktop_refresh_verified` field in `docs/results/powerbi_validation.json` is written by the schema validator, which cannot check Desktop, so it stays `false`. The other charts under `docs/results` are generated separately from verified SQL output and are not Power BI screenshots.

Format references: [report projects](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report), [semantic model projects](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-dataset), [Microsoft JSON schemas](https://github.com/microsoft/json-schemas).
