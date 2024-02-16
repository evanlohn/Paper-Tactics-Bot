import json
import time
import platform
import argparse
import asyncio

from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK
from websockets.sync.client import ClientConnection

from agent import RandomAgent, HeuristicAgent

from game import Game

        

# see https://stackoverflow.com/questions/1111056/get-time-zone-information-of-the-system-in-python
def get_tz():
    return time.tzname[time.daylight]

def wait_for_message(ws: ClientConnection, game=None, timeout=None):
    try:
        message = ws.recv(timeout=timeout)
        return json.loads(message)
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

def make_move(ws: ClientConnection, game, move):
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

    parser.add_argument('--agent', type=str, default='random', help='The type of Agent you would like to run. See client.py for options.')

    args = parser.parse_args()

    if args.agent == 'random':
        agent = RandomAgent()
    elif args.agent == 'heuristic':
        agent = HeuristicAgent()
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

    timeout= 600

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
                    print(move)
                    make_move(ws, game, move)

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