#!/usr/bin/env sh
# End-to-end walkthrough of the evidence workflow on the buck-demo design,
# in documentation-only mode (no KiCad or ngspice needed).
#
#   sh examples/buck-demo/build_demo.sh [WORKDIR]
#
# Produces WORKDIR/.edagov (records + audit chain), WORKDIR/dashboard.html and a
# review snapshot zip. Each step runs as the role a real team would use.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
WORK="${1:-$HERE/_work}"
EDA="$REPO/bin/edagov"

rm -rf "$WORK"; mkdir -p "$WORK"
cp -R "$HERE/kicad" "$HERE/reports" "$HERE/bom" "$HERE/sim" "$HERE/fab" "$HERE/github" "$WORK/"
cd "$WORK"
export EDAGOV_ROOT="$WORK"

as() { EDAGOV_ACTOR="$1"; export EDAGOV_ACTOR; }

echo "== 1. Scope and identity"
as designer@example.com
"$EDA" init --product PRD-BUCK --design DES-BUCK-DEMO --board PCB-BUCK-01 --revision B --variant default \
  --authority designer@example.com --repository example-hw/buck-demo --standard "IPC-2221B (2012)" \
  --grant designer@example.com=contributor --grant reviewer@example.com=design_reviewer \
  --grant supply@example.com=supply_reviewer --grant fab@example.com=manufacturing_reviewer \
  --grant release@example.com=release_approver --grant admin@example.com=connector_admin \
  --grant audit@example.com=auditor >/dev/null

echo "== 2. Requirements, architecture, decisions"
"$EDA" record requirement --id REQ-VOUT --text "Output 3.3 V ±2% from 9–36 V input at 0–3 A" --source "Customer spec CS-118 r2" \
  --owner designer@example.com --priority high --method simulation --acceptance "3.234–3.366 V across line/load corners" --status approved
"$EDA" record requirement --id REQ-RIPPLE --text "Output ripple below 30 mVpp at 3 A" --source "Customer spec CS-118 r2" \
  --owner designer@example.com --priority high --method test --acceptance "≤ 30 mVpp, 20 MHz BW, 3 A load" --status approved
"$EDA" record requirement --id REQ-TEMP --text "Operate at 85 °C ambient, still air" --source "Customer spec CS-118 r2" \
  --owner designer@example.com --priority medium --method analysis --acceptance "Tj ≤ 125 °C at 85 °C ambient, 3 A" --status approved
"$EDA" record requirement --id REQ-EMI --text "Conducted emissions meet CISPR 32:2015 Class B on the input port" --source "Regulatory plan RP-4" \
  --owner designer@example.com --priority high --method test --acceptance "CISPR 32:2015 Class B limits, 150 kHz–30 MHz" --status approved
"$EDA" record block --id BLK-POWER --name "Power stage" --purpose "12 V to 3.3 V conversion" --owner designer@example.com \
  --interface J1 --interface VOUT --allocate REQ-VOUT --allocate REQ-RIPPLE --allocate REQ-TEMP
"$EDA" record block --id BLK-INPUT --name "Input filter and connector" --purpose "Input protection and EMI filtering" \
  --owner designer@example.com --interface J1 --allocate REQ-EMI
"$EDA" record assumption --id ASM-AIRFLOW --text "Enclosure gives still air only; no forced cooling" --owner designer@example.com \
  --review-condition "Mechanical enclosure review MR-2 (Nov 2026)"
"$EDA" record decision --id ADR-PWR-FLAG --title "Treat VIN as externally driven in rev B" \
  --rationale "VIN arrives through J1 from the host; ERC power-driver error is excluded until a PWR_FLAG is added in rev C" \
  --alternative "Add PWR_FLAG now (deferred: schematic frozen for rev B layout)" --consequences "One ERC exclusion carried in rev B"

echo "== 3. Inventory and schematic evidence"
"$EDA" inventory --project kicad --library-release "kicad-symbols/kicad-footprints 10.0.0 tag" || true
"$EDA" record library --path lib/demo.kicad_sym --source "Project-local; drawn from TI TPS54360B datasheet SLVSBB4 rev. E, pinout reviewed 2026-10-12" \
  --license "CERN-OHL-P-2.0 (company library policy)" --rationale "Hidden GND pin kept to match vendor convention; flagged for rev C cleanup"
"$EDA" ingest erc reports/erc.json --project kicad
"$EDA" ingest drc reports/drc.json --project kicad

echo "== 4. Simulation (failed attempt kept, retry linked)"
"$EDA" ingest spice sim/buck_loop_ac.cir --log sim/buck_loop_ac.log --tool-version ngspice-44.2 --exit-code 0 \
  --validation "Crossover 38 kHz, PM 58° vs. Type-II hand calc ±10% (REQ-VOUT); bench Bode pending"
V1=$("$EDA" ingest spice sim/buck_tran_v1.cir --log sim/buck_tran_v1.log --tool-version ngspice-44.2 --exit-code 1 \
     | sed -n 's/^id=\([^ ]*\).*/\1/p')
