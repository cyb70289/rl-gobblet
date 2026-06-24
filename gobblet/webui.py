"""FastAPI web server: hosts the static UI and exposes /api/move and /api/health.

The client (browser) holds the full game state and sends a wire-format snapshot
plus the model color on every model turn. The server is stateless across
requests: it rebuilds the State from the request body, runs a fresh MCTS, and
returns the chosen action.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Config
from .game import Action, State
from .mcts import MCTS
from .net import GobbletNet


# ---------- wire conversion ----------

def _state_from_wire(d: dict) -> State:
    board_in = d["board"]
    if len(board_in) != 9:
        raise ValueError(f"board must have 9 cells, got {len(board_in)}")
    trays_in = d["trays"]
    if len(trays_in) != 6:
        raise ValueError(f"trays must have 6 counts, got {len(trays_in)}")
    return State(
        board=tuple(tuple((int(c), int(s)) for c, s in cell) for cell in board_in),
        trays=tuple(int(t) for t in trays_in),
        player=int(d["player"]),
        ply=int(d["ply"]),
        winner=(None if d.get("winner") is None else int(d["winner"])),
        is_draw=bool(d.get("is_draw", False)),
    )


def _action_to_wire(a: Action) -> dict:
    if a.kind == "place":
        return {"kind": "place", "to": a.to, "size": a.size}
    return {"kind": "move", "from_": a.from_, "to": a.to}


# ---------- request / response models ----------

class _WireState(BaseModel):
    board: list
    trays: list
    player: int
    ply: int = 0
    winner: Optional[int] = None
    is_draw: bool = False


class _MoveRequest(BaseModel):
    state: _WireState
    modelColor: int


class _Action(BaseModel):
    kind: str
    to: int
    size: Optional[int] = None
    from_: Optional[int] = Field(default=None, alias="from_")


class _MoveResponse(BaseModel):
    action: _Action


# ---------- app factory ----------

def create_app(
    net: GobbletNet,
    mcts: MCTS,
    model_path: str,
    sims: int,
    static_dir: Optional[str] = None,
) -> FastAPI:
    """Build the FastAPI app. Tests can inject net/mcts/static_dir."""
    app = FastAPI()

    @app.get("/api/health")
    def health():
        device = str(next(net.parameters()).device)
        return {
            "ok": True,
            "model_loaded": True,
            "sims": sims,
            "device": device,
            "model_path": model_path,
        }

    @app.post("/api/move", response_model=_MoveResponse)
    def move(req: _MoveRequest):
        try:
            state = _state_from_wire(req.state.model_dump())
        except (KeyError, TypeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"invalid state: {e}")
        if state.is_terminal():
            raise HTTPException(status_code=400, detail="state is terminal")
        if state.player != req.modelColor:
            raise HTTPException(
                status_code=400,
                detail=f"modelColor {req.modelColor} != state.player {state.player}",
            )
        counts = mcts.search(state, add_noise=False)
        action = mcts.choose_action(counts, temperature=0.0)
        if action is None:
            raise HTTPException(status_code=500, detail="MCTS returned no action")
        return _MoveResponse(action=_Action(**_action_to_wire(action)))

    if static_dir is not None:
        _mount_static(app, static_dir)

    return app


def _mount_static(app: FastAPI, static_dir: str) -> None:
    root = Path(static_dir).resolve()

    @app.get("/")
    def index():
        return FileResponse(root / "index.html")

    for name in ("game.js", "app.js", "styles.css"):
        path = root / name
        if not path.exists():
            continue
        if name.endswith(".js"):
            media = "application/javascript"
        elif name.endswith(".css"):
            media = "text/css"
        else:
            media = "application/octet-stream"

        def make_handler(p, m):
            def handler():
                return FileResponse(p, media_type=m)
            return handler

        app.add_api_route(f"/{name}", make_handler(path, media), methods=["GET"])


# ---------- CLI entry point ----------

def main():
    parser = argparse.ArgumentParser(description="Run the Gobblet web UI server")
    parser.add_argument("--ckpt", required=True, help="model checkpoint path")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--sims", type=int, default=200, help="MCTS simulations per move")
    parser.add_argument("--smoke", action="store_true", help="use tiny smoke config (random init, 4 sims)")
    parser.add_argument("--static-dir", default="ui", help="directory containing index.html, app.js, etc.")
    args = parser.parse_args()

    cfg = Config.for_smoke() if args.smoke else Config()
    if args.smoke:
        cfg.mcts.simulations = 4
    else:
        cfg.mcts.simulations = args.sims

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    net = GobbletNet(cfg.net).to(device)
    if not args.smoke:
        net.load(args.ckpt)
    net.eval()
    mcts = MCTS(cfg.mcts, net)

    app = create_app(
        net=net, mcts=mcts, model_path=args.ckpt, sims=cfg.mcts.simulations,
        static_dir=args.static_dir,
    )

    if args.smoke:
        print(f"SMOKE mode (random init): sims={cfg.mcts.simulations}, device={device}")
    else:
        print(f"model loaded: {args.ckpt}, sims={cfg.mcts.simulations}, device={device}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
