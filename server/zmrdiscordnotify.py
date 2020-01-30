
# HTTP server
from aiohttp import web
import ssl

# Discord
import discord

import re
import datetime
import sqlite3
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


class Event:
    def __init__(self, id, name, time, description):
        self.id = id
        self.name = name
        self.time = time
        self.description = description

    @staticmethod
    def dateformat():
        return '%Y-%m-%d %H:%M'

    def time_to_str(self):
        return self.time.strftime(Event.dateformat())

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

        event = Event(0, data[0], time, '' if len(data) <= 2 else data[2])

    @staticmethod
    def create_event_sql(row):
        # id, name, description, time
        return Event(row[0], row[1], row[3], row[2])

    def format_time_todelta(self):
        timedelta = self.time - datetime.datetime.now()
        days = timedelta.days
        hours = timedelta.seconds // 3600
        
        s = ''
        
        if days > 0:
            s = '%i days ' % days
        if hours > 0:
            s += '%i hours' % hours

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

    def db_remove(self, conn):
        c = conn.cursor()
        c.execute(
            '''DELETE FROM ntf_events WHERE id=?''',
            (self.id)
        )
        conn.commit()

    async def create_msg(self, member, message):
        await message.channel.send(
            '%s Added event %s. (%s) Happens in %s' %
            (member.mention,
                self.name,
                self.description,
                self.format_time_todelta())
        )

    async def remove_msg(self, member, message):
        await message.channel.send(
            '%s Removed event %s.' %
            (member.mention, self.name))

    async def start_msg(self, channel, ping_role):
        desc = '%s %s is starting!' % (ping_role.mention, self.name)
        embed = discord.Embed(
            title=self.name,
            description=self.description,
            color=0x13e82e
        )
        await channel.send(content=desc, embed=embed)


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

        self.events = []

        self.token = config.get('discord', 'token')

        self.ping_role = int(config.get('discord', 'ping_role'))
        self.channel_id = int(config.get('discord', 'channel'))

        self.port = int(config.get('server', 'port'))

        self.cert_path = config.get('server', 'cert')
        self.key_path = config.get('server', 'key')

        self.webapp = web.Application()
        self.webapp.router.add_post('/', self.handle_webrequest)

        self.bg_task = self.loop.create_task(self.init_webapp())

        self.init_sqlite()

    def init_sqlite(self):
        self.sqlite_connection = sqlite3.connect('zmrdiscordnotify.db')
        
        c = self.sqlite_connection.cursor()
        c.execute(
            '''CREATE TABLE IF NOT EXISTS ntf_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(128) NOT NULL,
            description VARCHAR(256),
            time DATETIME NOT NULL)''')
        c.execute(
            '''SELECT id,name,description,time FROM ntf_events WHERE time >= CURRENT_TIMESTAMP''')

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

            runner = web.AppRunner(self.webapp)
            await runner.setup()
            site = web.TCPSite(runner, port=self.port, ssl_context=sslcontext)
            print('Starting HTTP server...')
            await site.start()
        except Exception as e:
            print(e)
        else:
            print('Done with HTTP server...')

    """Handles the POST request from servers"""
    async def handle_webrequest(self, request):
        data = None
        try:
            d = await request.json()
            data = RequestData(d, self.token)
        except Exception as e:
            print('Error occurred when parsing json from request!', e)
            print('Body:')
            print(await request.text())
        
        if data is None:
            return web.Response(text='Failed!')

        try:
            print('Sending mention!')
            await self.my_channel.send(
                content=self.format_content(data),
                embed=self.format_embed(data)
            )
        except Exception as e:
            print(e)

        return web.Response(text='Success!')

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
        if message.channel != self.my_channel
        and not isinstance(message.channel, discord.DMChannel):
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
            
        if message.content.startswith('addevent', 1):
            await self.add_event(member, message)
            
        if message.content.startswith('removeevent', 1):
            await self.remove_event(member, message)

        if message.content.startswith('forceevent', 1):
            await self.force_event(member, message)

    def format_content(self, data):
        desc = '%s **%s** wants you to join! (*%i*/*%i*)' %
        (self.my_ping_role.mention,
            data.player_name,
            data.num_players,
            data.max_players)
        return desc

    def format_embed(self, data):
        name = data.hostname
        link = data.link

        embed = discord.Embed(title=name, description=link, color=0x13e82e)
        return embed

    #
    # Add ping role
    #
    async def add_ping_role(self, member, from_channel):
        if self.my_ping_role in member.roles:
            try:
                await from_channel.send("%s You already have role %s!" %
                                        (member.mention,
                                            self.my_ping_role.name))
            except Exception as e:
                print(e)
            return
        try:
            print('Adding role to user!')
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
            try:
                await from_channel.send("%s You don't have role %s!" %
                                        (member.mention,
                                            self.my_ping_role.name))
            except Exception as e:
                print(e)
            return
        try:
            print('Removing role from user!')
            await member.remove_roles(
                self.my_ping_role,
                reason='User requested.')
            await from_channel.send('%s Removed role %s.' %
                                    (member.mention,
                                        self.my_ping_role.name))
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
            await message.channel.send('%s Invalid syntax!' % member.mention)
            return

        event.db_insert(self.sqlite_connection)
        self.events.append(event)

        await event.create_msg(member, message)

    #
    # Remove event
    #
    async def remove_event(self, member, message):
        # Check if they can
        if not member.permissions_in(message.channel).manage_channels:
            return

        # Find the event they want removed.
        id = int(message.content.split()[1])
        event = None
        for e in self.events:
            if e.id == id:
                event = e
                break

        if not event:
            await message.channel.send('%s Could not find event #%i!' %
                                       (member.mention, id))
            return

        event.db_remove(self.sqlite_connection)
        self.events.remove(event)

        await event.remove_msg(member, message)

    #
    # Force event to start
    #
    async def force_event(self, member, message):
        if len(self.events) <= 0:
            await message.channel.send('%s no events found!' % member.mention)

        event = self.events[0]

        await event.start_msg(self.my_channel, self.my_ping_role)

        self.events.remove(event)

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
