import re
import os
import pickle
import asyncio
import logging
import requests
import argparse

from uuid import uuid4
from datetime import datetime
from discord.ext import commands
from logging.handlers import RotatingFileHandler
from passwords import DISCORD_BOT_TOKEN, TWITCH_CLIENT_ID


logger = logging.getLogger(__name__)
client = commands.Bot(command_prefix='!', description='Setup Access Control to Voice Channels '
                                                      'based off currently played game.')


def parse_args():
    parser = argparse.ArgumentParser('Discord Voice Channel Manager',
                                     description='Bot that validates playing game with a voice channel. '
                                                 'This aids admins in keeping voice channels intended '
                                                 'to be used for game play of specific game(s), clear '
                                                 'of loiters.')
    parser.add_argument('-s', '--settings', help='Path to stored bot_settings.pickle', default=None)
    parser.add_argument('-l', '--log-file', help='File path to write log file',
                        default=os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                             'discord_voice_chat_manager.log'))
    parser.add_argument('-L', '--log-level', help='Log Level. Valid Options: DEBUG, INFO',
                        default='INFO')
    return parser.parse_args()


class BotSettings(object):
    _settings = None
    claim_code = None

    def __init__(self, file_path=None):
        if file_path is None:
            file_path = 'bot_settings.pickle'
            self.path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                     file_path)
        self.file_path = file_path

    @property
    def default_settings(self):
        return {
            'enabled': False,
            'kick_mode': True,
            'bot_admin_role_id': '',
            'general_voice_channel_id': '',
            'bot_text_channel_id': '',
            'game_close_disconnect_timeout': 30,
            'whitelisted_role_ids': [],
            'whitelisted_user_ids': [],
            'restricted_voice_channels': {}
        }

    @property
    def settings(self):
        if self._settings is None:
            self.load()
        return self._settings

    @property
    def enabled(self):
        return self.settings['enabled']

    @property
    def kick_mode(self):
        return self.settings['kick_mode']

    @property
    def bot_admin_role_id(self):
        return self.settings['bot_admin_role_id']

    @property
    def general_voice_channel_id(self):
        return self.settings['general_voice_channel_id']

    @property
    def bot_text_channel_id(self):
        return self.settings['bot_text_channel_id']

    @property
    def game_close_disconnect_timeout(self):
        return self.settings['game_close_disconnect_timeout']

    @property
    def whitelisted_role_ids(self):
        return self.settings['whitelisted_role_ids']

    @property
    def whitelisted_user_ids(self):
        return self.settings['whitelisted_user_ids']

    @property
    def restricted_voice_channels(self):
        return self.settings['restricted_voice_channels']

    @property
    def claimed(self):
        return bool(self.bot_admin_role_id)

    def claim(self, claim_code, role_id):
        if self.claimed:
            logger.info('Already Claimed')
            return False
        if claim_code != self.claim_code:
            logger.info(f'Claim Code Mismatch: {self.claimed} != {claim_code}')
            return False
        self._settings['bot_admin_role_id'] = role_id
        self.save()
        return True

    def authorize_command(self, author):
        if not self.claimed:
            return False
        return any(role.id == self.bot_admin_role_id for role in author.roles)

    def load(self):
        if not os.path.exists(self.file_path):
            self._settings = self.default_settings
            return
        with open(self.file_path, 'rb') as settings_file:
            self._settings = pickle.load(settings_file)
        for k, v in self.default_settings.items():
            if k not in self._settings:
                self._settings[k] = v

    def save(self):
        with open(self.file_path, 'wb') as settings_file:
            self._settings = pickle.dump(self._settings, settings_file)

    def set_setting(self, setting, value):
        if setting not in self._settings:
            return False
        self.load()
        self._settings[setting] = value
        self.save()
        return True

    def set_enabled(self, enabled=True):
        self.load()
        self._settings['enabled'] = enabled
        self.save()
        return self.enabled

    def set_kick_mode(self, kick=True):
        self.load()
        self._settings['kick_mode'] = kick
        self.save()
        return self.kick_mode

    def set_general_voice_channel_id(self, channel_id):
        self.load()
        self._settings['general_voice_channel_id'] = channel_id
        self.save()
        return True

    def set_bot_text_channel_id(self, channel_id):
        self.load()
        self._settings['bot_text_channel_id'] = channel_id
        self.save()
        return True

    def set_game_close_disconnect_timeout(self, timeout: int):
        if timeout < 0:
            return False
        self.load()
        self._settings['game_close_disconnect_timeout'] = timeout
        self.save()
        return True

    def whitelist_user(self, user_id, remove=False):
        if not remove and user_id not in self.whitelisted_user_ids:
            self._settings['whitelisted_user_ids'].append(user_id)
            self.save()
            return True
        if remove and user_id in self.whitelisted_user_ids:
            self._settings['whitelisted_user_ids'].remove(user_id)
            self.save()
            return True
        return False

    def whitelist_role(self, role_id, remove=False):
        if not remove and role_id not in self.whitelisted_role_ids:
            self._settings['whitelisted_role_ids'].append(role_id)
            self.save()
            return True
        if remove and role_id in self.whitelisted_role_ids:
            self._settings['whitelisted_role_ids'].remove(role_id)
            self.save()
            return True
        return False

    def restrict_channel(self, channel_id, games):
        self.load()
        self._settings['restricted_voice_channels'][channel_id] = games
        self.save()
        return True

    def release_channel(self, channel_id):
        if channel_id not in self.restricted_voice_channels:
            return False
        del self._settings['restricted_voice_channels'][channel_id]
        self.save()
        return True


