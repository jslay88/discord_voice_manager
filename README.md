# Discord Voice Channel Manager

A Discord bot which has the ability to restrict voice channel 
access based off of the user's game currently played. The bot 
can either move the user to a General voice channel, or can 
Server Mute the user. This allows large Discord servers to 
better manager the users loitering within voice channels

## Installation

*Note: discord.py does not support Python 3.7 yet. It is 
recommended to use Python 3.6.4+*

Download the latest release through the Releases Tab.

Extract archive to desired location.

Install requirements with pip. It is recommended to install 
within a virtual environment.

    pip install -r requirements.txt

### passwords.py

This bot requires a token from Discord to run. See the 
Discord Developers page to create an application and bot.

This bot also requires a Twitch Client ID. This can be 
found in the Twitch Developers portal as well.

Copy `passwords.example.py` to `passwords.py` and fill in 
the details.

    DISCORD_BOT_TOKEN = 'LONG_RANDOM_STRING_FROM_DISCORD'
    TWITCH_CLIENT_ID = 'LONG_RANDOM_STRING_FROM_TWITCH'
    
### Service File

Assuming you are running this under a Linux environment 
with `systemd`, it is simple enough to configure the bot
as a systemd service. This assumes you have installed the 
bot to `/opt/voice_bot` with a `venv` virtual environment.

    [Unit]
    Description=Voice Channel Bot
    After=syslog.target network.target
    
    [Service]
    Type=simple
    User=discord
    WorkingDirectory=/opt/voice_bot
    ExecStart=/opt/voice_bot/venv/bin/python /opt/voice_bot/main.py
    Restart=always
    RestartSec=15
    
    [Install]
    WantedBy=multi-user.target

## Configuration

Run the bot manually for the first time. This will allow us 
to easily get the claim code produced on first runs.

    python main.py
    01/11/2019 XX:XX:00 :: INFO: ====== Discord Voice Chat Manager ======
    01/11/2019 XX:XX:00 :: WARNING: THIS BOT IS UNCLAIMED
    01/11/2019 XX:XX:00 :: WARNING: To claim this bot run this command:
    
    !voice_bot claim 5cefd113-8d0a-4871-a709-80d1c1cf8d47 @bot_admin_role

Now that we have the bot running, we need to add it to our server. 
Use the Discord Bot permissions calculator to give the bot 
`Send Messages` permission. Add the bot to the server. Then 
modify the bot's role that is automatically created.

The bot requires the following roles:
* Send Messages
* Move Members
* Mute Members

Add the bot to any private/restricted text channels that 
you may want to manage the bot from, if any.

From a text channel the bot is able to access, we need to 
issue the first set of commands to get things working.

#### Claim the Bot

We need to provide a role for the bot to attach "bot admin 
privileges to. Using the claim code/command produced earlier, 
run the claim command @ing the role. In a bot accessible text 
channel, run the command providing the claim code and @ing 
the bot's administrative role:

     !voice_bot claim 5cefd113-8d0a-4871-a709-80d1c1cf8d47 @bot_admin_role

This role will be required for any user issuing any further 
commands to this bot. If you need to, assign this role to 
yourself and continue.

#### Change Bot Admin Role

To change the Bot Admin Role after claiming the bot, issue the 
following command, @ing the role:

    !voice_bot set bot_admin_role_id @role

#### Setup General Voice Channel

When the bot is in kick mode, it needs to have a General voice 
channel to move members into when they fail the restrictions check.
In a bot accessible text channel, run the command providing a 
text channel ID:

    !voice_bot set general_voice_channel_id 412104631792041999

#### Setup Bot Text Channel

When a user fails the restrictions check for a voice channel, 
the bot can mention the user in a text channel of your choice, 
letting them known they failed the checks. In a bot accessible 
text channel, run the command providing a text channel ID:

    !voice_bot set bot_text_channel_id 533177011028623370
    
To disable this message to users, run the following command:

    !voice_bot set bot_text_channel_id none
    
#### Set Game Close Disconnect Timeout

When a user closes the game (or crashes), the bot will wait 
to see if the user rejoins their game before performing a 
restrictions check on the user. This period of time is 30 
seconds by default. To change this value, issue the following 
command, providing a new value in seconds:

    !voice_bot set game_close_disconnect_timeout 30 
    
## Usage    
    
#### Displaying Help Message

You can display a help message which lists a compact form 
of the available commands and a short description.

    !voice_bot help
    
#### Enable/Disable the Bot

By default, the bot starts disable. In a bot accessible text 
channel, run the following command:

    !voice_bot enable
    
You can disable the bot by issuing the following command:

    !voice_bot disable
    
#### Enable/Disable Kick Mode

By default, kick mode is enabled. This will move members to 
the configured General voice channel. When kick mode is 
disabled, it will Server Mute members instead. Remember, 
if you want to disable the bot entirely, use the 
enable/disable commands mentioned above.

    !voice_bot kick enable
    
You can disable kick mode (and enable 'mute mode') by 
issuing the following command:

    !voice_bot kick disable
    
#### Whitelisting

You will probably want to whitelist specific users or 
roles from being restricted by this bot. To do so, we 
can issue a list of @ed user(s) or role(s). In a bot 
accessible text channel: run the command providing 
a list of @ed user(s) and/or role(s), while also 
providing the mode in which you want to add or remove 
from the whitelist.

    !voice_bot whitelist add @user1 @user2 @role1 @role2
    !voice_bot whitelist remove @user1
    
To see the current whitelist, issue the following 
command:

    !voice_bot whitelist list
    
#### Restricting Voice Channels

To restrict a voice channel to a list of games that 
a player must be playing to pass the restriction checks, 
we need to know what the name of the game is in both 
Discord and Twitch. For instance, the game ARK: Survival 
Evolved, is reported differently by both Discord and Twitch. 
Discord presents `ARK: Survival Evolved` while Twitch 
provides `ARK`. The reason we need to provide a Twitch 
name, is so that Discord replaces the game name, with the 
stream name of the user's active stream. This bot will 
then query the Twitch API for the game they are playing 
on their stream. 

We can restrict a single voice channel to more than one 
game as well. **If a game name has spaces, wrap it in 
quotes.**

The following command is an example for 
restricting voice channel ID `12345` to `ARK`, `ARK: 
Survival Evolved`, and `ATLAS`.

    !voice_bot restrict 12345 ARK "ARK: Survival Evolved" ATLAS

#### Releasing a Voice Channel

To release a voice channel from all restrictions, issue the 
following command, providing the voice channel ID:

    !voice_bot release 12345
    
#### Status

You can see the current settings of the bot at any time 
with the following command:

    !voice_bot status
    
## Settings File

The bot's settings are stored in `bot_settings.pickle` in 
the same directory as `main.py`. You can override this 
location by running the script with `-s`, `--settings`. 
Feel free to backup/migrate this file if needed.

    python main.py -s /path/to/bot_settings.pickle
    python main.py --settings /path/to/bot_settings.pickle
