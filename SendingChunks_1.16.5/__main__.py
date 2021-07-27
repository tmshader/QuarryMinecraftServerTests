import math, os, sys, argparse

from twisted.internet import reactor
from quarry.net.server import ServerFactory, ServerProtocol
from quarry.data.data_packs import data_packs, dimension_types
from quarry.types.nbt import RegionFile, TagCompound, TagLongArray, TagRoot
from quarry.types.chunk import BlockArray, PackedArray
from quarry.types.registry import LookupRegistry

reactor.suggestThreadPoolSize(50)

sent_chunks = False
counter = 0

loaded_regions = {}
loaded_chunks = {}

queue = []

def load_chunks():
    print("Loading spawn chunks, please wait...")

    for x in range(-10, 11):
        for z in range(-10, 11):
            x2 = x * 16
            z2 = z * 16

            rx, x2 = divmod(x2, 512)
            rz, z2 = divmod(z2, 512)
            cx, x2 = divmod(x2, 16)
            cz, z2 = divmod(z2, 16)

            if (str(rx) + ";" + str(rz)) in loaded_regions:
                region = loaded_regions[str(rx) + ";" + str(rz)]
            else:
                region = RegionFile(os.path.join("SendingChunks_1.16.5", "assets", "world", "region", "r.%d.%d.mca" % (rx, rz)))
                loaded_regions[str(rx) + ";" + str(rz)] = region

            try:
                if not (str(cx) + ";" + str(cz)) in loaded_chunks:
                    loaded_chunks[str(rx) + ";" + str(rz) + "#" + str(cx) + ";" + str(cz)] = region.load_chunk(cx, cz)
            except ValueError as e:
                continue
            except OSError as e:
                continue

    print("Spawn chunks succesfully loaded!")