class Twitch(object):
    _last_api_call = None

    def validate_twitch_game(self, twitch_username, voice_channel_id):
        if self._last_api_call is None:
            self._last_api_call = datetime.utcnow()
        elif (datetime.utcnow() - self._last_api_call).seconds > 5:
            self._last_api_call = datetime.utcnow()
        else:
            logger.warning(f'UNABLE TO HIT TWITCH API. INTERNAL RATE LIMIT REACHED! {twitch_username}')
            return False
        headers = {
            'Client-ID': TWITCH_CLIENT_ID,
            'Accept': 'application/vnd.twitchtv.v5+json'
        }
        logger.debug(f'Twitch Name: {twitch_username}')
        url = 'https://api.twitch.tv/kraken/users?login=' + twitch_username
        resp = requests.get(url, headers=headers)
        data = resp.json()
        logger.debug(f'Twitch Get User JSON: {data}')
        url = 'https://api.twitch.tv/kraken/channels/' + data['users'][0]['_id']
        resp = requests.get(url, headers=headers)
        data = resp.json()
        logger.debug(f'Twitch Get Channel JSON: {data}')
        if data['game'] in settings.restricted_voice_channels[voice_channel_id]:
            logger.debug(f'Twitch User ({twitch_username}) validated '
                         f'voice channel ({voice_channel_id}) with {data["game"]}.')
            return True
        logger.debug(f'Twitch User ({twitch_username}) unable to validate '
                     f'voice channel ({voice_channel_id}) with {data["game"]}.')
        return False


twitch = Twitch()
settings = BotSettings()


