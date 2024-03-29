from abc import ABC, abstractproperty, abstractmethod
from typing import Dict, Optional, Union, TYPE_CHECKING

from onepointsix.entity import Entity

if TYPE_CHECKING:
    from onepointsix.gamemode_client import GamemodeClient
    from onepointsix.gamemode_server import GamemodeServer

class DrawableEntity(Entity):
    
    def __init__(
        self, 
        game: Union["GamemodeClient", "GamemodeServer"], 
        updater: str, 
        draw_layer: int, 
        id: str | None = None,
        *args,
        **kwargs
    ):
        super().__init__(
            game, 
            updater, 
            id,
            *args,
            **kwargs
        )

        self.draw_layer = draw_layer

    @abstractmethod
    def draw(self):
        pass

    def serialize(self) -> Dict[str, int | bool | str | list | None]:
        data_dict = Entity.serialize(self)

        data_dict.update(
            {
                "draw_layer": self.draw_layer
            }
        )
        
        return data_dict
    
    def update(self, update_data: dict):
        Entity.update(self, update_data)

        for attribute_name, attribute_value in update_data.items():

            match attribute_name:

                case "draw_layer":
                    self.draw_layer = attribute_value               
    
    @staticmethod
    def deserialize(entity_data: Dict[str, int | bool | str | list], entity_id: str, game: Union["GamemodeClient", "GamemodeServer"]) -> Dict[str, int | bool | str | list]:
        
        entity_data["draw_layer"] = entity_data["draw_layer"]

        entity_data.update(Entity.deserialize(entity_data=entity_data, entity_id=entity_id, game=game))

        return entity_data
