import uuid
import inspect
from typing import Dict, List, Type, Tuple, Union, TYPE_CHECKING, get_type_hints, Callable

import pygame.image
from pygame import Rect
from rich import print

from engine.unresolved import Unresolved
from engine.helpers import get_matching_objects, dict_diff
from engine.events import LogicTick, GameTickComplete, GameTickStart, EntityCreated

if TYPE_CHECKING:
    from gamemode_client import GamemodeClient
    from gamemode_server import GamemodeServer


class Entity:
    def __init__(self, interaction_rect: Rect, game: Union["GamemodeClient", "GamemodeServer"], updater: str, id: str = None):

        self.interaction_rect = interaction_rect
        self.updater = updater
        self.game = game
        self.last_tick_dict = {}
        
        if id is None:
            id = str(uuid.uuid4())
        
        self.id = id

        # add entity to the game state automatically
        self.game.entities[self.id] = self

        self.game.event_subscriptions[GameTickComplete] += [self.detect_updates] 

    def set_last_tick_dict(self, event: GameTickStart):
        """Set a keyframe of the serialized object before it ticked"""

        self.last_tick_dict = self.dict()

    def detect_updates(self, event: GameTickComplete):
        """Compare entity state from last tick to this tick to find differences"""

        current_tick_dict = self.dict()
        
        # this indicates that the entity did not exist last tick
        if self.last_tick_dict == {}:
            self.game.network_update(
                update_type="create",
                entity_id=self.id,
                data=self.dict(),
                entity_type_string=self.game.lookup_entity_type_string(self)
            )

            self.last_tick_dict = current_tick_dict

            return

        if current_tick_dict != self.last_tick_dict:
            
            update_data_dict = dict_diff(self.last_tick_dict, current_tick_dict)

            #print(update_data_dict)

            self.game.network_update(update_type="update", entity_id=self.id, data=update_data_dict)
        
        self.last_tick_dict = current_tick_dict
                
    def resolve(self):
        """Convert any of the entity's attributes that are of type 'Unresolved' to the actual entity they are pointing to"""

        for attribute_name, attribute in self.__dict__.copy().items():

            if type(attribute) is not Unresolved:
                continue

            resolved_attribute = self.game.entities[
                attribute.uuid
            ]

            self.__setattr__(attribute_name, resolved_attribute)

    def dict(self) -> Dict[str, Union[int, bool, str, list]]:
        """Serialize the entity's data"""

        data_dict = {
            "interaction_rect": list(self.interaction_rect),
            "updater": self.updater
        }

        return data_dict

    @classmethod
    def create(cls, entity_data: Dict[str, Union[int, bool, str, list]], entity_id: str, game: Union[Type["GamemodeClient"], Type["GamemodeServer"]]) -> Type["Entity"]:
        """Use serialized entity data to create a new entity"""

        entity_data["interaction_rect"] = Rect(
             entity_data["interaction_rect"]
        )

        entity_data["updater"] = entity_data["updater"]

        return cls(game=game, id=entity_id, **entity_data)

    def update(self, update_data):
        """Use serialized entity data to update existing entity"""

        for attribute in update_data:

            match attribute:

                case "interaction_rect":
                    
                    self.interaction_rect.update(
                        update_data["interaction_rect"]
                    )

                case "updater":
                    self.updater = update_data["updater"]
        
    def draw(self):
        """Draw the entity onto the game screen"""

        #pygame.draw.rect(self.game.screen, (255, 255, 255), self.interaction_rect)
        for tile in self.tiles:
            pygame.draw.rect(
                surface=self.game.screen, 
                color=(255,255,255), 
                rect=Rect(tile.body.position[0], tile.body.position[1], width=10, height=10)
            )