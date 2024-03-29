import socket
import json
from collections import defaultdict
from copy import deepcopy
from typing import List, Literal, Optional, Type, Dict, Union, Tuple, NewType
from types import MethodType
import time
import zlib
import pathlib
from rich import print

import pygame
from pygame import Rect

from onepointsix import headered_socket
from onepointsix.headered_socket import Disconnected
from onepointsix.exceptions import MalformedUpdate, InvalidUpdateType
from onepointsix.events import Tick, Event, DisconnectedClient, NewClient, ReceivedClientUpdates, UpdatesLoaded, ServerStart, TickStart, TickComplete, NetworkTick, ResourcesLoaded, GameStart
from onepointsix.entity import Entity


class GamemodeServer:
    """
    Very similar to the GamemodeClient but with some important differences:
    - Holds entities that wouldnt make sense for clients to create, like level elements
    - Receives updates from individual clients and distributes them to every other client

    Could be theoretically be replaced by setting one client as a "master", then using p2p networking, but that would require every client to be port forwarded
    
    Basically only exists to simplify networking
    """

    def __init__(self, server_ip: str = socket.gethostname(), server_port: int = 5560, network_compression: bool = True):

        pygame.init()

        self.socket = headered_socket.HeaderedSocket(socket.AF_INET, socket.SOCK_STREAM)

        self.client_sockets: Dict[str, headered_socket.HeaderedSocket] = {}
        self.entities: Dict[str, Entity] = {}
        self.entity_type_map: Dict[str, Type[Entity]] = {}
        self.updates_to_load: List[dict] = []
        self.uuid = "server"
        self.server_clock = pygame.time.Clock()
        self.update_queue: defaultdict[str, List[dict]] = defaultdict(list)
        self.event_subscriptions: defaultdict[Type[Event], list] = defaultdict(list)
        self.server_ip = server_ip
        self.server_port = server_port
        self.tick_count = 0
        self.last_tick = time.time()
        self.network_compression = network_compression
        self.resources: Dict[str, pygame.Surface] = {}
        self.dt = 0.1 # i am initializing this with 0.1 instead of 0 because i think it might break stuff

        self.event_subscriptions[ReceivedClientUpdates] += [
            self.load_updates
        ]

        self.event_subscriptions[ServerStart] += [
            self.load_resources
        ]

        self.event_subscriptions[UpdatesLoaded] += [
            self.send_client_updates
        ]

        self.event_subscriptions[ServerStart] += [
            self.enable_socket
        ]

        self.event_subscriptions[NewClient] += [
            self.handle_new_client
        ]

        self.event_subscriptions[Tick] += [
            self.increment_tick_counter,
            self.accept_new_clients,
            self.receive_client_updates 
        ]

        self.event_subscriptions[TickStart] += [
            self.measure_dt
        ]
    
    def measure_dt(self, event: TickStart):
        """Measure the time since the last tick and update self.dt"""
        self.dt = time.time() - self.last_tick

        self.last_tick = time.time()

    def enable_socket(self, event: ServerStart):
        self.socket.bind((self.server_ip, self.server_port))
        self.socket.setblocking(False)
        self.socket.listen(5)

        print("server online...")

    def trigger(self, event: Event):

        for function in self.event_subscriptions[type(event)]:
            if function.__self__.__class__.__base__ == GamemodeServer:
                # if the object this listener function belongs to has a base class that is GamemodeServer, then we don't need to check if we should run it
                # this is because we never receive other user's GamemodeServer objects

                # we need to do this check because the GamemodeServer object does not have an "updater" attribute
                pass
            # dont call function if the entity this function belongs to isnt ours
            elif function.__self__.updater != self.uuid:
                continue
            
            function(event) 

    def network_update(self, update_type: Union[Literal["create"], Literal["update"], Literal["delete"]], entity_id: str, destinations: Optional[List[str]] = None, data: Optional[dict] = None, entity_type_string: Optional[str] = None):
        """Queue up a network update for specified client uuid(s)"""

        if update_type not in ["create", "update", "delete"]:
            raise InvalidUpdateType(f"Update type {update_type} is invalid")

        if update_type == "create" and entity_type_string is None:
            raise MalformedUpdate("Create update requires 'entity_type_string' parameter")

        if update_type == "create" and entity_type_string not in self.entity_type_map:
            raise MalformedUpdate(f"Entity type {entity_type_string} does not exist in the entity type map")

        # if no destinations are specified, we just send the update to all connected clients
        if destinations is None:
            destinations = list(self.client_sockets.keys())

        update = {
            "update_type": update_type,
            "entity_id": entity_id,
            "entity_type": entity_type_string,
            "data": data
        }
        
        for destination in destinations:
            self.update_queue[destination].append(update)
    
    def load_resources(self, event: GameStart):
        for sprite_path in pathlib.Path("resources").rglob("*.png"):
            sprite_path_string = str(sprite_path)
            # replace windows file path backslashes with forward slashes
            sprite_path_string = sprite_path_string.replace("\\", "/")
            self.resources[sprite_path_string] = pygame.image.load(sprite_path)

        self.trigger(ResourcesLoaded())

    def load_updates(self, event: ReceivedClientUpdates):

        for update in deepcopy(self.updates_to_load):
            
            match update["update_type"]:

                case "create":

                    print(f"created entity {update['entity_id']}")

                    entity_class = self.entity_type_map[
                        update["entity_type"]
                    ]

                    deserialized_data = entity_class.deserialize(
                        entity_data=update["data"], 
                        entity_id=update["entity_id"], 
                        game=self
                    )
                    
                    entity_class(game=self, id=update["entity_id"], **deserialized_data)

                case "update":

                    # sometimes entity updates will come in for entities that have killed because latency
                    if update["entity_id"] not in self.entities.keys():
                        continue

                    updating_entity = self.entities[
                        update["entity_id"]
                    ]

                    updating_entity.update(
                        update["data"]
                    )

                case "delete":

                    print(f"deleting entity {update['entity_id']} {self.tick_count}")

                    print(self.updates_to_load)

                    try:
                        self.entities[update["entity_id"]].kill()
                    except KeyError:
                        # THIS IS A BANDAID FIX
                        pass

                

        self.updates_to_load = []

        for entity in self.entities.values():

            entity.resolve()

        self.trigger(UpdatesLoaded())

    def lookup_entity_type_string(self, entity: Entity) -> Optional[str]:
        """Find entity type's corresponding type string in entity_type_map"""

        entity_type_string = None

        for possible_entity_type_string, entity_type in self.entity_type_map.items():
            if type(entity) is entity_type or entity is entity_type: # this allows looking up an instance of an entity or just the class of an entity
                entity_type_string = possible_entity_type_string
        
        if entity_type_string ==  None:
            raise KeyError(f"Entity type {type(entity)} does not exist in entity type map")
    
        else:
            return entity_type_string

        
    def handle_new_client(self, event: NewClient):

        print("New connecting client")

        # make server socket blocking temporarily, because we need this data now
        event.new_client.setblocking(True)

        client_uuid = event.new_client.recv_headered().decode("utf-8")

        event.new_client.setblocking(False)

        self.client_sockets[client_uuid] = event.new_client

        if len(self.entities) == 0:
            
            empty_update = json.dumps([])

            empty_update_bytes = bytes(empty_update, "utf-8")

            if self.network_compression:
                empty_update_bytes = zlib.compress(empty_update_bytes, zlib.Z_BEST_COMPRESSION)

            event.new_client.send_headered(
                empty_update_bytes
            )

            print("no entities, sending empty update")

        else:
            for entity in self.entities.values():

                entity_type_string = self.lookup_entity_type_string(entity)
                
                data = entity.serialize()

                self.network_update(update_type="create", entity_id=entity.id, data=data, entity_type_string=entity_type_string, destinations=[client_uuid])
                
            self.send_client_updates()

    def increment_tick_counter(self, event: Tick):
        self.tick_count += 1

    def handle_client_disconnect(self, event: DisconnectedClient):
        
        disconnected_client_uuid = event.disconnected_client_uuid
        
        for entity_uuid, entity in self.entities.copy().items():

            if entity.updater == disconnected_client_uuid:
                del self.entities[entity_uuid]

                self.network_update(
                    update_type="delete",
                    entity_id=entity_uuid,
                    destinations=list(self.client_sockets.keys())
                )
        
        print(f"{disconnected_client_uuid} disconnected")
        
        del self.client_sockets[disconnected_client_uuid]

        del self.update_queue[disconnected_client_uuid]
        
    def accept_new_clients(self, event: Tick):

        try:
            new_client, address = self.socket.accept()

            self.trigger(NewClient(new_client))

        except BlockingIOError: 
            pass
    
    def receive_client_updates(self, event: Tick):

        for sending_client_uuid, sending_client in self.client_sockets.copy().items():
            
            try:
                
                incoming_updates_bytes = sending_client.recv_headered()

            except Disconnected:

                self.trigger(DisconnectedClient(sending_client_uuid))

                continue

            except BlockingIOError:
                continue

            if self.network_compression:
                incoming_updates_bytes = zlib.decompress(incoming_updates_bytes)

            incoming_updates = json.loads(incoming_updates_bytes.decode("utf-8"))
            
            #self.validate_updates

            self.updates_to_load += incoming_updates

            for receiving_client_uuid, receiving_client in self.client_sockets.items():

                if sending_client_uuid is receiving_client_uuid:
                    continue
                
                #print(self.update_queue[receiving_client_uuid])

                self.update_queue[receiving_client_uuid] += incoming_updates
        
        self.trigger(ReceivedClientUpdates())

    def send_client_updates(self, event: Optional[ReceivedClientUpdates] = None):
        """Actually send queued network updates"""

        for receiving_client_uuid, updates in self.update_queue.copy().items():

            if updates == []:
                # if there are no updates to send, dont send anything
                continue
            
            updates_json = json.dumps(updates)
            
            updates_json_bytes = bytes(updates_json, "utf-8")

            if self.network_compression:
                updates_json_bytes = zlib.compress(updates_json_bytes, zlib.Z_BEST_COMPRESSION)

            self.client_sockets[receiving_client_uuid].send_headered(
                updates_json_bytes
            )
        
            self.update_queue[receiving_client_uuid] = []
            
    def run(self, max_tick_rate: int, network_tick_rate: int):
        
        self.trigger(ServerStart())
        
        last_network_tick: float = 0
        last_game_tick: float = 0

        while True:   
            
            if time.time() - last_game_tick >= 1/max_tick_rate:

                self.trigger(TickStart())

                self.trigger(Tick())

                self.trigger(TickComplete())

            if time.time() - last_network_tick >= 1/network_tick_rate:
                self.trigger(NetworkTick())

                last_network_tick = time.time()