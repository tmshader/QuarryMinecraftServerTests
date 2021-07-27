# Sending chunks to 1.16.5 clients

Limitations and current problems:
- Can't send entities (It can send tile entities, like chests)
- Lava has the texture of water
- Chunks take 1-2 seconds to send
- Biomes cannot be sent

## How to run:

From the top directory (not from inside `SendingChunks_1.16.5`) run
```
py SendingChunks_1.16.5
```
The project was tested with `Python 3.9.5` and `Minecraft 1.16.5`