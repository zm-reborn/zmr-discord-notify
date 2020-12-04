
# HTTP server
from aiohttp import web
import ssl

# Discord
import discord

# Our stuff
import asyncio
import re
import datetime
import sqlite3
from os import path
from configparser import ConfigParser


DB_NAME = 'zmrdiscordnotify.db'


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


class Event:
    def __init__(self, id, name, time, description='', warned=False):
        self.id = id
        self.name = name
        self.time = time
        self.description = description
        self.warned = warned

    @staticmethod
    def dateformat():
        return '%Y-%m-%d %H:%M'

    # HACK: We need timezone aware datetime object.
    @staticmethod
    def timezone_aware_time(time):
        delta = datetime.datetime.now() - datetime.datetime.utcnow()
        return time.replace(tzinfo=datetime.timezone(delta))

    @staticmethod
    def create_event(msg_content):
        data = re.findall('"(.+?)"', msg_content)

        if len(data) < 2:
            return None

        cur_time = datetime.datetime.utcnow()
        target_time = datetime.datetime.strptime(data[1], Event.dateformat())

        # We can't make an event in the past!
        if target_time < cur_time:
            return None

        delta = target_time - cur_time

        time = datetime.datetime.now() + delta
        time = Event.timezone_aware_time(time)

        print('Creating event %s...' % data[0])

        return Event(0, data[0], time, '' if len(data) <= 2 else data[2])

    @staticmethod
    def create_event_sql(row):
        # id, name, description, time, warned
        # print(row)

        time = datetime.datetime.strptime(row[3], Event.dateformat())
        time = Event.timezone_aware_time(time)

        return Event(row[0], row[1], time, row[2], row[4])

    def time_to_str(self):
        return self.time.strftime(Event.dateformat())

    def time_to_str_full(self):
        return self.time.strftime(Event.dateformat() + ' (%z)')

    def get_delta_to_now(self):
        return self.time.replace(tzinfo=None) - datetime.datetime.now()

    def should_warn(self):
        if self.warned:
            return False

        timedelta = self.get_delta_to_now()
        # If the days are negative, that means it's in the past.
        # And all logic goes out the window.
        if timedelta.days < 0:
            return False
        minutes = timedelta.days * 1440 + timedelta.seconds / 60
        return minutes < 30 and minutes > 2

    def should_ping(self):
        timedelta = self.get_delta_to_now()
        # If the days are negative, that means it's in the past.
        # And all logic goes out the window.
        if timedelta.days < 0:
            return True
        minutes = timedelta.days * 1440 + timedelta.seconds / 60
        return minutes < 1

    def format_time_todelta(self):
        timedelta = self.get_delta_to_now()
        days = timedelta.days
        hours = timedelta.seconds // 3600
        minutes = timedelta.seconds // 60

        s = ''
        if days > 0:
            s = '%i days ' % days
        if hours > 0:
            s += '%i hours' % hours
        elif minutes > 0:
            s += '%i minutes' % minutes
        else:
            s += '%i seconds' % timedelta.seconds

        return s

    def db_insert(self, conn):
        c = conn.cursor()
        c.execute(
            '''INSERT INTO ntf_events (name,description,time) VALUES
            (?,?,?)''',
            (self.name, self.description, self.time_to_str())
        )
        c.execute('''SELECT LAST_INSERT_ROWID()''')
        self.id = c.fetchone()[0]
        conn.commit()

    def db_markdone(self, conn):
        c = conn.cursor()
        c.execute(
            '''UPDATE ntf_events SET done=1 WHERE id=%i''' % self.id
        )
        conn.commit()

    def db_markwarned(self, conn):
        c = conn.cursor()
        c.execute(
            '''UPDATE ntf_events SET warned=1 WHERE id=%i''' % self.id
        )
        conn.commit()


