"""Tests for the webui FastAPI server: state/action wire conversion and endpoints."""
import pytest
from fastapi.testclient import TestClient

from gobblet.config import Config
from gobblet.game import State, Action, S, M, L
from gobblet.mcts import MCTS
from gobblet.net import GobbletNet
from gobblet.webui import _action_to_wire, _state_from_wire, create_app


def _make_client(static_dir=None):
    cfg = Config.for_smoke()
    net = GobbletNet(cfg.net).eval()
    mcts = MCTS(cfg.mcts, net)
    app = create_app(
        net=net, mcts=mcts, model_path="<test>", sims=cfg.mcts.simulations,
        static_dir=static_dir,
    )
    return TestClient(app)


def _initial_wire():
    s = State.initial()
    return {
        "board": [list(map(list, cell)) for cell in s.board],
        "trays": list(s.trays),
        "player": s.player,
        "ply": s.ply,
        "winner": s.winner,
        "is_draw": s.is_draw,
    }


# ---------- wire conversion ----------

def test_state_from_wire_matches_initial_state():
    s = _state_from_wire(_initial_wire())
    assert s == State.initial()


def test_state_from_wire_preserves_a_partial_state():
    st = State.initial()
    st = st.apply(Action.place(S, 0))
    st = st.apply(Action.place(M, 4))
    wire = {
        "board": [list(map(list, cell)) for cell in st.board],
        "trays": list(st.trays),
        "player": st.player,
        "ply": st.ply,
        "winner": st.winner,
        "is_draw": st.is_draw,
    }
    s = _state_from_wire(wire)
    assert s == st


def test_action_to_wire_place():
    assert _action_to_wire(Action.place(S, 4)) == {"kind": "place", "to": 4, "size": 0}


def test_action_to_wire_move():
    assert _action_to_wire(Action.move(0, 4)) == {"kind": "move", "from_": 0, "to": 4}


# ---------- /api/health ----------

def test_health_returns_200_and_required_fields():
    c = _make_client()
    r = c.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["model_loaded"] is True
    assert body["sims"] == 4
    assert body["device"] in ("cpu", "cuda")
    assert body["model_path"] == "<test>"


# ---------- /api/move ----------

def test_move_returns_a_legal_place_action_for_initial_state():
    c = _make_client()
    r = c.post("/api/move", json={"state": _initial_wire(), "modelColor": 0})
    assert r.status_code == 200
    action = r.json()["action"]
    assert action["kind"] == "place"
    s = State.initial()
    assert Action.place(action["size"], action["to"]) in s.legal_actions()


def test_move_rejects_terminal_state():
    c = _make_client()
    st = State.initial()
    for a in [Action.place(S, 0), Action.place(S, 3), Action.place(M, 1),
              Action.place(S, 5), Action.place(L, 2)]:
        st = st.apply(a)
    assert st.is_terminal()
    wire = {
        "board": [list(map(list, cell)) for cell in st.board],
        "trays": list(st.trays),
        "player": st.player,
        "ply": st.ply,
        "winner": st.winner,
        "is_draw": st.is_draw,
    }
    r = c.post("/api/move", json={"state": wire, "modelColor": st.player})
    assert r.status_code == 400


def test_move_rejects_mismatched_model_color():
    c = _make_client()
    body = {"state": _initial_wire(), "modelColor": 1}
    r = c.post("/api/move", json=body)
    assert r.status_code == 400


def test_move_rejects_garbage_state():
    c = _make_client()
    r = c.post("/api/move", json={"state": {"board": "not a list"}, "modelColor": 0})
    assert r.status_code in (400, 422)


def test_move_rejects_wrong_board_length():
    c = _make_client()
    bad = _initial_wire()
    bad["board"] = bad["board"][:8]  # only 8 cells
    r = c.post("/api/move", json={"state": bad, "modelColor": 0})
    assert r.status_code in (400, 422)


# ---------- static files ----------

def test_root_serves_index_html(static_dir_from_test):
    c = _make_client(static_dir=str(static_dir_from_test))
    r = c.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "Gobblet" in r.text


def test_app_js_is_served_at_root_path(static_dir_from_test):
    c = _make_client(static_dir=str(static_dir_from_test))
    r = c.get("/app.js")
    assert r.status_code == 200
    assert "javascript" in r.headers.get("content-type", "") or r.text.startswith("(")


# ---------- fixtures ----------

@pytest.fixture
def static_dir_from_test():
    from pathlib import Path
    return Path(__file__).resolve().parents[2] / "ui"
