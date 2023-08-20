from typing import Dict, Optional, Type, Union, Tuple, List, TYPE_CHECKING
import time
import math

import pygame
import pymunk
from pymunk import Vec2d
from pymunk import Shape, Body
from pymunk.constraints import DampedSpring

from engine.entity import Entity
from engine import events
from engine.gamemode_client import GamemodeClient
from engine.gamemode_server import GamemodeServer
from engine.tile import Tile
from engine.events import Tick, NewEntity
from engine.unresolved import Unresolved

class FreezableTileMaker(Entity):
    def __init__(self, game: GamemodeClient | GamemodeServer, updater: str, id: str | None = None):
        super().__init__(game, updater, id)

        self.game.event_subscriptions[events.KeyReturn] += [
            self.spawn_tile
        ]

        self.game.event_subscriptions[Tick] += [
            self.set_starting_point
        ]

        self.starting_point: Tuple[int, int] = [0,0]

        self.making_tile: bool = False

        self.last_spawn = 0

    def set_starting_point(self, event: Tick):
        
        if not pygame.key.get_pressed()[pygame.K_c]:
            self.making_tile = False 

            return

        if self.making_tile:
            return

        self.starting_point = pygame.mouse.get_pos()

        self.making_tile = True 
    
    def spawn_tile(self, event: events.KeyReturn):

        if not self.making_tile:
            return 
        
        if time.time() - self.last_spawn < 3:
            return
        
        body=pymunk.Body(
            body_type=pymunk.Body.STATIC
        )

        center = pygame.Rect([self.starting_point[0], self.starting_point[1], pygame.mouse.get_pos()[0] - self.starting_point[0], pygame.mouse.get_pos()[1] - self.starting_point[1]]).center

        body.position = center
    
        shape=pymunk.Poly.create_box(
            body=body,
            size=(
                pygame.mouse.get_pos()[0] - self.starting_point[0],
                pygame.mouse.get_pos()[1] - self.starting_point[1]
            )
        )

        shape.friction = 0.5
        shape.elasticity = 0.1
        
        tile = FreezableTile(
            body=body,
            shape=shape,
            game=self.game,
            updater=self.game.uuid
        )

        self.last_spawn = time.time()
    
    def draw(self):

        if not self.making_tile:
            return
        
        pygame.draw.rect(
            self.game.screen,
            color=(255,255,255),
            rect=[self.starting_point[0], self.starting_point[1], pygame.mouse.get_pos()[0] - self.starting_point[0], pygame.mouse.get_pos()[1] - self.starting_point[1]],
            width=1
        )

class Player(Tile):
    def __init__(self, game: GamemodeClient | GamemodeServer, updater: str, body: Body = None, shape: Shape = None, weapon: "Weapon" = None, id: str | None = None):
        
        if body is None or shape is None:
            body=pymunk.Body(
                mass=20,
                moment=float("inf"),
                body_type=pymunk.Body.DYNAMIC
            )

            body.position = game.screen.get_bounding_rect().center
    
            shape=pymunk.Poly.create_box(
                body=body,
                size=(20,40)
            )

            shape.friction = 0.5

        super().__init__(body, shape, game, updater, id)

        self.weapon: Weapon = weapon

        self.game.event_subscriptions[Tick] += [
            self.handle_keys
        ]

    def constrain_weapon(self, event: Tick):
        if not self.weapon:
            return 
        
        # already has constraint
        if len(self.weapon.body.constraints) > 0:
            return
        
        weapon_constraint = pymunk.constraints.PinJoint(self.body, self.weapon.body)
        weapon_constraint.collide_bodies = False
        self.game.space.add(weapon_constraint)
        
    def serialize(self) -> Dict[str, int | bool | str | list]:
        data_dict = super().serialize()

        if self.weapon:
            data_dict["weapon"] = self.weapon.id
        else:
            data_dict["weapon"] = None
        
        return data_dict
        
    @classmethod
    def create(self, entity_data: Dict[str, int | bool | str | list], entity_id: str, game: GamemodeClient | GamemodeServer) -> type[Tile]:
        
        if entity_data["weapon"]:
            entity_data["weapon"] = Unresolved(entity_data["weapon"])
        else:
            entity_data["weapon"] = None

        return super().create(entity_data, entity_id, game)
    
    def update(self, update_data: dict):
        super().update(update_data)
        
        for attribute_name, attribute_value in update_data.items():

            match attribute_name:
                
                case "weapon":

                    if attribute_value:
                        self.weapon = Unresolved(update_data["weapon"])
                    self.weapon = None
        
    def handle_keys(self, event: Tick):
        
        # move right
        if pygame.key.get_pressed()[pygame.K_d]:
            #print("right!")
            self.body.apply_force_at_local_point(
                (1000000,0),
                self.body.center_of_gravity
            )
        
        if pygame.key.get_pressed()[pygame.K_a]:
            #print("left")
            self.body.apply_force_at_local_point(
                (-1000000,0),
                self.body.center_of_gravity
            )
        
        if pygame.key.get_pressed()[pygame.K_SPACE]:
            print("jump")

            if self.body.velocity.y != 0:
                return 
            
            self.body.apply_impulse_at_local_point(
                (0,-10000),
                self.body.center_of_gravity
            )
    
