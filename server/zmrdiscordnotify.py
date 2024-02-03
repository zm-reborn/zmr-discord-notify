
# HTTP server
from aiohttp import web
import ssl

# Discord
import discord

# Our stuff
import logging
import sys
from os import path
from configparser import ConfigParser


LOG_FORMAT = '%(asctime)s | %(message)s'


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def escape_everything(data: str):
    return discord.utils.escape_markdown(discord.utils.escape_mentions(data))


def get_valid_tokens():
    tokens: list[str] = []
    with open(path.join(path.dirname(__file__), '.tokens.txt')) as fp:
        lines = fp.read().splitlines()
        for line in lines:
            if len(line) == 0:
                continue
            # Check for comments
            try:
                comment_index = line.index(';')
                if comment_index == 0:
                    continue
                line = line[:comment_index]
            except ValueError:
                pass
            tokens.append(line.strip())

    return tokens


class RequestData:
    def __init__(self, data, valid_tokens: list[str]):
        if 'token' not in data:
            raise Exception('No token in JSON object!')

        if not data['token'] in valid_tokens:
            raise Exception('Invalid token.')

        self.hostname = escape_everything(data['hostname'])
        self.link = 'steam://connect/' + escape_everything(data['join_ip'])
        self.num_players = int(data['num_players'])
        self.max_players = int(data['max_players'])
        self.player_name = escape_everything(data['player_name'])


