import random
from agent_utils import GameState, get_moves, sim_move, pos_of_xy
from game import Game

class Agent:
    def __init__(self) -> None:
        pass

    def choose_move(self, game):
        pass

class RandomAgent(Agent):
    def __init__(self) -> None:
        super().__init__()
    
    def choose_move(self, game):
        candidates = game.me['reachable']
        return random.choice(candidates)
    
class HeuristicAgent(Agent):
    def __init__(self) -> None:
        super().__init__()
        self.move_seq = None

    def unroll_tree(self, start_gs, turns):
        q = [(turns, start_gs, [])]
        done = []
        while len(q) > 0:
            tl, gs, mvseq = q.pop()
            append_to = q if tl > 1 else done
            #print(gs.units)
            #print(get_moves(gs))
            avail_mvs = get_moves(gs)
            if len(avail_mvs) == 0:
                done.append((tl - 1, gs, mvseq))
            for mv in avail_mvs:
                append_to.append((tl - 1, sim_move(gs, mv), mvseq + [mv]))

        seen_moves = set()
        deduped = []
        for tl, gs, mvseq in done:
            smvs = tuple(sorted(mvseq, key=lambda tup: pos_of_xy(tup[0], tup[1], gs.sz)))
            if smvs not in seen_moves:
                deduped.append((tl, gs, mvseq))
            seen_moves.add(smvs)
        return deduped

    def choose_move_seq(self, game: Game):
        gs = GameState(game.preferences['size'], game.me['units'], game.me['walls'], game.opponent['units'], game.opponent['walls'], game.trenches)
        turns = game.turns_left

        done = self.unroll_tree(gs, turns)

        
        scored = sorted([(gs, mvs, self.eval_state(gs)) for _, gs, mvs in done], key=lambda x: -x[2])
        continue_eval = [gs.flip() for gs, _, _ in  scored[:10]]

        worst_cases = []
        for gs2 in continue_eval:
            done2 = self.unroll_tree(gs2, turns)
            worst_cases.append(max([(gs, mvs, self.eval_state(gs)) for _, gs, mvs in done2], key=lambda x: x[2]))
        best_worst_case = min(list(range(len(worst_cases))), key = lambda ind: worst_cases[ind][2])
        best_worst_val = worst_cases[best_worst_case][2]
        iset = [i for i in list(range(len(worst_cases))) if worst_cases[i][2] == best_worst_val]

        mset = [scored[i][1] for i in iset]
        print(-best_worst_val)
        return random.choice(mset)
        

    def choose_move(self, game: Game):
        if self.move_seq is None:
            self.move_seq = self.choose_move_seq(game)
            print(self.move_seq)

        tl = game.turns_left
        ind = game.preferences['turn_count'] - tl
        mv = self.move_seq[ind]
        if tl == 1:
            self.move_seq = None # prepare to replan
        return mv
    
    def eval_state(self, gs: GameState):
        return len(get_moves(gs)) - len(get_moves(gs.flip()))
        #return - len(get_moves(gs.flip()))
