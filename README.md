<p align="center"><img src="docs/figures/hero.png" alt="Process Quality Analytics and SPC: 426 of 426 workbook rows explained, 635 values reconciled, 15 of 15 NIST values reproduced" width="100%"></p>

<p align="center"><a href="https://github.com/KarimAmer45/process-quality-analytics/actions/workflows/verify.yml"><img src="https://github.com/KarimAmer45/process-quality-analytics/actions/workflows/verify.yml/badge.svg" alt="CI"></a> <img src="https://img.shields.io/badge/PostgreSQL-17-4169E1?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL 17"> <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12"> <img src="https://img.shields.io/badge/Power_BI-report-F2C811?style=flat-square&logo=powerbi&logoColor=white" alt="Power BI"> <img src="https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker"></p>
<p align="center">Plating Data Platform: <a href="https://github.com/KarimAmer45/manufacturing-traceability">Traceability</a> &middot; <b>Lab ETL & SPC</b> &middot; <a href="https://github.com/KarimAmer45/industrial-iot-historian">IoT historian</a> &middot; <a href="https://github.com/KarimAmer45/coating-specification-engine">Specification & release</a></p>

Labs keep their bath analyses in Excel. This project moves a deliberately messy German lab journal into PostgreSQL without losing or guessing a single row, reconciles the result against the database in both directions, and then runs statistical process control on it, all as SQL views that also feed a Power BI report.

> **Kurzfassung:** Ein bewusst unordentliches Laborjournal aus Excel wird nach PostgreSQL übernommen, ohne dass eine Zeile verloren geht oder geraten wird, und in beide Richtungen mit der Datenbank abgeglichen. Darauf laufen I-MR-Regelkarten, Run-Regel und monatliche Cpk/Ppk-Werte als SQL-Sichten, die auch einen Power-BI-Bericht speisen. Bad- und Labordaten sind simuliert; NIST und UCI SECOM sind echte öffentliche Datensätze.

<p align="center"><img src="docs/figures/row_accounting.png" alt="All 426 workbook rows with their status: 390 loaded, 34 ignored with a reason, 1 duplicate, 1 quarantined" width="100%"></p>

<p align="center"><img src="docs/figures/nickel_chart.png" alt="Nickel individuals chart with two analyses below the lower control limit" width="100%"></p>

<table>
<tr>
<td width="50%"><img src="docs/results/powerbi_l1t05.png" alt="Power BI report page for tank L1-T05, refreshed from the database views"></td>
<td width="50%"><img src="docs/results/powerbi_nist.png" alt="Power BI page reproducing the NIST lithography case study"></td>
</tr>
<tr><td align="center">Power BI, tank page (refreshed in Desktop)</td><td align="center">Power BI, NIST case study page</td></tr>
</table>

## Inside the database

- **Nothing dropped silently.** Raw rows go into an insert only staging ledger with the file hash; every row ends as loaded, ignored, duplicate or quarantined, each with a reason. Reimporting the same file changes nothing.
- **Reconciliation both ways.** Workbook to database and database to workbook: 635 values matched, 15 explicit "n.b." gaps, zero unexplained rows or conflicts.
- **SPC as SQL.** Individuals and moving range charts, run rule 4 (eight in a row) and monthly Cpk and Ppk with time-valid specification limits, all views.
- **Checked against published answers.** 15 NIST reference values reproduced; 590 real UCI SECOM sensors ranked in a materialized view against a chance reference.
- **BI on a read only login.** Power BI reads only seven database views, with no credentials in the project files; 57 tests on every push.

## Run it

```bash
cp .env.example .env    # set a local password
docker compose up -d db
docker compose run --rm demo
```

The demo downloads the NIST and UCI SECOM files, builds everything from an empty database and writes the evidence to `docs/results/`. Details are in the [report](REPORT.md).

## Data

The bath, schedule, workbook and doses are **simulated** from cited public sources; the NIST lithography data and UCI SECOM are **real** public datasets. This is a portfolio demonstration, not company production data or a dosing controller.

---

**Full technical report:** [REPORT.md](REPORT.md) has every result table, the evidence file behind each number, how each part is run and the known limitations.

Built by [Karim Amer](https://github.com/KarimAmer45), M.Sc. Mobile Robotics student at the University of Bonn.
