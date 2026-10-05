import unittest
from game_engine import GameEngine

class EngineSmokeTest(unittest.TestCase):
    def test_three_player_flow(self):
        e=GameEngine(); g=e.new_game(-100,1,'A')
        e.join(g,2,'B'); e.join(g,3,'C'); e.start_draft(g)
        while g.status=='drafting':
            e.draft_pick(g,e.current_drafter(g),g.draft_pool[0])
        self.assertEqual(g.status,'selecting')
        for uid,p in g.players.items():
            e.race_select(g,uid,p.team[0])
        self.assertEqual(g.status,'racing')
        self.assertEqual(len(g.race.racers),3)

if __name__=='__main__': unittest.main()
