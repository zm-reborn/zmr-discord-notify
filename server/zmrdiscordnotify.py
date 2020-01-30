
# HTTP server
from aiohttp import web
import ssl

# Discord
import discord

from os import path
from configparser import ConfigParser


def escape_everything(data):
    return discord.utils.escape_markdown(discord.utils.escape_mentions(data))

def get_valid_tokens():
    tokens = []
    with open(path.join(path.dirname(__file__), '.tokens.txt')) as fp:
        lines = fp.read().splitlines()
        for line in lines:
            if len(line) > 0:
                tokens.append(line)
    return tokens


validtokens = get_valid_tokens()

print('Valid tokens:')
for token in validtokens:
    print(token)
print()


class RequestData:
    def __init__(self, data, validtoken):
        if not data['token'] in validtokens:
            raise Exception('Invalid token.')

        self.hostname = escape_everything(data['hostname'])
        self.link = 'steam://connect/' + escape_everything(data['join_ip'])
        self.num_players = int(data['num_players'])
        self.max_players = int(data['max_players'])
        self.player_name = escape_everything(data['player_name'])

class MyDiscordClient(discord.Client):
    def __init__(self, config):
        super().__init__()

        self.my_channel = None
        self.my_guild = None
        self.my_ping_role = None

        self.token = config.get('discord', 'token')

        self.ping_role = int(config.get('discord', 'ping_role'))
        self.channel_id = int(config.get('discord', 'channel'))

        self.port = int(config.get('server', 'port'))

        self.cert_path = config.get('server', 'cert')
        self.key_path = config.get('server', 'key')

        self.webapp = web.Application()
        self.webapp.router.add_post('/', self.handle_webrequest)

        self.bg_task = self.loop.create_task(self.init_webapp())

    """Init web app"""
    async def init_webapp(self):
        try:
            print('Initializing HTTP server...')

            sslcontext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            sslcontext.load_cert_chain(self.cert_path, self.key_path)

            runner = web.AppRunner(self.webapp)
            await runner.setup()
            site = web.TCPSite(runner, port=self.port, ssl_context=sslcontext)
            print('Starting HTTP server...')
            await site.start()
            print('Done with HTTP server...')
        except Exception as e:
            print(e)


    #curl -X POST -H "Content-Type: application/json" -d @request_test1.txt localhost:3000
    """Handles the POST request from servers"""
    async def handle_webrequest(self, request):
        #print(await request.text())
        data = None
        try:
            d = await request.json()
            data = RequestData(d, self.token)
        except:
            print('Error occurred when parsing json from request!')
            print('Body:')
            print(await request.text())
        
        if data is None:
            return web.Response(text='Failed!')

        try:
            print('Sending mention!')
            await self.my_channel.send(content=self.format_content(data), embed=self.format_embed(data))
        except Exception as e:
            print(e)

        return web.Response(text='Success!')

    async def on_ready(self):
        print('Logged on as', self.user)

        self.my_channel = self.get_channel(self.channel_id)
        if self.my_channel is None:
            raise Exception('Channel with id %i does not exist!' % self.channel_id)
        
        self.my_guild = self.my_channel.guild

        self.my_ping_role = self.my_channel.guild.get_role(self.ping_role)
        if self.my_ping_role is None:
            raise Exception('Role with id %i does not exist!' % self.ping_role)

    async def on_message(self, message):
        # Not command?
        if not message.content or message.content[0] != '!':
            return
        # Don't respond to ourselves
        if message.author == self.user:
            return
        # Only either in my channel or DM
        if message.channel != self.my_channel and not isinstance(message.channel, discord.DMChannel):
            return
        # Not a member of my server
        member = self.my_guild.get_member(message.author.id)
        if member is None:
            return
        #
        # Actual actions.
        #
        if message.content[1:] == 'add':
            await self.add_ping_role(member, message.channel)

        if message.content[1:] == 'remove':
            await self.remove_ping_role(member, message.channel)



    def format_content(self, data):
        desc = '%s **%s** wants you to join! (*%i*/*%i*)' % (self.my_ping_role.mention, data.player_name, data.num_players, data.max_players)
        return desc

    def format_embed(self, data):
        name = data.hostname
        link = data.link

        embed=discord.Embed(title=name, description=link, color=0x13e82e)
        return embed

    #
    # Add ping role
    #
    async def add_ping_role(self, member, from_channel):
        if self.my_ping_role in member.roles:
            try:
                await from_channel.send("%s You already have role %s!" % (member.mention, self.my_ping_role.name))
            except Exception as e:
                print(e)
            return
        try:
            print('Adding role to user!')
            await member.add_roles(self.my_ping_role, reason='User requested.')
            await from_channel.send('%s Added role %s.' % (member.mention, self.my_ping_role.name))
        except Exception as e:
            print(e)

    #
    # Remove ping role
    #
    async def remove_ping_role(self, member, from_channel):
        if not self.my_ping_role in member.roles:
            try:
                await from_channel.send("%s You don't have role %s!" % (member.mention, self.my_ping_role.name))
            except Exception as e:
                print(e)
            return
        try:
            print('Removing role from user!')
            await member.remove_roles(self.my_ping_role, reason='User requested.')
            await from_channel.send('%s Removed role %s.' % (member.mention, self.my_ping_role.name))
        except Exception as e:
            print(e)





if __name__ == '__main__':
    # Read our config
    config = ConfigParser()
    with open(path.join(path.dirname(__file__), '.config.ini')) as fp:
        config.read_file(fp)
    client = MyDiscordClient(config)

    try:
        client.run(config.get('discord', 'token'))
    except discord.LoginFailure:
        print('Failed to log in! Make sure your token is correct!')