echo "failed transient kept as $V1"
"$EDA" ingest spice sim/buck_tran_v2.cir --log sim/buck_tran_v2.log --tool-version ngspice-44.2 --exit-code 0 --retry-of "$V1" \
  --justification "reltol 1e-3→3e-3 with Gear integration; ripple result changes <1% vs reltol 1e-3 on a 50 µs window" \
  --validation "Steady-state ripple 18 mVpp vs. 30 mVpp limit (REQ-RIPPLE); bench measurement pending"

echo "== 5. PCB integrity evidence"
"$EDA" record evidence --id ART-STACKUP-B --path kicad/buck-demo.kicad_pcb --artifact-kind configuration --tag stackup --owner designer@example.com \
  --claim "2-layer 1.6 mm FR4 stackup as defined in board setup; fabricator confirmation pending"
"$EDA" record evidence --id ART-PI-NOTE-B --path "https://www.ti.com/lit/an/swpa222a/swpa222a.pdf" --artifact-kind report --tag pi_analysis --owner designer@example.com \
  --claim "PDN reviewed against TI guidance: input/output loops minimised; no PI simulation performed"
"$EDA" record evidence --id ART-THERMAL-B --path "kicad/buck-demo.kicad_pcb" --artifact-kind report --tag thermal_analysis --owner designer@example.com \
  --claim "Tj estimate 104 °C at 85 °C ambient using measured-board theta from TI SZZA009 method; not a measurement"

echo "== 6. Supply chain"
as designer@example.com
"$EDA" ingest bom bom/bom-revB.csv --project kicad

echo "== 7. Manufacturing package"
"$EDA" manifest --outputs fab --origin "drill/place origin at board lower-left (0,0)" \
  --supplier-assumption "Fabricator standard 2-layer 1.6 mm ENIG, 0.2/0.2 mm" || true

echo "== 8. Issues, reviews, exceptions"
DRC=$(grep -l '"check": "drc"' .edagov/records/run/*.json | head -1 | xargs basename | sed 's/\.v[0-9]*\.json//')
ERC=$(grep -l '"check": "erc"' .edagov/records/run/*.json | head -1 | xargs basename | sed 's/\.v[0-9]*\.json//')
"$EDA" issue open "L1 reference silkscreen clipped by mask" --id ISS-17 --severity medium --owner designer@example.com \
  --affected "$DRC" --gate pcb --due 2026-11-08 --external "example-hw/buck-demo#17"
"$EDA" issue open "J1 orderable part not selected" --id ISS-21 --severity high --owner supply@example.com \
  --affected BOM-EH-3001-DEFAULT --gate supply --due 2026-11-05
as reviewer@example.com
"$EDA" review "$ERC" --state approved --role design_reviewer --comments "Exclusion matches ADR-PWR-FLAG; ignored lib_symbol_issues check justified by vendored library"
for A in ART-STACKUP-B ART-THERMAL-B; do
  "$EDA" review "$A" --state approved --role design_reviewer --comments "Scope and limits acceptable for rev B"
done
for S in $(grep -l '"check": "simulation"' .edagov/records/run/*.json | xargs -n1 basename | sed 's/\.v[0-9]*\.json//' | sort -u); do
  "$EDA" review "$S" --state approved --role design_reviewer --comments "Settings and validation scope reviewed" >/dev/null 2>&1 || true
done

echo "== 9. Gate decisions"
"$EDA" approve requirements --decision approved --note "Requirements baseline CS-118 r2"
"$EDA" approve architecture --decision approved --note "Two-block architecture accepted"
"$EDA" approve schematic_library --decision approved --note "ERC exclusion accepted per ADR-PWR-FLAG" || true
"$EDA" approve simulation --decision approved --note "AC loop and retried transient qualified for stated scope" || true

echo "== 10. Connectors and GitHub (read-only)"
as admin@example.com
"$EDA" connector register --id CON-GITHUB --provider github --protocol rest --protocol-version 2022-11-28 --transport https \
  --endpoint https://api.github.com --scope repo:read --data-class design-metadata --trust-tier verified_read --secret-ref GITHUB_TOKEN
"$EDA" connector register --id CON-FAB-MCP --provider fab-quote-mcp --protocol mcp --protocol-version 2026-07-28 \
  --transport streamable-http --endpoint https://mcp.fab.example/mcp --scope quotes:write --data-class manufacturing-package \
  --secret-ref FAB_MCP_TOKEN
as designer@example.com
"$EDA" ingest github example-hw/buck-demo 42 --from-json github/pr-42.json
"$EDA" connector sync --id CON-GITHUB --state synced
"$EDA" connector sync --id CON-FAB-MCP --state unauthorized --error "401 from token audience check" --correlation COR-DEMO-0001
"$EDA" connector propose --id CON-FAB-MCP --verb publish --target "quote request for PCB-BUCK-01 rev B" \
  --input package=MFG-PCB-BUCK-01-B-DEFAULT --input quantity=50 --side-effect "Sends fabrication data to an external supplier" \
  --compensation "Request supplier deletion of uploaded data"

echo "== 11. Evaluate, snapshot, dashboard"
"$EDA" gates --persist
as reviewer@example.com
"$EDA" snapshot --out snapshots
"$EDA" dashboard --out dashboard.html
"$EDA" audit verify
echo "Done. Open $WORK/dashboard.html"
