
# stuff your agents might want to use

# the basics of what exists in the game. trenches aren't considered yet :/
class GameState:
    def __init__(self, sz, units, walls, opp_units, opp_walls, trenches) -> None:
        self.sz = sz
        self.units = [tuple(x) for x in units]
        self.walls = [tuple(x) for x in walls]
        self.opp_units = [tuple(x) for x in opp_units]
        self.opp_walls = [tuple(x) for x in opp_walls]
        self.trenches = [tuple(x) for x in trenches]

    def unpack(self):
        return self.sz, self.units, self.walls, self.opp_units, self.opp_walls, self.trenches
    
    def flip(self):
        return GameState(self.sz, self.opp_units, self.opp_walls, self.units, self.walls, self.trenches)

def pos_of_xy(x, y, sz):
    return (y - 1) * sz + (x - 1)

def xy_of_pos(pos, sz): 
    return (pos % sz + 1, pos // sz + 1)

def neighbors(pos, sz):
    x, y = xy_of_pos(pos, sz)
    filt = lambda v: v > 0 and v <= sz
    cands = [(x + i, y + j) for i in range(-1, 2) for j in range(-1, 2) if not (i == 0 and j == 0)]
    return [pos_of_xy(c[0], c[1], sz) for c in cands if filt(c[0]) and filt(c[1])]

def get_moves(gs: GameState):
    sz, units, walls, opp_units, opp_walls, _ = gs.unpack()
    num_pos = sz * sz

    alive = [pos_of_xy(p[0], p[1], sz) for p in units] 
    units = set(alive)
    # but this list ^^ gets expanded in the first while loop to include living walls

    walls = set([pos_of_xy(p[0], p[1], sz) for p in walls])

    opp_units = set([pos_of_xy(p[0], p[1], sz) for p in opp_units])
    opp_walls = set([pos_of_xy(p[0], p[1], sz) for p in opp_walls])

    #trenches = set([pos_of_xy(p, sz) for p in trenches]) # don't need for reachability, treat like blank square

    reachable = [False for _ in range(num_pos)] # the valid squares to play on
    seen = [i in alive for i in range(num_pos)] #tiles already in alive, hence don't want to re-add

    num_expanded = 0 # number of units that have finished donating life and giving reachability
    num_reachable = 0
    while num_expanded < len(alive):
        curr = alive[num_expanded]
        for np in neighbors(curr, sz):
            #print(curr, np)
            if (np not in units) and (np not in walls) and (np not in opp_walls):
                reachable[np] = True   #non-walled and non-self-owned neighbors are reachable
                num_reachable += 1
            elif not seen[np] and (np in walls):
                alive.append(np) #a wall neighboring an alive square is alive
                seen[np] = True # don't re-add this to alive
        num_expanded+=1
    return [xy_of_pos(i, sz) for (i, p) in enumerate(reachable) if p]

def sim_move(gs: GameState, move):
    sz, units, walls, opp_units, opp_walls, trenches = gs.unpack()
    units, walls, opp_units, opp_walls, trenches = units[:], walls[:], opp_units[:], opp_walls[:], trenches[:]
    filt = [u for u in opp_units if u != move]
    
    if len(filt) < len(opp_units):
        opp_units = filt
        walls.append(move)
    else:
        filt2 = [u for u in trenches if u != move]
        if len(filt2) < len(trenches):
            trenches = filt2
            walls.append(move)
        else:
            units.append(move)
    return GameState(sz, units, walls, opp_units, opp_walls, trenches)