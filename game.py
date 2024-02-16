"""
Responses look like this:
{"id": "825074cfccd64087adc6a5324ffc3e31", "turns_left": 3, "my_turn": false, 
"me": {"units": [[10, 10]], "walls": [], "reachable": [[9, 10], [10, 9], [9, 9]], 
"view_data": {"iconIndex": "0", "timeZone": "EDT", "os": "Darwin"}, 
"is_gone": false, "is_defeated": false}, 
"opponent": {"units": [[1, 1]], "walls": [], "reachable": [],
"view_data": {"os": "Android", "timeZone": "America/New_York", "iconIndex": "34"}, 
"is_gone": false, "is_defeated": false},
"trenches": [], 
"preferences": {"size": 10, "turn_count": 3, "is_visibility_applied": false, "is_against_bot": false, "trench_density_percent": 0, "is_double_base": false, "code": ""}}
"""
class Game:
    def __init__(self, ws_dct) -> None:
        self.update(ws_dct)
        self.preferences = ws_dct['preferences']

    def update(self, ws_dct):
        self.id = ws_dct['id']
        self.my_turn = ws_dct['my_turn']
        self.turns_left = ws_dct['turns_left']
        self.me = ws_dct['me']
        self.opponent = ws_dct['opponent']
        self.trenches = ws_dct['trenches']