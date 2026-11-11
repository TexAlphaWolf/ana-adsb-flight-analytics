#!/usr/bin/env bash
# End to end inside the image (read-only root, no capabilities, no network): a day of traces is generated, analysed and scored
# against its truth, the same day is read from a tar archive, a report is made (and rebuilt exactly from its JSON), the two
# implementations are compared and the benchmark runs small. Needs Docker. Usage: tools/docker_e2e.sh [image]
set -euo pipefail
IMAGE="${1:-adsbstat}"
VOL="adsbstat-e2e-$$"
TMP="$(mktemp -d)"
trap 'docker volume rm -f "$VOL" >/dev/null 2>&1 || true; rm -rf "$TMP"' EXIT

[ "$(docker run --rm --entrypoint id "$IMAGE" -u)" != 0 ]   # not root
docker volume create "$VOL" >/dev/null
docker run --rm --user 0 -v "$VOL":/data --entrypoint chown "$IMAGE" 10001 /data

RUN=(docker run --rm --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --network none -v "$VOL":/data "$IMAGE")
cat_file() { docker run --rm --entrypoint cat -v "$VOL":/data "$IMAGE" "$1" > "$2"; }

"${RUN[@]}" generate /data/day --aircraft 40 --seed 3 | grep -q '42 trace files, 91 flights'
out="$("${RUN[@]}" analyze /data/day --out /data/out)"
grep -q '42 aircraft, 29,462 position reports, 91 flights' <<<"$out"
grep -q 'against the truth: 91 of 91 flights found, 0 extra' <<<"$out"
cat_file /data/out/report.json "$TMP/report.json"
grep -q '"kind": "report"' "$TMP/report.json"
cat_file /data/out/report.md "$TMP/report.md"
"${RUN[@]}" render /data/out/report.json -o /data/out/again.md >/dev/null
cat_file /data/out/again.md "$TMP/again.md"
cmp "$TMP/again.md" "$TMP/report.md"                              # the report is rebuilt exactly from the JSON
cat_file /data/out/summary.png "$TMP/summary.png"
[ "$(head -c 4 "$TMP/summary.png" | tail -c 3)" = "PNG" ]

# the same day from a tar archive, the way the real archives come
docker run --rm --entrypoint python -v "$VOL":/data "$IMAGE" -c "import tarfile; t = tarfile.open('/data/day.tar.aa', 'w'); t.add('/data/day/traces', arcname='traces'); t.close()"
out="$("${RUN[@]}" analyze /data/day.tar.aa --airports /data/day/airports.csv)"
grep -q '42 aircraft, 29,462 position reports, 91 flights' <<<"$out"

out="$("${RUN[@]}" analyze)"
grep -q 'demo day' <<<"$out"

out="$("${RUN[@]}" verify --draws 5)"
grep -q '^6 of 6 comparisons agree with the literal implementation' <<<"$out"

"${RUN[@]}" bench --sizes 20,40 --ref-aircraft 40 --repeat 1 --draws 2 --seeds 2 --out /data/bench >/dev/null
cat_file /data/bench/bench.json "$TMP/bench.json"
grep -q '"ok": true' "$TMP/bench.json"

set +e; "${RUN[@]}" analyze /data/nope >/dev/null 2>&1; rc=$?; set -e   # a missing path is exit code 2
[ "$rc" = 2 ]
echo "docker end-to-end: OK"
