import json
import os
import sys
import time
import platform
import argparse
import asyncio

from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK
from websockets.sync.client import ClientConnection

from agent import RandomAgent, HeuristicAgent

from game import Game

        

class Recorder:
    """Appends every server message (and our moves) to one JSONL file per game."""

    def __init__(self, record_dir):
        self.dir = record_dir
        self.f = None
        if record_dir:
            os.makedirs(record_dir, exist_ok=True)

    def start(self, tag=""):
        if self.dir:
            import uuid
            name = time.strftime("%Y%m%d-%H%M%S") + (f"-{tag}" if tag else "") + f"-{uuid.uuid4().hex[:6]}.jsonl"
            self.f = open(os.path.join(self.dir, name), "a")
            print("recording to", self.f.name)

    def write(self, **rec):
        if self.f:
            self.f.write(json.dumps({"t": time.time(), **rec}) + "\n")
            self.f.flush()

    def close(self):
        if self.f:
            self.f.close()
            self.f = None


recorder = Recorder(None)


# see https://stackoverflow.com/questions/1111056/get-time-zone-information-of-the-system-in-python
def get_tz():
    return time.tzname[time.daylight]

def wait_for_message(ws: ClientConnection, game=None, timeout=None):
    try:
        message = ws.recv(timeout=timeout)
        msg = json.loads(message)
        recorder.write(msg=msg)
        return msg
    except TimeoutError:
        concede(ws, game)
        return None

def wait_for_update(ws:ClientConnection, game, timeout=None):
    msg = wait_for_message(ws, game, timeout)
    if msg is not None:
        game.update(msg)
        return True
    return False
        

def send_json(ws: ClientConnection, dct):
    ws.send(json.dumps(dct))

def concede(ws: ClientConnection, game):
    send_json(ws, {
        'action': "concede",
        'gameId': game.id,
    })
    
def create_game(ws: ClientConnection, icon, preferences):
    send_json(ws, {
        'action': "create-game",
        'view_data': {'iconIndex': icon, 'timeZone': get_tz(), 'os': platform.system()}, # the timezone and os don't quite work yet
        'preferences': preferences,
    })

def make_move(ws: ClientConnection, game, move, value=None):
    recorder.write(bot_move=move, value=value)
    send_json(ws, {
        'action': "make-turn",
        'gameId': game.id,
        'cell': move,
    })

def main() -> None:

    parser = argparse.ArgumentParser()
    parser.add_argument('--size', type=int, default=10, help='size of the game board')
    parser.add_argument('--tc', type=int, default=3, help='turn count, i.e. how many moves do you get')
    parser.add_argument('--fog', type=bool, default=False, help='whether to play with fog of war (default no fog)')
    parser.add_argument('--bot', type=bool, default=False, help='whether to play against the default PT bot')
    parser.add_argument('--tdp', type=float, default=0, help='trench density percentage')
    parser.add_argument('--db', type=bool, default=False, help='whether to play with double bases (default single base)')
    parser.add_argument('--code', type=str, default="", help='game code, used to only match against players with the same code')
    parser.add_argument('--icon', type=int, default=0, help='which icon to use (default to X)')

    parser.add_argument('--agent', type=str, default='random', help='The type of Agent you would like to run: random, heuristic, az')
    parser.add_argument('--ckpt', type=str, default='', help='[az] checkpoint .pkl (reloaded between games if it changes)')
    parser.add_argument('--sims', type=int, default=256, help='[az] search simulations per move')
    parser.add_argument('--pt-path', type=str, default=os.path.expanduser('~/main-fs/paper-tactics-jax'), help='[az] path to paper-tactics-jax')
    parser.add_argument('--record-dir', type=str, default='', help='append every game (server messages + our moves) as JSONL here')
    parser.add_argument('--games', type=int, default=1, help='number of games to play in a row (0 = forever)')
    parser.add_argument('--timeout', type=float, default=600, help='seconds to wait for an opponent move before conceding (detects disconnects)')

    args = parser.parse_args()
    global recorder
    recorder = Recorder(args.record_dir)

    if args.agent == 'random':
        agent = RandomAgent()
    elif args.agent == 'heuristic':
        agent = HeuristicAgent()
    elif args.agent == 'az':
        sys.path.insert(0, args.pt_path)
        from pt.agent import AZAgent
        agent = AZAgent(args.ckpt, num_simulations=args.sims)
        print(f'loaded {args.ckpt} (iter {agent.ckpt_iter}), {args.sims} sims/move')
    else:
        raise NotImplementedError('unsupported agent type')

    preferences={
        'size': args.size,
        'turn_count': args.tc,
        'is_visibility_applied': args.fog,
        'is_against_bot': args.bot, # I am the bot now :)
        'trench_density_percent': args.tdp,
        'is_double_base': args.db,
        'code': args.code,
    }

    timeout = args.timeout

    played = 0
    while args.games == 0 or played < args.games:
        if args.agent == 'az' and agent.maybe_reload():
            print(f'reloaded checkpoint (iter {agent.ckpt_iter})')
        recorder.start()
        recorder.write(preferences=preferences, agent=args.agent, ckpt=args.ckpt,
                       ckpt_iter=getattr(agent, 'ckpt_iter', None))
        try:
            play_one_game(args, agent, preferences, timeout)
        finally:
            recorder.close()
        played += 1


def play_one_game(args, agent, preferences, timeout):
    try:
        with connect("wss://az7ndrlaxk.execute-api.eu-central-1.amazonaws.com/rolling") as ws:
            create_game(ws, str(args.icon), preferences)
            print('sent create game')
            mdct = wait_for_message(ws, game=None, timeout=None)
            print('game id:', mdct['id'])
            game = Game(mdct)
            success = True
            while True:
                while not game.my_turn: # wait until your turn, you silly bot!
                    success = wait_for_update(ws, game, timeout=timeout)
                    print('sup', game.opponent['is_defeated'], game.opponent['is_gone'])
                    if not success or game.opponent['is_defeated'] or game.opponent['is_gone'] or game.me['is_defeated']:
                        break

                if not success or game.opponent['is_defeated'] or game.opponent['is_gone'] or game.me['is_defeated']:
                    break

                print('my turn!')
                while game.my_turn:
                    if not success or game.me['is_defeated'] or game.opponent['is_defeated'] or game.opponent['is_gone']:
                        break
                    move = agent.choose_move(game)
                    value = getattr(agent, 'last_value', None)
                    print(move, '' if value is None else f'(value {value:+.2f})')
                    make_move(ws, game, move, value)

                    success = wait_for_update(ws, game, timeout=timeout)
                if not success or game.me['is_defeated'] or game.opponent['is_defeated'] or game.opponent['is_gone']:
                    break

            if not success:
                print('timed out')
            elif game.opponent['is_defeated'] or game.opponent['is_gone']:
                print('I win!')
            elif game.me['is_defeated']:
                print('I lose :(')

    except ConnectionClosed as e:
        if isinstance(e, ConnectionClosedOK):
            print('websocket closed normally')

        elif isinstance(e, ConnectionClosedError):
            print('error on websocket close: timeout?')


if __name__ == "__main__":
    main()