class Weapon(Tile):
    def __init__(self, game: GamemodeClient | GamemodeServer, updater: str, player: Optional[Player] = None, body: Body = None, shape: Shape = None, id: str | None = None):

        body = Body(
            body_type=pymunk.Body.KINEMATIC
        )

        shape = pymunk.Poly.create_box(
            body=body,
            size=(30,10)
        ) 

        super().__init__(body, shape, game, updater, id)

        self.game.event_subscriptions[Tick] += [
            self.aim,
            self.follow_player
        ]

        self.game.event_subscriptions[events.MouseLeftClick] += [
            self.shoot
        ]

        self.player = player
    
    def aim(self, event: Tick):
        if not self.player:
            return

        self.body.angle = math.atan2(
            pygame.mouse.get_pos()[1] - self.body.position.y,
            pygame.mouse.get_pos()[0] - self.body.position.x
        )
    
    def follow_player(self, event: Tick):
        if not self.player:
            return
        
        self.body.velocity = self.player.body.velocity
        
        self.body.position = (
            self.player.body.position.x + 30,
            self.player.body.position.y - 20
        )
    
    def shoot(self, event: events.MouseLeftClick):
        bullet = Bullet(
            game=self.game,
            updater=self.game.uuid
        )

        bullet.body.angle = self.body.angle

        mouse_pos = pygame.mouse.get_pos()

        # vector from weapon to mouse
        bullet_path_vector = Vec2d(
            x = mouse_pos[0] - self.body.position.x,
            y = mouse_pos[1] - self.body.position.y
        )

        bullet.body.position = (
            self.shape.bb.right + 20,
            self.body.position.y - 20
        )

        bullet.body.velocity = self.body.velocity + (bullet_path_vector.normalized() * 3000)

    def serialize(self) -> Dict[str, int | bool | str | list]:
        data_dict = super().serialize()

        if self.player:
            data_dict["player"] = self.player.id
        else:
            data_dict['player'] = None

        return data_dict
    
    def update(self, update_data: dict):
        super().update(update_data)

        for attribute_name, attribute_value in update_data.items():

            match attribute_name:

                case "player":
                    
                    if attribute_value:
                        self.player = attribute_value
                    else:
                        self.player = None
    
    @classmethod
    def create(self, entity_data: Dict[str, int | bool | str | list], entity_id: str, game: GamemodeClient | GamemodeServer) -> type[Tile]:
        
        if entity_data["player"]:
            entity_data["player"] = Unresolved(entity_data["player"])
        else:
            entity_data["player"] = None
        
        return super().create(entity_data, entity_id, game)
        

class Bullet(Tile):
    def __init__(self, game: GamemodeClient | GamemodeServer, updater: str, weapon: Weapon = None, body: Body = None, shape: Shape = None, id: str | None = None):

        body = Body(
            mass = 0.1,
            body_type=pymunk.Body.DYNAMIC
        )

        shape = pymunk.Poly.create_box(
            body=body,
            size=(10,5)
        )

        body.moment = pymunk.moment_for_box(
            body.mass,
            (10, 5)
        )

        super().__init__(body, shape, game, updater, id)

        self.weapon = weapon
    
    def serialize(self) -> Dict[str, int | bool | str | list]:
        data_dict = super().serialize()

        if self.weapon:
            data_dict["weapon"] = self.weapon.id
        
        else:
            data_dict["weapon"] = None

        return data_dict

    def update(self, update_data: dict):
        super().update(update_data)

        for attribute_name, attribute_value in update_data.items():
            match attribute_name:
                case "weapon":

                    if attribute_value:
                        self.weapon = Unresolved(attribute_value)
                    else:
                        self.weapon = attribute_value
    
    @classmethod
    def create(self, entity_data: Dict[str, int | bool | str | list], entity_id: str, game: GamemodeClient | GamemodeServer) -> type[Tile]:
        
        if entity_data["weapon"]:
            entity_data["weapon"] = Unresolved(entity_data["weapon"])
        else:
            entity_data["weapon"] = None
        
        return super().create(entity_data, entity_id, game)

class FreezableTile(Tile):
    def __init__(self, body: Body, shape: Shape, game: GamemodeClient | GamemodeServer, updater: str, id: str | None = None):
        super().__init__(body, shape, game, updater, id)

        self.game.event_subscriptions[Tick] += [
            self.create_constraint,
            self.freeze,
            self.unfreeze,
            self.move
        ]
    
    def draw(self):
        super().draw()
        
    def freeze(self, event: Tick):
        if not pygame.mouse.get_pressed()[2]:
            return
        
        # shape contains mouse
        if not self.shape.bb.contains_vect(
            pygame.mouse.get_pos()
        ):
            return

        self.body.body_type = pymunk.Body.STATIC
    
    def unfreeze(self, event: Tick):
        if not pygame.mouse.get_pressed()[1]:
            return
        
        # shape contains mouse
        if not self.shape.bb.contains_vect(
            pygame.mouse.get_pos()
        ):
            return
        
        self.body.body_type = pymunk.Body.DYNAMIC
        
        shape_width = self.shape.bb.right- self.shape.bb.left
        shape_height = self.shape.bb.top - self.shape.bb.bottom

        print(shape_width)
        print(shape_height)

        self.body.mass = 20
        moment = pymunk.moment_for_box(
            self.body.mass,
            (shape_width, shape_height)
        )

        self.body.moment = moment
    
    def move(self, event: Tick):
        if not pygame.mouse.get_pressed()[0]:
            return
        
        # shape contains mouse
        if not self.shape.bb.contains_vect(
            pygame.mouse.get_pos()
        ):
            return
        
        self.body.position = pygame.mouse.get_pos()
        self.body.velocity = (0,0)
        self.body.angle = 0

    def create_constraint(self, event: Tick):

        # left clicking
        if not pygame.mouse.get_pressed()[0]:
            return
        
        # shape contains mouse
        if not self.shape.bb.contains_vect(
            pygame.mouse.get_pos()
        ):
            return