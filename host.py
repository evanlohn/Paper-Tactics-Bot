"""Host the AZ bot for any number of simultaneous games, in two seatings.

  <code>     bot moves first. One bot connection always waits in the matchmaking queue;
             when someone joins, that game moves to its own thread and a new waiting
             connection opens immediately.
  <code>-p2  you move first. The server makes whoever was queued first the first player,
             so the bot polls: it connects, asks for a game, and leaves after
             --p2-wait seconds if nobody was waiting. If you join during that window,
             the bot would end up moving first, so it concedes right away (just
             rejoin).

  python host.py --code evan-az-1eef [friend-code ...] --ckpt .../latest.pkl --record-dir .../human_games [--p2]

Searches from different games share the GPU behind a lock. The checkpoint (by default
the bot/current.pkl symlink, retargeted with `python -m pt.bot_ckpt set ...`) is checked
when each game starts; each game keeps the network it started with.
"""

import argparse
import json
import os
import platform
import sys
import threading
import time
import traceback

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from client import Recorder, get_tz
from game import Game

DEFAULT_URL = "wss://az7ndrlaxk.execute-api.eu-central-1.amazonaws.com/rolling"
URL = DEFAULT_URL  # overridden by --url
_print_lock = threading.Lock()


def log(*a):
    with _print_lock:
        print(time.strftime("%H:%M:%S"), *a, flush=True)


class SharedAgent:
    """One AZAgent shared by all game threads. Each game pins the checkpoint snapshot
    it started with, so retargeting the checkpoint never changes a game in progress."""

    def __init__(self, agent):
        self.agent, self.lock = agent, threading.Lock()

    def choose(self, game, snap):
        with self.lock:
            move = self.agent.choose_move(game, snap)
            return move, self.agent.last_value

    def current(self):
        """Reload if the checkpoint (or the symlink's target) changed; return the snapshot."""
        with self.lock:
            old = self.agent.snapshot
            if self.agent.maybe_reload():
                new = self.agent.snapshot
                log(f"checkpoint changed: {old.path} (iter {old.iter}) -> {new.path} (iter {new.iter})")
            return self.agent.snapshot


def send(ws, d):
    ws.send(json.dumps(d))


def create_game(ws, icon, prefs):
    send(ws, {"action": "create-game",
              "view_data": {"iconIndex": str(icon), "timeZone": get_tz(), "os": platform.system()},
              "preferences": prefs})


def is_over(g):
    return g.me["is_defeated"] or g.opponent["is_defeated"] or g.me["is_gone"] or g.opponent["is_gone"]


def play(ws, first_msg, agent, snap, rec, timeout, label):
    """Play one game on an already-matched connection. Closes ws and rec."""
    game = Game(first_msg)
    result = "?"
    n = 0
    try:
        while not is_over(game):
            if game.my_turn:
                move, value = agent.choose(game, snap)
                rec.write(bot_move=move, value=value)
                send(ws, {"action": "make-turn", "gameId": game.id, "cell": move})
                n += 1
            msg = json.loads(ws.recv(timeout=timeout))
            rec.write(msg=msg)
            game.update(msg)
        if game.opponent["is_defeated"] or game.opponent["is_gone"]:
            result = "bot won" + (" (opponent left)" if game.opponent["is_gone"] else "")
        else:
            result = "bot lost"
    except TimeoutError:
        send(ws, {"action": "concede", "gameId": game.id})
        result = f"no opponent move for {timeout:.0f}s, conceded"
    except ConnectionClosed:
        result = "connection closed"
    except Exception:
        result = "error: " + traceback.format_exc(limit=3)
    finally:
        rec.write(result=result)
        rec.close()
        try:
            ws.close()
        except Exception:
            pass
    log(f"[{label}] game {game.id[:8]} (iter {snap.iter}) over after {n} bot moves: {result}")


def start_game(ws, msg, args, agent, label, snap):
    rec = Recorder(args.record_dir)
    rec.start(tag=label)
    rec.write(preferences=msg.get("preferences"), agent="az", ckpt=snap.path, ckpt_iter=snap.iter,
              seat="bot-first" if msg["my_turn"] else "bot-second", mode=label)
    rec.write(msg=msg)
    log(f"[{label}] matched: game {msg['id'][:8]}, bot moves {'first' if msg['my_turn'] else 'second'}, iter {snap.iter}"
        + (f", recording to {rec.f.name}" if rec.f else ""))
    t = threading.Thread(target=play, args=(ws, msg, agent, snap, rec, args.timeout, label), daemon=True)
    t.start()


