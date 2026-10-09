# Pokémon Discord Bot — Ultimate PvP Edition

Hybrid prefix + slash Pokémon-style Discord game.

## Commands
- `!start` / `/start`
- `!hunt` / `/hunt`
- `!catch <pokemon>` / `/catch <pokemon>`
- `!pokemon` / `/pokemon`
- `!pokedex <pokemon>` / `/pokedex <pokemon>`
- `!team` / `/team`
- `!setteam <pokemon_id> <slot>` / `/setteam`
- `!battle` / `/battle` — NPC battle with move buttons
- `!challenge @user` / `/challenge` — PvP challenge with move buttons
- `!heal` / `/heal`
- `!shop`, `!buy`, `!inventory`, `!daily`, `!balance`, `!leaderboard`

## Setup
1. Install Python 3.11+.
2. Open CMD in this folder.
3. Run `pip install -r requirements.txt`.
4. In Discord Developer Portal → Bot → Privileged Gateway Intents, enable **Message Content Intent** only.
5. In CMD: `set DISCORD_TOKEN=YOUR_TOKEN`.
6. Run `python bot.py`.

Keep your bot token private.
