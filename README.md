#### SourceMod Client Installation:

- Download [latest client](https://github.com/zm-reborn/zmr-discord-notify/releases).
- Install [SteamWorks](http://users.alliedmods.net/~kyles/builds/SteamWorks/) extension.
- Ask a token from Mehis. Put it in ```token```-key in `addons/sourcemod/configs/zmrdiscordnotify.cfg`

#### Python Server Installation (Docker):

```bash
cd ./server

cp .config.ini.template .config.ini

# Configure .config.ini file with bot token, etc.

cp docker-compose.template.yml docker-compose.yml

# Configure docker-compose.yml with cert paths.

# Build & run image
docker compose up
```
