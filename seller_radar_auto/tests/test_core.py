import json, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"

def run(name):
    return subprocess.run([sys.executable,str(ROOT/name)],capture_output=True,text=True,check=True)

def test_matrix():
    run("build_discovery_matrix.py")
    d=json.loads((DATA/"discovery_matrix.json").read_text(encoding="utf-8"))
    assert any(x["tipo"]=="COMUNE" and x["comune"]=="Sant'Ambrogio di Torino" for x in d["targets"])
    assert any(x["tipo"]=="BORGATA" for x in d["targets"])

def test_route_preserves_master():
    run("prepare_acquisition_route.py")
    r=run("validate_giro_acquisizione.py")
    assert "PASS GIRO QA" in r.stdout