async def can_join_restricted_voice_channel(member):
    if not settings.enabled:
        logger.debug('Bot is disabled. Ignoring.')
        return
    username = member.nick if member.nick is not None else member.name
    if member.id in settings.whitelisted_user_ids:
        logger.debug(f'{username}({member.id}) is a WHITELISTED USER. Ignoring.')
        if not settings.kick_mode and member.voice.mute:
            await client.server_voice_state(member, mute=False)
        return
    for role in member.roles:
        if role.id in settings.whitelisted_role_ids:
            logger.debug(f'{username}({member.id}) is WHITELISTED via {role.name}({role.id}). Ignoring.')
            if not settings.kick_mode and member.voice.mute:
                await client.server_voice_state(member, mute=False)
            return
    if member.voice is not None and member.voice.voice_channel is not None\
            and member.voice.voice_channel.id in settings.restricted_voice_channels and\
            (member.game is None or
             member.game.name not in settings.restricted_voice_channels[member.voice.voice_channel.id]):
        if member.game is not None and member.game.type == 1 and member.game.url.startswith('https://www.twitch.tv/'):
            logger.debug(f'{username}({member.id}) is streaming. Validating via Twitch...')
            twitch_username = member.game.url.replace('https://www.twitch.tv/', '')
            if twitch.validate_twitch_game(twitch_username, member.voice.voice_channel.id):
                logger.debug(f'{username}({member.id}) validated via Twitch! Ignoring.')
                return
        game_channel_name = member.voice.voice_channel.name
        general_channel = client.get_channel(settings.general_voice_channel_id)
        games = ",".join(settings.restricted_voice_channels[member.voice.voice_channel.id])
        logger.info(f'{username}({member.id}) has failed the check for '
                    f'{member.voice.voice_channel.name}({member.voice.voice_channel.id}). '
                    f'Acceptable Games: {games}')
        if settings.kick_mode:
            logger.info(f'Moving {username}({member.id}) '
                        f'{member.voice.voice_channel.name}({member.voice.voice_channel.id}) -> '
                        f'{general_channel.name}({general_channel.id})')
            await client.move_member(member, general_channel)
            if settings.bot_text_channel_id:
                await client.send_message(client.get_channel(settings.bot_text_channel_id),
                                          f'{member.mention} You must be playing the following to join '
                                          f'{game_channel_name}: {games}. If you are streaming, '
                                          f'I am only friends with Twitch for right now and am unable '
                                          f'to determine what game you are currently playing outside of '
                                          f'my friends list. :( ')
            return
        else:
            logger.info(f'Muting {username}({member.id}) '
                        f'{member.voice.voice_channel.name}({member.voice.voice_channel.id})')
            if member.voice.mute:
                logger.info(f'{username}({member.id}) is already server muted. Ignoring.')
                return
            await client.server_voice_state(member, mute=True)
            logger.info(f'Muted {username}({member.id}) in {game_channel_name}.')
            if settings.bot_text_channel_id:
                await client.send_message(client.get_channel(settings.bot_text_channel_id),
                                          f'{member.mention} You must be playing the following to not be '
                                          f'muted in {game_channel_name}: {games}. If you are streaming, '
                                          f'I am only friends with Twitch for right now and am unable '
                                          f'to determine what game you are currently playing outside of '
                                          f'my friends list. :( ')
            return
    else:
        if not settings.kick_mode and member.voice.mute:
            await client.server_voice_state(member, mute=False)


@client.event
async def on_voice_state_update(_, after):
    await can_join_restricted_voice_channel(after)


@client.event
async def on_member_update(before, after):
    if before.voice is not None and after.voice is not None \
        and before.voice.voice_channel is not None and after.voice.voice_channel is not None \
            and after.voice.voice_channel.id in settings.restricted_voice_channels \
            and before.game is not None \
            and before.game.name in settings.restricted_voice_channels[before.voice.voice_channel.id] \
            and after.game is None and before.voice.voice_channel.id == after.voice_channel.id:
        username = before.nick if before.nick is not None else before.name
        logger.debug(f'{username}({before.id}) appears to have quit game. '
                     f'Sleeping for {settings.game_close_disconnect_timeout}s before validating...')
        await asyncio.sleep(settings.game_close_disconnect_timeout)
        after = list(client.servers)[0].get_member(after.id)
    await can_join_restricted_voice_channel(after)


@client.group(pass_context=True)
async def voice_bot(ctx):
    if ctx.invoked_subcommand is None:
        if not settings.authorize_command(ctx.message.author):
            return
        message = ctx.message.content.replace('!voice_bot ', '')
        if message.lower() == 'enable':
            if settings.general_voice_channel_id and settings.set_enabled():
                await client.say('Restrictions Enabled!')
            else:
                await client.say('general_voice_channel_id not set or an error occurred!')
        elif message.lower() == 'disable':
            if settings.set_enabled(enabled=False):
                await client.say('Restrictions Disabled!')
            else:
                await client.say('Something went wrong!')
        elif message.lower() == 'help':
            await client.say('This bot provides admins the ability to restrict '
                             'voice channels to users playing a specific game(s). '
                             'You may whitelist users and roles from these restrictions. '
                             'If voice channel kick mode is disabled, then users will be '
                             'muted instead.\n\n**Available Commands**\n'
                             '```'
                             '!voice_bot enable|disable                                             Enables or '
                             'Disables the bot.\n'
                             '!voice_bot set general_voice_channel_id <channel_id>                  Sets the '
                             'voice channel to move users into that fail to meet the restrictions.\n'
                             '!voice_bot set bot_text_channel_id <channel_id>                       Sets the '
                             'channel for the bot to notify users they have failed the restriction checks.\n'
                             '!voice_bot kick enable|disable                                        Enables or '
                             'Disables the Voice Channel Kick Mode.\n'
                             '!voice_bot whitelist add|remove @user @role                           Add or Remove '
                             'user(s) or role(s) to the Whitelist.\n'
                             '!voice_bot restrict <voice_channel_id> <game> <"game with spaces">    Restrict a '
                             'voice channel to the specified games. Additionally specify Twitch Game Name if '
                             'different than Discord.\n'
                             '!voice_bot release <voice_channel_id>                                 Releases a '
                             'voice channel from all restrictions.\n'
                             '!voice_bot status                                                     Get a status '
                             'report.'
                             '```\n\n'
                             'To restrict voice channel ID 1234 to ARK and ATLAS, we specify both Discord and Twitch '
                             'game names for ARK, as they differ. (Discord displays ARK: Survival Evolved, '
                             'Twitch displays ARK)\n'
                             '```'
                             '!voice_bot restrict 1234 ARK "ARK: Survival Evolved" ATLAS' 
                             '```')


