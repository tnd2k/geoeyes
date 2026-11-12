"""ProjectState: phases left "running" by a killed run."""
from geoeyes.controller.phase import ProjectState


class _P:
    def __init__(self, root):
        self.state_file = root / "state.json"


def test_running_phases_of_a_killed_run_become_interrupted(tmp_path):
    st = ProjectState(_P(tmp_path))
    st.set("s1-asc-1", "ps", status="running", run_id="A")
    st.set("s1-asc-1", "phase_linking", status="done", run_id="A")
    st.set("s1-dsc-2", "ps", status="running", run_id="B")
    assert st.clear_interrupted(["s1-asc-1"]) == ["s1-asc-1/ps"]
    rec = st.get("s1-asc-1", "ps")
    assert rec["status"] == "failed" and "interrupted" in rec["error"] and rec["run_id"] == "A"
    assert st.get("s1-asc-1", "phase_linking")["status"] == "done"
    assert st.get("s1-dsc-2", "ps")["status"] == "running"          # another track, another lock
