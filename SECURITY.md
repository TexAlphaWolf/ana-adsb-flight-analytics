# Security

## Model

adsbstat is a command line program that **reads trace files and writes a few files**. It starts no service, opens no network
connection and runs no code from its input.

- **What it reads:** readsb trace files (JSON, gzip-compressed or not, in a directory, a tar archive or alone), an OurAirports
  `airports.csv`, a `truth.json` given to `analyze`, and a `report.json` or `bench.json` given to `render`. JSON is parsed with the
  standard library, points are validated one by one, and a malformed file is counted and skipped or reported.
- **What it writes:** only where the options say: `generate DIR` (it refuses a directory that is not empty), `analyze --out`,
  `bench --out` and `render -o` and `--figure`.
- **Archives are only read as streams.** Members are never extracted to disk, so a tar archive with odd member names cannot write
  outside anything. Their contents are read in memory one at a time.
- **Compressed input can be large.** A gzip file that expands to a very large document is read whole into memory; run the tool on
  files you trust to be what they say, or under a memory limit (`docker run --memory`).
- **The Docker image** runs as an unprivileged user and works with a read-only root filesystem (plus `--tmpfs /tmp` for matplotlib's
  cache), no capabilities and no network (`--network none`); `tools/run_real.ps1` mounts the input read-only.
- **No real data** is in the repository: the traces are synthetic. adsb.lol's data is published under the Open Database License
  (ODbL), and aircraft positions can identify people; check the licence and the rules that apply to you before publishing results.

## Reporting

If you find a vulnerability, please open a private security advisory on the GitHub repository (Security tab) rather than a public
issue.
