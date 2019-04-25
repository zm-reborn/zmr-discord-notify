#### Installation:

- Compile the plugin!
- Install [SteamWorks](http://users.alliedmods.net/~kyles/builds/SteamWorks/) extension.
- Install [Discord API](https://forums.alliedmods.net/showthread.php?t=292663). (Only needs `discord.smx` and `configs/discord.cfg`)
- Add the webhook URL to `discord.cfg`:
  ```
  "Discord"
  {
  	  ...
      
      "zmrdiscordnotify"
      {
          "url"	"WEBHOOKS_URL_GOES_HERE"
      }
  }
  ```