class MyDiscordClient(discord.Client):
    def __init__(self, config: ConfigParser):
        intents = discord.Intents.default()
        intents.members = True # We need members so we can add roles.
        intents.message_content = True # Read messages.
        super().__init__(intents=intents)

        self.init_done = False
        self.exitcode = 0

        self.my_channel: discord.TextChannel | None = None
        self.my_guild: discord.Guild | None = None
        self.my_ping_role: discord.Role | None = None

        self.token = config.get('discord', 'token')

        self.ping_role = int(config.get('discord', 'ping_role'))
        self.channel_id = int(config.get('discord', 'channel'))

        self.port = int(config.get('server', 'port'))

        self.cert_path = config.get('server', 'cert')
        self.key_path = config.get('server', 'key')

        self.test_post = False
        if config.get('server', 'test_post'):
            self.test_post = True
            logger.info(
                'Testing POST requests. Notifications are not sent to Discord!'
            )

        self.valid_tokens = get_valid_tokens()

        logger.info('Loaded %i valid tokens.' % len(self.valid_tokens))
        for token in self.valid_tokens:
            logger.debug('"' + token + '"')

        self.webapp = web.Application()
        self.webapp.router.add_post('/', self.handle_webrequest)
        if config.get('server', 'test_get'):
            self.webapp.router.add_get('/', self.handle_webrequest_test_get)
            logger.info('Added test GET handler.')

    async def setup_hook(self):
        await self.init_webapp()

    async def on_ready(self):
        logger.info('Logged on as %s' % self.user)

        chnl = self.get_channel(self.channel_id)
        if chnl is None:
            logger.error(f'Channel with id {self.channel_id} does not exist!')
            self.exitcode = 1
            await self.close()
            return
        if not isinstance(chnl, discord.TextChannel):
            logger.error(f'Channel {self.channel_id} must be a text channel!')
            self.exitcode = 1
            await self.close()
            return

        self.my_channel = chnl
        self.my_guild = self.my_channel.guild
        self.my_ping_role = self.my_channel.guild.get_role(self.ping_role)
        if self.my_ping_role is None:
            logger.error(f'Role with id {self.ping_role} does not exist!')
            self.exitcode = 1
            await self.close()
            return

        self.init_done = True

    async def on_message(self, message: discord.Message):
        if not self.is_ready() or not self.init_done:
            logger.debug('Received message but bot is not ready yet.')
            return
        # Not command?
        if not message.content or message.content[0] != '!':
            return
        # Don't respond to ourselves
        if message.author == self.user:
            return
        # Only either in my channel or DM
        if (message.channel != self.my_channel and
                not isinstance(message.channel, discord.DMChannel)):
            return
        # Not a member of my server
        assert self.my_guild
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

    """Init web app"""
    async def init_webapp(self):
        try:
            logger.info('Initializing HTTP server...')

            sslcontext = None
            if self.cert_path or self.key_path:
                sslcontext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                sslcontext.load_cert_chain(self.cert_path, self.key_path)
            else:
                logger.info('NOT USING SSL')

            runner = web.AppRunner(self.webapp)
            await runner.setup()
            site = web.TCPSite(runner, port=self.port, ssl_context=sslcontext)
            await site.start()
        except Exception as e:
            logger.error('Error initializing web server: ' + str(e))
        else:
            logger.info('Started HTTP server on port %i.' % self.port)

    """Handles the POST request from game servers."""
    async def handle_webrequest(self, request: web.Request):
        if not self.is_ready() or not self.init_done:
            logger.error(
                'Received a POST request while Discord bot is not ready!')
            return web.Response(status=503)

        data = None
        try:
            d = await request.json()
            logger.debug('Received valid JSON:')
            logger.debug(str(d))
            data = RequestData(d, self.valid_tokens)
        except Exception as e:
            logger.error(
                'Error occurred when parsing json from request: ' + str(e))
            try:
                body = await request.text()
                logger.error('Body: ' + str(body))
            except Exception:
                pass

        if data is None:
            return web.Response(text='Failed!', status=400)

        if self.test_post:
            logger.info('Testing POST. Not sending a mention.')
            return web.Response(text='Success!')

        assert self.my_ping_role and self.my_channel
        try:
            logger.info('Sending mention.')

            embed = discord.Embed(
                title=data.hostname,
                description=data.link,
                color=0x13e82e)
            content = ('%s **%s** wants you to join! (*%i*/*%i*)' %
                       (self.my_ping_role.mention,
                        data.player_name,
                        data.num_players,
                        data.max_players))
            await self.my_channel.send(content=content, embed=embed)
        except Exception as e:
            logger.error('Error sending a mention: ' + str(e))

        return web.Response(text='Success!')

    async def handle_webrequest_test_get(self, request: web.Request):
        logger.info('Received test GET request!')
        return web.Response(text='Hello!')

    async def add_ping_role(self, member: discord.Member, from_channel: discord.abc.Messageable):
        assert self.my_ping_role
        if self.my_ping_role in member.roles:
            await self.quick_channel_msg(
                "%s You already have role %s!" %
                (member.mention,
                    self.my_ping_role.name),
                from_channel)
            return
        try:
            logger.info('Adding ping role to user %s!' % member.display_name)

            await member.add_roles(self.my_ping_role, reason='User requested.')
            await from_channel.send('%s Added role %s.' %
                                    (member.mention, self.my_ping_role.name))
        except Exception as e:
            logger.error('Error adding a ping role: ' + str(e))

    async def remove_ping_role(self, member: discord.Member, from_channel: discord.abc.Messageable):
        assert self.my_ping_role
        if self.my_ping_role not in member.roles:
            await self.quick_channel_msg(
                "%s You don't have role %s!" %
                (member.mention,
                    self.my_ping_role.name),
                from_channel)
            return
        try:
            logger.info('Removing role from user %s!' % member.display_name)

            await member.remove_roles(
                self.my_ping_role,
                reason='User requested.')
            await from_channel.send('%s Removed role %s.' %
                                    (member.mention,
                                        self.my_ping_role.name))
        except Exception as e:
            logger.error('Error removing a ping role: ' + str(e))

    async def quick_channel_msg(self, msg: str, channel: discord.abc.Messageable | None = None):
        if channel is None:
            channel = self.my_channel
        assert channel
        try:
            await channel.send(msg)
        except Exception as e:
            logger.error('Error sending a channel message: ' + str(e))


if __name__ == '__main__':
    # Read our config
    config = ConfigParser()
    with open(path.join(path.dirname(__file__), '.config.ini')) as fp:
        config.read_file(fp)

    # Init logger
    log_level_str = config.get(
        'server', 'logging', fallback='').upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(log_level)
    formatter = logging.Formatter(LOG_FORMAT)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    client = MyDiscordClient(config)

    try:
        client.run(config.get('discord', 'token'))
    except discord.LoginFailure:
        logger.error('Failed to log in! Make sure your token is correct!')
        client.exitcode = 2
    except Exception as e:
        logger.error('Discord bot ended unexpectedly: ' + str(e))
        client.exitcode = 1

    if client.exitcode > 0:
        sys.exit(client.exitcode)