@voice_bot.command(name='claim')
async def _claim(code, role=None):
    if settings.claimed:
        return False
    if code.lower() == 'help':
        await client.say('Claim the Voice Bot with claim code and attach '
                         'Role to Admin Role (or other).\n\n'
                         '!invite_bot claim code @role')
        return
    if role is None:
        await client.say('No role was provided.')
        return
    obj = re.findall(r'<@&(\d+)>', role)
    if not obj:
        await client.say(f'Invalid ID: {role}')
        return
    claimed = settings.claim(code, obj[0])
    if claimed:
        await client.say(f'Voice Bot successfully claimed!')


@voice_bot.command(name='set', pass_context=True)
async def _set(ctx, setting, arg):
    settable_props = ['general_voice_channel_id', 'bot_text_channel_id',
                      'game_close_disconnect_timeout', 'bot_admin_role_id']
    if not settings.authorize_command(ctx.message.author):
        return
    if setting in settable_props:
        if setting == 'bot_text_channel_id' and arg.lower() == 'none':
            arg = ''
        elif setting == 'game_close_disconnect_timeout':
            arg = int(arg)
        elif setting == 'bot_admin_role_id':
            role_id = re.findall(r'<@&(\d+)>', arg)
            if not role_id:
                await client.say(f'Invalid Role: {arg}')
                return
            else:
                arg = role_id[0]
        if settings.set_setting(setting, arg):
            await client.say(f'Set!')


@voice_bot.command(name='kick', pass_context=True)
async def _kick(ctx, state):
    if not settings.authorize_command(ctx.message.author):
        return
    if state.lower() == 'help':
        await client.say('Enabled or disables Voice Channel Kick. If disabled, '
                         'mutes the user instead.\n\n'
                         '!voice_bot kick enable\n'
                         '!voice_bot kick disable')
    elif state.lower() == 'enable':
        settings.set_kick_mode()
        await client.say('Kick mode enabled!')
    elif state.lower() == 'disable':
        settings.set_kick_mode(False)
        await client.say('Kick mode disabled!')
    else:
        await client.say(f'Invalid mode: {state}')


@voice_bot.command(name='whitelist', pass_context=True)
async def _whitelist(ctx, mode, *args):
    if not settings.authorize_command(ctx.message.author):
        return
    if mode.lower() == 'add':
        remove = False
    elif mode.lower() == 'remove':
        remove = True
    elif mode.lower() == 'list':
        users = '\n'.join([f'<@{user}>' for user in settings.whitelisted_user_ids])
        roles = '\n'.join([f'<@&{role}>' for role in settings.whitelisted_role_ids])
        message = f'**Whitelist**\n**Users:**\n{users}\n\n**Roles**:\n{roles}'
        await client.say(message)
        return
    elif mode.lower() == 'help':
        await client.say('Add user(s) or role(s) to the whitelist.\n\n'
                         '!voice_bot whitelist add|remove @user @role\n'
                         '!voice_bot whitelist list')
        return
    else:
        await client.say('Invalid whitelist mode. `Add`, `Remove`, or `List` only.')
        return
    if not args:
        await client.say('Must @ Role(s) or User(s)')
    for object_id in args:
        obj = re.findall(r'<@(\d+)>', object_id)
        if not obj:
            obj = re.findall(r'<@&(\d+)>', object_id)
            if not obj:
                print(object_id)
                await client.say(f'Invalid ID: {object_id}')
                continue
            else:
                for role in list(client.servers)[0].roles:
                    print((role.id, role.name))
                    if role.id == obj[0]:
                        settings.whitelist_role(role.id, remove)
                        if remove:
                            await client.say(f'Removed {role.mention} from Whitelist')
                        else:
                            await client.say(f'Whitelisted {role.mention}')
                        break
                else:
                    await client.say(f'ID {obj} not User or Role! Ignoring!')
                    continue
        else:
            member = list(client.servers)[0].get_member(obj[0])
            settings.whitelist_user(member.id, remove)
            if remove:
                await client.say(f'Removed {member.mention} from Whitelist')
            else:
                await client.say(f'Whitelisted {member.mention}')