class ChunkSendingProtocol(ServerProtocol):
    global registry, emptyHeight, loaded_regions, sent_chunks, counter

    emptyHeight = TagRoot({"": TagCompound({
        "MOTION_BLOCKING": TagLongArray(PackedArray.empty_height())
    })})

    registry = LookupRegistry.from_jar(os.path.join("SendingChunks_1.16.5", "assets", "registry", "server.jar"))

    class chunk:
        x = 0
        z = 0

    class player:
        x = 0
        z = 0

    def player_joined(self):
        ServerProtocol.player_joined(self)

        self.send_packet("join_game",
            self.buff_type.pack("i?BB",
                0, False, 1, 1),
            self.buff_type.pack_varint(1),
            self.buff_type.pack_string("chunks"),
            self.buff_type.pack_nbt(data_packs[self.protocol_version]),
            self.buff_type.pack_nbt(dimension_types[self.protocol_version, "minecraft:overworld"]),
            self.buff_type.pack_string("chunks"),
            self.buff_type.pack("q", 42),
            self.buff_type.pack_varint(0),
            self.buff_type.pack_varint(2),
            self.buff_type.pack("????", False, True, False, False))

        self.send_packet("player_position_and_look",
            self.buff_type.pack("dddff?",
                8, 200, 8, 0, 90, 0b00000),
            self.buff_type.pack_varint(0))
        
        self.ticker.add_loop(20, self.update_keep_alive)
        self.ticker.add_loop(1, self.send_next_from_queue)

    def send_perimiter(self, size, thread=True):
        for x in range(-size, size + 1):
            for z in range(-size, size + 1):
                if x == -size or x == size or z == -size or z == size:
                    if thread:
                        reactor.callInThread(self.read_and_send_chunk, x * 16, z * 16)
                    else:
                        self.read_and_send_chunk(x * 16, z * 16)
                
    def send_empty_perimiter(self, size):
        for x in range(-size, size + 1):
            for z in range(-size, size + 1):
                if x == -size or x == size or z == -size or z == size:
                    queue.append([x, z, True, emptyHeight, [None]*16, [1]*256, []])

    def send_empty_full(self, size):
        for x in range(-size, size + 1):
            for z in range(-size, size + 1):
                if x == 0 and z == 0: continue
                queue.append([x, z, True, emptyHeight, [None]*16, [1]*256, []])

    def player_left(self):
        ServerProtocol.player_left(self)

    def update_keep_alive(self):
        global sent_chunks, counter

        self.send_packet("keep_alive", self.buff_type.pack("Q", 0))

        if not sent_chunks:
            if counter == 0:
                self.send_empty_full(4)
            if counter == 10:
                self.send_perimiter(2)
            if counter == 20:
                self.send_perimiter(0)
            
            counter += 1

    def send_next_from_queue(self):
        if len(queue) == 0: return

        x, z, full, heightmap, sections, biomes, block_entities = queue.pop();
        self.send_chunk(x, z, full, heightmap, sections, biomes, block_entities)

    def send_chunk(self, x, z, full, heightmap, sections, biomes, block_entities):
        sections_data = self.buff_type.pack_chunk(sections)

        biomes = [1] * 256
        for i in range(0, len(block_entities)):
            block_entities[i] = TagRoot({"": block_entities[i]})

        self.send_packet('chunk_data',
            self.buff_type.pack('ii?', x, z, full),
            self.buff_type.pack_chunk_bitmask(sections),
            self.buff_type.pack_nbt(heightmap),
            self.buff_type.pack_optional_varint(1023),
            self.buff_type.pack_array("I", biomes),
            self.buff_type.pack_varint(len(sections_data)),
            sections_data,
            self.buff_type.pack_varint(len(block_entities)),
            b"".join(self.buff_type.pack_nbt(entity) for entity in block_entities))

    def read_and_send_chunk(self, x, z):
        px = math.floor(x / 16)
        pz = math.floor(z / 16)

        rx, x = divmod(x, 512)
        rz, z = divmod(z, 512)
        cx, x = divmod(x, 16)
        cz, z = divmod(z, 16)

        if (str(rx) + ";" + str(rz)) in loaded_regions:
            region = loaded_regions[str(rx) + ";" + str(rz)]
        else:
            region = RegionFile(os.path.join("SendingChunks_1.16.5", "assets", "world", "region", "r.%d.%d.mca" % (rx, rz)))
            loaded_regions[str(rx) + ";" + str(rz)] = region

        try:
            if (str(rx) + ";" + str(rz) + "#" + str(cx) + ";" + str(cz)) in loaded_chunks:
                chunk = loaded_chunks[str(rx) + ";" + str(rz) + "#" + str(cx) + ";" + str(cz)].body.value["Level"].value
            else:
                chunk = region.load_chunk(cx, cz).body.value["Level"].value
        except ValueError as e:
            return
        except OSError as e:
            return

        sections = [None] * 16

        for section in chunk["Sections"].value:
            if 'Palette' in section.value:
                y = section.value["Y"].value
                if 0 <= y < 16:
                    blocks = BlockArray.from_nbt(section, registry)
                    block_light = None
                    sky_light = None
                    sections[y] = (blocks, block_light, sky_light)

        heightmap = TagRoot.from_body(chunk["Heightmaps"])
        biomes = chunk["Biomes"].value
        block_entities = chunk["TileEntities"].value
        biomes = [biome for biome in biomes]

        queue.append([px, pz, True, heightmap, sections, biomes, block_entities])

    def update_chunks(self):
        if math.floor(self.player.x / 16) == self.chunk.x and math.floor(self.player.z / 16) == self.chunk.z:
            return

        self.read_and_send_chunk(math.floor(self.player.x / 16), math.floor(self.player.z / 16))

        self.chunk.x = math.floor(self.player.x / 16)
        self.chunk.z = math.floor(self.player.z / 16)

    def packet_player_position_and_look(self, buff):
        x, y, z, ry, rp, flag = buff.unpack('dddff?')

        self.player.x = x
        self.player.z = z


class ChunkSendingFactory(ServerFactory):
    protocol = ChunkSendingProtocol
    motd = "Chunk Sending Server"


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--host", default="0.0.0.0", help="Address to listen on")
    parser.add_argument("-p", "--port", default=25565, type=int, help="Port to listen on")
    parser.add_argument("--offline", action="store_true", help="Offline server")
    args = parser.parse_args(argv)

    factory = ChunkSendingFactory()
    factory.online_mode = not args.offline
    factory.listen(args.host, args.port)
    print("Server running on %d:%d" % (args.host, args.port))
    reactor.run()


if __name__ == "__main__":
    load_chunks()
    main(sys.argv[1:])