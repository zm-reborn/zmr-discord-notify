#### SourceMod Client Installation:

- Compile the plugin!
- Install [SteamWorks](http://users.alliedmods.net/~kyles/builds/SteamWorks/) extension.
- Ask a token from Mehis. Put it in ```token```-key in `addons/sourcemod/configs/zmrdiscordnotify.cfg`

#### Python Server Installation:

- Install Python 3 and make sure it's in your PATH.
- Run `pip install -r server/requirements.txt`
- Configure ```.config.ini``` (create a copy of  ```.config.template.ini```)
    - You'll need an SSL cert, bot token and channel+role ids.
- Insert some tokens in ```.tokens.txt``` (create a copy of  ```.tokens.template.txt```)
- Run the ```zmrdiscordnotify.py``` script.