@voice_bot.command(name='restrict', pass_context=True)
async def _restrict(ctx, channel, *args):
    if not settings.authorize_command(ctx.message.author):
        return
    if channel.lower() == 'help':
        await client.say('Add a voice channel to the restricted list.\n\n'
                         '!voice_bot restrict numeric_voice_channel_id '
                         'game game "game with spaces"')
    if channel.lower() == 'list':
        message = f'**Restricted Channels**\n\n'
        for channel, games in settings.restricted_voice_channels.items():
            channel = client.get_channel(channel)
            games = ', '.join(games)
            message += f'{channel}: {games}'
        await client.say(message)
        return
    if not args:
        await client.say('You must provide a list of games to restrict the channel to.')
        return
    channel = client.get_channel(channel)
    games = ', '.join(args)
    await client.say(f'Are you sure you want to restrict {channel.name} '
                     f'to people playing {games}?\n\n 1. Yes    2. No')
    response = await client.wait_for_message(author=ctx.message.author, timeout=30)
    if response is None or response.content != '1':
        await client.say('Aborted')
        return
    settings.restrict_channel(channel.id, args)
    await client.say(f'Restricted')


@voice_bot.command(name='release', pass_context=True)
async def _release(ctx, channel):
    if not settings.authorize_command(ctx.message.author):
        return
    if channel.lower() == 'help':
        await client.say('Releases a Voice Channel from any restrictions.\n\n'
                         '!voice_bot release numeric_channel_id')
        return
    if settings.release_channel(channel):
        await client.say('Channel Released!')


@voice_bot.command(name='status', pass_context=True)
async def _status(ctx):
    if not settings.authorize_command(ctx.message.author):
        return
    whitelisted_users = ', '.join(settings.whitelisted_user_ids)
    whitelisted_roles = ', '.join(settings.whitelisted_role_ids)
    restricted_channels = ''
    for channel, games in settings.restricted_voice_channels.items():
        channel = client.get_channel(channel)
        games = ', '.join(games)
        restricted_channels += f'{channel.name} ({channel.id}) -- {games}\n'
    await client.say(f'**Status:**\n'
                     '```'
                     f'Enabled: {settings.enabled}\n'
                     f'Kick Mode Enabled: {settings.kick_mode}\n'
                     f'Bot Admin Role ID: {settings.bot_admin_role_id}\n'
                     f'Whitelisted User IDs: {whitelisted_users}\n'
                     f'Whitelisted Role IDs: {whitelisted_roles}\n'
                     f'Game Close Disconnect Timeout: {settings.game_close_disconnect_timeout}s\n'
                     f'Restricted Voice Channels:\n\n{restricted_channels}'
                     '```')


def configure_logger(log_level, log_file_path):
    from sys import stdout
    log_format = logging.Formatter('%(asctime)s :: %(levelname)s: %(message)s', datefmt='%m/%d/%Y %H:%M:%S')
    logger.setLevel(log_level)
    console_handler = logging.StreamHandler(stdout)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    if log_file_path is not None:
        file_handler = RotatingFileHandler(log_file_path, maxBytes=5 * (1024 ** 2), backupCount=5)
        file_handler.setFormatter(log_format)
        logger.addHandler(file_handler)


def main():
    args = parse_args()
    configure_logger(args.log_level, args.log_file)
    if args.settings is not None:
        settings.file_path = args.settings
    logger.info('====== Discord Voice Chat Manager ======')
    if not settings.claimed:
        settings.claim_code = str(uuid4())
        logger.warning(f'THIS BOT IS UNCLAIMED')
        logger.warning(f'To claim this bot run this command:\n\n'
                       f'!voice_bot claim {settings.claim_code} @bot_admin_role')
    client.run(DISCORD_BOT_TOKEN)


if __name__ == '__main__':
    main()
    client.close()
