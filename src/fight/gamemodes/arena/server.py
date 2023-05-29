from pygame import Rect

from engine.gamemode_server import GamemodeServer
from engine.events import ServerStart
from fight.gamemodes.arena.entities import Player, Floor, Shotgun, Cursor

class ArenaServer(GamemodeServer):
    def __init__(self, tick_rate):
        super().__init__(tick_rate=tick_rate)

        self.entity_type_map.update(
            {
                "player": Player,
                "floor": Floor,
                "shotgun": Shotgun,
                "cursor": Cursor
            }
        )

        self.event_subscriptions[ServerStart] += [
            self.start
        ]
    
    def start(self, event: ServerStart):

        floor = Floor(
            rect=Rect(0,600,1920,20),
            game=self,
            updater="server"
        )



        