def host_bot_first(args, prefs, agent):
    """Always keep one connection waiting under `code`.

    The server deletes queued requests after an hour even if the connection is still
    open, and someone who joins while we're not (visibly) queued just gets queued
    themselves; two queued requests never match. So the waiting request is renewed every
    `--refresh` seconds. The old connection is closed first, so the new request can't
    match our own old one, and the new request pops anyone left waiting."""
    announced = False
    while True:
        ws = None
        try:
            ws = connect(URL)
            create_game(ws, args.icon, prefs)
            if not announced:
                log(f"[{prefs['code']}] waiting for an opponent under code '{prefs['code']}' "
                    f"(re-queueing every {args.refresh:.0f}s)")
                announced = True
            msg = json.loads(ws.recv(timeout=args.refresh))
        except TimeoutError:
            if ws is None:  # connect() itself timed out
                log(f"[{prefs['code']}] connect timed out; retrying")
                time.sleep(3)
            else:
                ws.close()  # renew: drop this request and queue a fresh one
            continue
        except (ConnectionClosed, OSError) as e:
            log(f"[{prefs['code']}] waiting connection dropped ({type(e).__name__}); reconnecting")
            if ws is not None:
                ws.close()
            time.sleep(3)
            continue
        if "me" not in msg:
            log(f"[{prefs['code']}] unexpected message: {str(msg)[:200]}")
            ws.close()
            continue
        # If someone was already queued, we joined second: still a fine game, just play it.
        start_game(ws, msg, args, agent, prefs["code"], agent.current())
        announced = False


def host_bot_second(args, prefs, agent):
    """Poll under `code-p2` so the human is always the queued (first) player."""
    while True:
        ws = None
        try:
            ws = connect(URL)
            create_game(ws, args.icon, prefs)
            try:
                msg = json.loads(ws.recv(timeout=args.p2_wait))
            except TimeoutError:
                ws.close()
                time.sleep(args.p2_interval)
                continue
        except (ConnectionClosed, OSError) as e:
            log(f"[{prefs['code']}] poll failed ({type(e).__name__}); retrying")
            time.sleep(5)
            continue
        if "me" not in msg:
            ws.close()
            continue
        if msg["my_turn"]:
            # we were the queued one -> we'd move first; bail so the human can rejoin
            send(ws, {"action": "concede", "gameId": msg["id"]})
            ws.close()
            log(f"[{prefs['code']}] joined as first player (game {msg['id'][:8]}), conceded; rejoin to play as first")
            continue
        start_game(ws, msg, args, agent, prefs["code"], agent.current())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--code", required=True, nargs="+",
                    help="one or more codes (give each person their own, or people entering the same code at "
                         "the same moment can be paired with each other). For each: <code> = bot moves first, "
                         "<code>-p2 = you move first (with --p2)")
    ap.add_argument("--ckpt", default=os.path.expanduser("~/main-fs/paper-tactics-jax/bot/current.pkl"),
                    help="checkpoint (default: the bot/current.pkl symlink managed by `python -m pt.bot_ckpt`)")
    ap.add_argument("--sims", type=int, default=256)
    ap.add_argument("--pt-path", default=os.path.expanduser("~/main-fs/paper-tactics-jax"))
    ap.add_argument("--record-dir", default="")
    ap.add_argument("--refresh", type=float, default=180,
                    help="re-queue the bot-first waiting request this often (server deletes queued requests after 1h)")
    ap.add_argument("--timeout", type=float, default=180, help="seconds without an opponent move before conceding")
    ap.add_argument("--icon", type=int, default=0)
    ap.add_argument("--url", default=DEFAULT_URL, help="server websocket URL (e.g. ws://localhost:8001 for a local test server)")
    ap.add_argument("--no-first", action="store_true", help="don't host the bot-first code")
    ap.add_argument("--p2", action="store_true", help="also poll <code>-p2 (you move first)")
    ap.add_argument("--p2-wait", type=float, default=1.0,
                    help="seconds to stay queued per poll (if you join inside this window the bot concedes and you rejoin)")
    ap.add_argument("--p2-interval", type=float, default=8.0, help="seconds between polls (max wait to get matched)")
    args = ap.parse_args()
    global URL
    URL = args.url

    sys.path.insert(0, args.pt_path)
    from pt.agent import AZAgent
    az = AZAgent(args.ckpt, num_simulations=args.sims)
    log(f"loaded {args.ckpt} -> {az.snapshot.path} (iter {az.ckpt_iter}), {args.sims} sims/move")
    agent = SharedAgent(az)

    base = {"size": 10, "turn_count": 3, "is_visibility_applied": False, "is_against_bot": False,
            "trench_density_percent": 0, "is_double_base": False}
    threads = []
    for code in args.code:
        if not args.no_first:
            threads.append(threading.Thread(target=host_bot_first, args=(args, {**base, "code": code}, agent), daemon=True))
        if args.p2:
            threads.append(threading.Thread(target=host_bot_second, args=(args, {**base, "code": code + "-p2"}, agent), daemon=True))
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