class RequestData:
    def __init__(self, data, valid_tokens):
        if not data['token'] in valid_tokens:
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

        self.events = []

        self.token = config.get('discord', 'token')

        self.ping_role = int(config.get('discord', 'ping_role'))
        self.channel_id = int(config.get('discord', 'channel'))

        self.port = int(config.get('server', 'port'))

        self.cert_path = config.get('server', 'cert')
        self.key_path = config.get('server', 'key')

        self.valid_tokens = get_valid_tokens()

        print('Valid tokens:')
        for token in self.valid_tokens:
            print(token)

        self.webapp = web.Application()
        self.webapp.router.add_post('/', self.handle_webrequest)
        if config.get('server', 'test_get'):
            self.webapp.router.add_get('/', self.handle_webrequest_test_get)
            print('Added test GET handler.')

        self.loop.run_until_complete(self.init_webapp())
        self.event_task = self.loop.create_task(self.check_events())

        self.init_sqlite()

    """Init SQL connection, create tables and get events"""
    def init_sqlite(self):
        self.sqlite_connection = sqlite3.connect(
            path.join(path.dirname(__file__), DB_NAME))

        c = self.sqlite_connection.cursor()

        #
        # Init tables
        #
        c.execute(
            '''CREATE TABLE IF NOT EXISTS ntf_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(128) NOT NULL,
            description VARCHAR(256),
            time DATETIME NOT NULL,
            done INTEGET NOT NULL DEFAULT 0,
            warned INTEGER NOT NULL DEFAULT 0)''')

        # Get events
        c.execute(
            '''SELECT id,name,description,time,warned
            FROM ntf_events WHERE done=0''')

        for row in c.fetchall():
            self.events.append(Event.create_event_sql(row))

        self.sqlite_connection.commit()

    """Init web app"""
    async def init_webapp(self):
        try:
            print('Initializing HTTP server...')

            sslcontext = None
            if self.cert_path or self.key_path:
                sslcontext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                sslcontext.load_cert_chain(self.cert_path, self.key_path)
            else:
                print('NOT USING SSL')

            runner = web.AppRunner(self.webapp)
            await runner.setup()
            site = web.TCPSite(runner, port=self.port, ssl_context=sslcontext)
            await site.start()
        except Exception as e:
            print(e)
        else:
            print('Started HTTP server on port %i.' % self.port)

    """Handles the POST request from game servers."""
    async def handle_webrequest(self, request):
        data = None
        try:
            d = await request.json()
            data = RequestData(d, self.valid_tokens)
        except Exception as e:
            print('Error occurred when parsing json from request!', e)
            print('Body:')
            print(await request.text())

        if data is None:
            return web.Response(text='Failed!')

        try:
            print('Sending mention!')

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
            print(e)

        return web.Response(text='Success!')

    async def handle_webrequest_test_get(self, request):
        print('Received test GET request!')
        return web.Response(text='Hello!')

    """Task that checks for any events about to happen"""
    async def check_events(self):
        # Wait until we're ready.
        while not self.is_ready():
            await asyncio.sleep(1)

        while not self.is_closed():
            if len(self.events) > 0:
                print('Checking %i events' % len(self.events))

            for event in self.events:
                if not event.warned and event.should_warn():
                    await self.warn_event(event)
                elif event.should_ping():
                    await self.start_event(event)
                    # We will be removed from the list, so we have to break.
                    break
            await asyncio.sleep(10)

    #
    # Discord.py
    #
    async def on_ready(self):
        print('Logged on as', self.user)

        self.my_channel = self.get_channel(self.channel_id)
        if self.my_channel is None:
            raise Exception('Channel with id %i does not exist!' %
                            self.channel_id)

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
        if (message.channel != self.my_channel and
                not isinstance(message.channel, discord.DMChannel)):
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

        if message.content[1:] == 'events':
            await self.list_events(message.channel)

        if message.content.startswith('addevent', 1):
            await self.add_event(member, message)

        if message.content.startswith('removeevent', 1):
            await self.remove_event(member, message)

        if message.content.startswith('forceevent', 1):
            await self.force_event(member, message)

    #
    # Event stuff
    #
    async def start_event(self, event):
        print('Starting event #%i (%s)' % (event.id, event.name))

        desc = ('%s **%s** is starting!' %
                (self.my_ping_role.mention, event.name))
        embed = discord.Embed(
            title=event.name,
            description=event.description,
            color=0x13e82e
        )
        try:
            await self.my_channel.send(content=desc, embed=embed)
            event.db_markdone(self.sqlite_connection)
            self.events.remove(event)
        except Exception as e:
            print(e)

    async def warn_event(self, event):
        print('Warning event #%i (%s)' % (event.id, event.name))

        desc = ('%s will start in %s!' %
                (event.name, event.format_time_todelta()))

        try:
            await self.my_channel.send(desc)
            event.warned = True
            event.db_markwarned()
        except Exception as e:
            print(e)

    def init_event(self, event):
        print('Adding event %s' % event.name)

        event.db_insert(self.sqlite_connection)
        self.events.append(event)

    async def quick_channel_msg(self, msg, channel=None):
        if channel is None:
            channel = self.my_channel
        try:
            await channel.send(msg)
        except Exception as e:
            print(e)

    #
    # Command actions
    #
    #
    # Add ping role
    #
    async def add_ping_role(self, member, from_channel):
        if self.my_ping_role in member.roles:
            await self.quick_channel_msg(
                "%s You already have role %s!" %
                (member.mention,
                    self.my_ping_role.name),
                from_channel)
            return
        try:
            print('Adding ping role to user %s!' % member.nick)

            await member.add_roles(self.my_ping_role, reason='User requested.')
            await from_channel.send('%s Added role %s.' %
                                    (member.mention, self.my_ping_role.name))
        except Exception as e:
            print(e)

    #
    # Remove ping role
    #
    async def remove_ping_role(self, member, from_channel):
        if self.my_ping_role not in member.roles:
            await self.quick_channel_msg(
                "%s You don't have role %s!" %
                (member.mention,
                    self.my_ping_role.name),
                from_channel)
            return
        try:
            print('Removing role from user %s!' % member.nick)

            await member.remove_roles(
                self.my_ping_role,
                reason='User requested.')
            await from_channel.send('%s Removed role %s.' %
                                    (member.mention,
                                        self.my_ping_role.name))
        except Exception as e:
            print(e)

    #
    # List events
    #
    async def list_events(self, from_channel):
        if len(self.events) <= 0:
            await self.quick_channel_msg(
                "No events found! :(",
                from_channel)
            return

        embed = discord.Embed(
            title='Events',
            description='',
            color=0x13e82e)

        for event in self.events:
            embed.add_field(
                name='%s | %s' % (event.name, event.time_to_str_full()),
                value=event.format_time_todelta(),
                inline=False)

        try:
            await from_channel.send(
                content='%i event(s)' % len(self.events),
                embed=embed)
        except Exception as e:
            print(e)

    #
    # Add event
    #
    async def add_event(self, member, message):
        # Check if they can
        if not member.permissions_in(message.channel).manage_channels:
            return

        # Create the event
        event = Event.create_event(message.content)
        if not event:
            await self.quick_channel_msg(
                '%s Invalid syntax!' % member.mention,
                message.channel)
            return

        try:
            self.init_event(event)
            await message.channel.send(
                '%s Added event **%s** (#%i)\n%s\n**Event happens in %s**.' %
                (member.mention,
                    event.name,
                    event.id,
                    event.time_to_str_full(),
                    event.format_time_todelta())
            )
        except Exception as e:
            print(e)

    #
    # Remove event
    #
    async def remove_event(self, member, message):
        # Check if they can
        if not member.permissions_in(message.channel).manage_channels:
            return

        # Find the event they want removed.
        event = None
        id = -1
        try:
            id = int(message.content.split()[1])
        except Exception as e:
            pass
        else:
            for e in self.events:
                if e.id == id:
                    event = e
                    break

        if not event:
            await self.quick_channel_msg(
                '%s Could not find event #%i!' %
                (member.mention, id),
                message.channel)
            return

        try:
            print('Removing event %s!' % event.name)

            event.db_markdone(self.sqlite_connection)
            self.events.remove(event)

            await message.channel.send(
                '%s Removed event **%s** (%s).' %
                (member.mention,
                    event.name,
                    event.time_to_str_full()))
        except Exception as e:
            print(e)

    #
    # Force event to start
    #
    async def force_event(self, member, message):
        # Check if they can
        if not member.permissions_in(message.channel).manage_channels:
            return

        # Find the event they want.
        event = None
        id = -1
        try:
            id = int(message.content.split()[1])
        except Exception as e:
            pass
        else:
            for e in self.events:
                if e.id == id:
                    event = e
                    break

        if not event:
            await self.quick_channel_msg(
                '%s Could not find event #%i!' %
                (member.mention, id),
                message.channel)
            return

        await self.start_event(event)


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
