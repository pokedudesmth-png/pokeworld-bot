import os, random, sqlite3, asyncio, time, re, json, base64, inspect
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

# Read token from the hosting environment first, then fall back to a local .env file.
def _read_env_file_value(key):
    for env_path in (os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'), os.path.join(os.getcwd(), '.env')):
        try:
            with open(env_path, 'r', encoding='utf-8') as env_file:
                for raw_line in env_file:
                    line = raw_line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    name, value = line.split('=', 1)
                    if name.strip() == key:
                        value = value.strip()
                        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('\"', "'"):
                            value = value[1:-1]
                        return value or None
        except OSError:
            continue
    return None

TOKEN = os.getenv('DISCORD_TOKEN') or os.getenv('TOKEN') or _read_env_file_value('DISCORD_TOKEN') or _read_env_file_value('TOKEN')
PREFIX = '!'
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pokemon_game.db')
# Developer/owner Discord user IDs. Supports hosting variables or a local .env,
# and accepts comma-, semicolon-, or whitespace-separated IDs.
def _read_owner_ids():
    raw = (
        os.getenv('DISCORD_OWNER_IDS')
        or os.getenv('OWNER_IDS')
        or _read_env_file_value('DISCORD_OWNER_IDS')
        or _read_env_file_value('OWNER_IDS')
        or ''
    )
    # Allow values such as: 123456789012345678, 234567890123456789
    # Quotes and brackets are tolerated to make common hosting formats work.
    raw = raw.strip().strip('[](){}')
    owner_ids = set()
    for owner_id in re.split(r'[,;\s]+', raw):
        owner_id = owner_id.strip().strip('\"\'')
        if owner_id.isdigit():
            try:
                owner_ids.add(int(owner_id))
            except ValueError:
                pass
    return owner_ids

OWNER_IDS = _read_owner_ids()
API = 'https://pokeapi.co/api/v2'
API_CACHE, TYPE_CACHE, MOVE_CACHE = {}, {}, {}
SESSION: Optional[aiohttp.ClientSession] = None
POKEMON_LIST = []
ACTIVE_VIEWS = {}

# Stable product IDs used by !shop buy <id>. This is a curated battle-focused catalogue.
SHOP_ITEMS = {
  1: ('oran-berry', 'Oran Berry', 120, 'Heals 10 HP when used on a Pokémon', 'ora1'),
  2: ('sitrus-berry', 'Sitrus Berry', 300, 'Heals 25% of max HP when used', 'sit2'),
  3: ('pecha-berry', 'Pecha Berry', 150, 'Cures poison', 'pec3'),
  4: ('cheri-berry', 'Cheri Berry', 150, 'Cures paralysis', 'che4'),
  5: ('rawst-berry', 'Rawst Berry', 150, 'Cures burn', 'raw5'),
  6: ('aspear-berry', 'Aspear Berry', 150, 'Cures freeze', 'asp6'),
  7: ('chesto-berry', 'Chesto Berry', 150, 'Cures sleep', 'che7'),
  8: ('lum-berry', 'Lum Berry', 350, 'Cures any major status condition', 'lum8'),
  9: ('leppa-berry', 'Leppa Berry', 250, 'Battle stamina item; restores a small amount of HP in this game', 'lep9'),
  10: ('figy-berry', 'Figy Berry', 250, 'Heals 20% of max HP when used', 'fig10'),
  11: ('wiki-berry', 'Wiki Berry', 250, 'Heals 20% of max HP when used', 'wik11'),
  12: ('mago-berry', 'Mago Berry', 250, 'Heals 20% of max HP when used', 'mag12'),
  13: ('aguav-berry', 'Aguav Berry', 250, 'Heals 20% of max HP when used', 'agu13'),
  14: ('iapapa-berry', 'Iapapa Berry', 250, 'Heals 20% of max HP when used', 'iap14'),
  15: ('leftovers', 'Leftovers', 1800, 'Held item; provides small passive healing after surviving a battle turn', 'lef15'),
  16: ('choice-band', 'Choice Band', 10000, 'Held item; increases physical damage', 'cho16'),
  17: ('choice-specs', 'Choice Specs', 10000, 'Held item; increases special damage', 'cho17'),
  18: ('choice-scarf', 'Choice Scarf', 10000, 'Held item; boosts Speed and slightly increases damage in this simplified battle system', 'cho18'),
  19: ('life-orb', 'Life Orb', 2500, 'Held item; boosts damage', 'lif19'),
  20: ('expert-belt', 'Expert Belt', 2000, 'Held item; boosts super-effective damage', 'exp20'),
  21: ('focus-sash', 'Focus Sash', 2000, 'Held item; may help survive a hit', 'foc21'),
  22: ('assault-vest', 'Assault Vest', 1800, 'Held item; reduces incoming damage slightly', 'ass22'),
  23: ('rocky-helmet', 'Rocky Helmet', 1800, 'Held item; retaliates with minor damage after being hit', 'roc23'),
  24: ('muscle-band', 'Muscle Band', 1500, 'Held item; boosts physical damage', 'mus24'),
  25: ('wise-glasses', 'Wise Glasses', 1500, 'Held item; boosts special damage', 'wis25'),
  26: ('shell-bell', 'Shell Bell', 1600, 'Held item; heals a little after dealing damage', 'she26'),
  27: ('safety-goggles', 'Safety Goggles', 1200, 'Held item; status protection flavour effect', 'saf27'),
  28: ('heavy-duty-boots', 'Heavy-Duty Boots', 1300, 'Held item; reduces incoming damage slightly (entry hazards are not implemented)', 'hea28'),
  29: ('black-belt', 'Black Belt', 1000, 'Held item; boosts Fighting-type move damage', 'bla29'),
  30: ('charcoal', 'Charcoal', 1000, 'Held item; boosts Fire-type move damage', 'cha30'),
  31: ('mystic-water', 'Mystic Water', 1000, 'Held item; boosts Water-type move damage', 'mys31'),
  32: ('magnet', 'Magnet', 1000, 'Held item; boosts Electric-type move damage', 'mag32'),
  33: ('miracle-seed', 'Miracle Seed', 1000, 'Held item; boosts Grass-type move damage', 'mir33'),
  34: ('never-melt-ice', 'Never-Melt Ice', 1000, 'Held item; boosts Ice-type move damage', 'nev34'),
  35: ('spell-tag', 'Spell Tag', 1000, 'Held item; boosts Ghost-type move damage', 'spe35'),
  36: ('dragon-fang', 'Dragon Fang', 1000, 'Held item; boosts Dragon-type move damage', 'dra36'),
  37: ('silk-scarf', 'Silk Scarf', 1000, 'Held item; boosts Normal-type move damage', 'sil37'),
  38: ('sharp-beak', 'Sharp Beak', 1000, 'Held item; boosts Flying-type move damage', 'sha38'),
  39: ('poison-barb', 'Poison Barb', 1000, 'Held item; boosts Poison-type move damage', 'poi39'),
  40: ('soft-sand', 'Soft Sand', 1000, 'Held item; boosts Ground-type move damage', 'sof40'),
  41: ('hard-stone', 'Hard Stone', 1000, 'Held item; boosts Rock-type move damage', 'har41'),
  42: ('silver-powder', 'Silver Powder', 1000, 'Held item; boosts Bug-type move damage', 'sil42'),
  43: ('black-glasses', 'Black Glasses', 1000, 'Held item; boosts Dark-type move damage', 'bla43'),
  44: ('twisted-spoon', 'Twisted Spoon', 1000, 'Held item; boosts Psychic-type move damage', 'twi44'),
  45: ('metal-coat', 'Metal Coat', 1000, 'Held item; boosts Steel-type move damage', 'met45'),
  46: ('pixie-plate', 'Pixie Plate', 1000, 'Held item; boosts Fairy-type move damage', 'pix46'),
  47: ('potion', 'Potion', 300, 'Consumable; restores 20 HP', 'pot47'),
  48: ('super-potion', 'Super Potion', 700, 'Consumable; restores 50 HP', 'sup48'),
  49: ('hyper-potion', 'Hyper Potion', 1500, 'Consumable; restores 120 HP', 'hyp49'),
  50: ('max-potion', 'Max Potion', 2500, 'Consumable; restores all HP', 'max50'),
  51: ('full-restore', 'Full Restore', 3000, 'Consumable; restores all HP and cures status', 'ful51'),
  52: ('fast-tm', 'Fast TM', 5000, 'Changes a Pokémon’s Fast Move randomly', 'ftm52'),
  53: ('charged-tm', 'Charged TM', 10000, 'Changes a Pokémon’s Charged Move randomly', 'ctm53'),
  54: ('elite-charged-tm', 'Elite Charged TM', 25000, 'Choose the Pokémon’s new Charged Move', 'ectm54'),
}
ITEM_BY_KEY = {v[0]: (k, *v) for k,v in SHOP_ITEMS.items()}
# Display-only emojis; no catalog, pricing, or game mechanics are changed.
ITEM_EMOJI = {
 'oran-berry':'🍊','sitrus-berry':'🍋','pecha-berry':'🍑','cheri-berry':'🍒','rawst-berry':'🍇',
 'aspear-berry':'🍐','chesto-berry':'🫐','lum-berry':'🍈','leppa-berry':'🍓','figy-berry':'🥝',
 'wiki-berry':'🍎','mago-berry':'🥭','aguav-berry':'🍍','iapapa-berry':'🥥',
 'leftovers':'🍱','choice-band':'🎗️','choice-specs':'🕶️','choice-scarf':'🧣','life-orb':'🔮',
 'expert-belt':'🥋','focus-sash':'🪢','assault-vest':'🦺','rocky-helmet':'⛑️','muscle-band':'💪',
 'wise-glasses':'👓','shell-bell':'🐚','safety-goggles':'🥽','heavy-duty-boots':'🥾','black-belt':'🏅',
 'charcoal':'🪵','mystic-water':'💧','magnet':'🧲','miracle-seed':'🌱','never-melt-ice':'🧊',
 'spell-tag':'📜','dragon-fang':'🦷','silk-scarf':'🧵','sharp-beak':'🪶','poison-barb':'🦂',
 'soft-sand':'🏜️','hard-stone':'🪨','silver-powder':'✨','black-glasses':'🌑','twisted-spoon':'🥄',
 'metal-coat':'🛡️','pixie-plate':'🧚','potion':'🧪','super-potion':'⚗️','hyper-potion':'💉',
 'max-potion':'❤️‍🩹','full-restore':'💖','fast-tm':'⚡','charged-tm':'🔋','elite-charged-tm':'🌟'
}
# Official item sprites are uploaded to this Discord server as custom emojis by
# !setupitememojis. The mapping is persisted beside bot.py so restarts keep working.
ITEM_EMOJI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'item_emojis.json')
VANTACOIN_EMOJI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vantacoin_emoji.json')
def get_vantacoin_emoji():
    try:
        with open(VANTACOIN_EMOJI_FILE, 'r', encoding='utf-8') as f:
            value = json.load(f).get('emoji')
            if value: return value
    except (OSError, ValueError, TypeError):
        pass
    return ''  # Do not substitute a generic coin emoji when the custom sprite is unavailable.

# Actual user-provided VantaCoin artwork, resized to Discord's 128px emoji dimensions.
VANTACOIN_SPRITE_B64 = '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'
# Keep actual server-uploaded item sprites separate from the decorative Unicode
# approximations. The shop uses only this map, so it never substitutes 🍒/🧪 etc.
SHOP_ITEM_EMOJI = {}
try:
    with open(ITEM_EMOJI_FILE, 'r', encoding='utf-8') as _emoji_file:
        _saved_item_emojis = json.load(_emoji_file)
    if isinstance(_saved_item_emojis, dict):
        SHOP_ITEM_EMOJI.update({str(k): str(v) for k, v in _saved_item_emojis.items()})
        ITEM_EMOJI.update({str(k): str(v) for k, v in _saved_item_emojis.items()})
except (OSError, ValueError, TypeError):
    pass

def item_emoji(item):
    return ITEM_EMOJI.get(item, '🎒')
SHOP_ALIASES = {}
for _pid, (_key, _label, _cost, _desc, _short) in SHOP_ITEMS.items():
    for _alias in (_key, _label, _short, str(_pid)):
        SHOP_ALIASES[re.sub(r'[^a-z0-9]', '', _alias.lower())] = _pid

# Extra player-friendly aliases for all TMs accepted by !giveitem.
# Numeric IDs and catalog shortforms (ftm52 / ctm53 / ectm54) also work.
SHOP_ALIASES.update({
    'fasttm': 52,
    'ftm': 52,
    'fasttechnicalmachine': 52,
    'chargedtm': 53,
    'ctm': 53,
    'chargedtechnicalmachine': 53,
    'elitechargedtm': 54,
    'elitectm': 54,
    'ectm': 54,
    'elitechargedtechnicalmachine': 54,
})

def resolve_shop_product(value):
    cleaned = re.sub(r'[^a-z0-9]', '', str(value).lower())
    return SHOP_ALIASES.get(cleaned)
TYPE_CHART = {
'normal':{'rock':.5,'ghost':0,'steel':.5}, 'fire':{'fire':.5,'water':.5,'grass':2,'ice':2,'bug':2,'rock':.5,'dragon':.5,'steel':2},
'water':{'fire':2,'water':.5,'grass':.5,'ground':2,'rock':2,'dragon':.5}, 'electric':{'water':2,'electric':.5,'grass':.5,'ground':0,'flying':2,'dragon':.5},
'grass':{'fire':.5,'water':2,'grass':.5,'poison':.5,'ground':2,'flying':.5,'bug':.5,'rock':2,'dragon':.5,'steel':.5},
'ice':{'fire':.5,'water':.5,'grass':2,'ice':.5,'ground':2,'flying':2,'dragon':2,'steel':.5},
'fighting':{'normal':2,'ice':2,'rock':2,'dark':2,'steel':2,'poison':.5,'flying':.5,'psychic':.5,'bug':.5,'fairy':.5,'ghost':0},
'poison':{'grass':2,'poison':.5,'ground':.5,'rock':.5,'ghost':.5,'steel':0,'fairy':2}, 'ground':{'fire':2,'electric':2,'grass':.5,'poison':2,'flying':0,'bug':.5,'rock':2,'steel':2},
'flying':{'electric':.5,'grass':2,'fighting':2,'bug':2,'rock':.5,'steel':.5}, 'psychic':{'fighting':2,'poison':2,'psychic':.5,'steel':.5,'dark':0},
'bug':{'fire':.5,'grass':2,'fighting':.5,'poison':.5,'flying':.5,'psychic':2,'ghost':.5,'dark':2,'steel':.5,'fairy':.5},
'rock':{'fire':2,'ice':2,'fighting':.5,'ground':.5,'flying':2,'bug':2,'steel':.5}, 'ghost':{'normal':0,'psychic':2,'ghost':2,'dark':.5},
'dragon':{'dragon':2,'steel':.5,'fairy':0}, 'dark':{'fighting':.5,'psychic':2,'ghost':2,'dark':.5,'fairy':.5},
'steel':{'fire':.5,'water':.5,'electric':.5,'ice':2,'rock':2,'steel':.5,'fairy':2}, 'fairy':{'fire':.5,'fighting':2,'poison':.5,'dragon':2,'dark':2,'steel':.5}}


def db(): return sqlite3.connect(DB)
def setup():
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS players(user_id INTEGER PRIMARY KEY, coins INTEGER DEFAULT 500, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, daily INTEGER DEFAULT 0, daily_streak INTEGER DEFAULT 0, started INTEGER DEFAULT 0)')
        c.execute("CREATE TABLE IF NOT EXISTS bot_bans(user_id INTEGER PRIMARY KEY, reason TEXT NOT NULL DEFAULT 'Violation of game rules', banned_by INTEGER NOT NULL, banned_at INTEGER NOT NULL)")
        c.execute('CREATE TABLE IF NOT EXISTS nick_freezes(guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, freezer_id INTEGER NOT NULL, original_nick TEXT, locked_nick TEXT, PRIMARY KEY(guild_id,user_id))')
        freeze_cols=[r[1] for r in c.execute('PRAGMA table_info(nick_freezes)').fetchall()]
        if 'locked_nick' not in freeze_cols: c.execute('ALTER TABLE nick_freezes ADD COLUMN locked_nick TEXT')
        c.execute('UPDATE nick_freezes SET locked_nick=original_nick WHERE locked_nick IS NULL')
        cols=[r[1] for r in c.execute('PRAGMA table_info(players)').fetchall()]
        if 'daily_streak' not in cols: c.execute('ALTER TABLE players ADD COLUMN daily_streak INTEGER DEFAULT 0')
        if 'started' not in cols:
            c.execute('ALTER TABLE players ADD COLUMN started INTEGER DEFAULT 0')
            # Existing trainers were already playing before this feature existed.
            c.execute('UPDATE players SET started=1')
        c.execute('CREATE TABLE IF NOT EXISTS pokemon(instance_id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,dex_id INTEGER,name TEXT,level INTEGER DEFAULT 5,xp INTEGER DEFAULT 0,shiny INTEGER DEFAULT 0,nickname TEXT DEFAULT "",hp INTEGER DEFAULT 1,max_hp INTEGER DEFAULT 1,held_item TEXT DEFAULT "",status_condition TEXT DEFAULT "")')
        c.execute("CREATE TABLE IF NOT EXISTS pokedex_entries(user_id INTEGER NOT NULL,dex_id INTEGER NOT NULL,name TEXT NOT NULL,shiny INTEGER NOT NULL DEFAULT 0,registered_at INTEGER DEFAULT 0,PRIMARY KEY(user_id,dex_id,shiny))")
        pcols=[r[1] for r in c.execute('PRAGMA table_info(pokemon)').fetchall()]
        if 'held_item' not in pcols: c.execute('ALTER TABLE pokemon ADD COLUMN held_item TEXT DEFAULT ""')
        if 'status_condition' not in pcols: c.execute('ALTER TABLE pokemon ADD COLUMN status_condition TEXT DEFAULT ""')
        if 'fast_move' not in pcols: c.execute('ALTER TABLE pokemon ADD COLUMN fast_move TEXT DEFAULT ""')
        if 'charged_move' not in pcols: c.execute('ALTER TABLE pokemon ADD COLUMN charged_move TEXT DEFAULT ""')
        if 'box_id' not in pcols: c.execute('ALTER TABLE pokemon ADD COLUMN box_id INTEGER')
        # Backfill stable, per-owner collection IDs. Listed Pokémon are unowned and receive an ID on return/purchase.
        owners=c.execute('SELECT DISTINCT user_id FROM pokemon WHERE user_id IS NOT NULL AND user_id<>0').fetchall()
        for (owner_id,) in owners:
            existing={int(r[0]) for r in c.execute('SELECT box_id FROM pokemon WHERE user_id=? AND box_id IS NOT NULL',(owner_id,)).fetchall()}
            next_id=max(existing,default=0)+1
            missing=c.execute('SELECT instance_id FROM pokemon WHERE user_id=? AND box_id IS NULL ORDER BY instance_id',(owner_id,)).fetchall()
            for (global_id,) in missing:
                while next_id in existing: next_id+=1
                c.execute('UPDATE pokemon SET box_id=? WHERE instance_id=?',(next_id,global_id)); existing.add(next_id); next_id+=1
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_pokemon_owner_box_id ON pokemon(user_id,box_id) WHERE user_id IS NOT NULL AND user_id<>0 AND box_id IS NOT NULL')
        c.execute('CREATE TABLE IF NOT EXISTS hunt_counts(user_id INTEGER PRIMARY KEY, count INTEGER DEFAULT 0)')
        c.execute('CREATE TABLE IF NOT EXISTS boss_encounters(user_id INTEGER PRIMARY KEY,dex_id INTEGER,name TEXT,level INTEGER,shiny INTEGER DEFAULT 0)')
        c.execute('CREATE TABLE IF NOT EXISTS boss_party(user_id INTEGER,slot INTEGER,instance_id INTEGER,PRIMARY KEY(user_id,slot),UNIQUE(user_id,instance_id))')
        c.execute('CREATE TABLE IF NOT EXISTS raid_encounters(user_id INTEGER PRIMARY KEY,dex_id INTEGER,name TEXT,level INTEGER,shiny INTEGER DEFAULT 1)')
        c.execute('CREATE TABLE IF NOT EXISTS raid_party(user_id INTEGER,slot INTEGER,instance_id INTEGER,PRIMARY KEY(user_id,slot),UNIQUE(user_id,instance_id))')
        c.execute('UPDATE pokemon SET level=300 WHERE level>300')
        c.execute('CREATE TABLE IF NOT EXISTS team(user_id INTEGER,slot INTEGER,instance_id INTEGER,PRIMARY KEY(user_id,slot))')
        c.execute('CREATE TABLE IF NOT EXISTS inventory(user_id INTEGER,item TEXT,amount INTEGER,PRIMARY KEY(user_id,item))')
        c.execute('CREATE TABLE IF NOT EXISTS encounters(user_id INTEGER PRIMARY KEY,dex_id INTEGER,name TEXT,shiny INTEGER DEFAULT 0,level INTEGER DEFAULT 5,hints_used INTEGER DEFAULT 0)')
        # One server-wide special encounter: the first correct guess claims it.
        c.execute('CREATE TABLE IF NOT EXISTS global_encounter(id INTEGER PRIMARY KEY CHECK(id=1),dex_id INTEGER,name TEXT,shiny INTEGER DEFAULT 1,level INTEGER DEFAULT 5,spawned_by INTEGER)')
        cols=[r[1] for r in c.execute('PRAGMA table_info(encounters)').fetchall()]
        if 'hints_used' not in cols: c.execute('ALTER TABLE encounters ADD COLUMN hints_used INTEGER DEFAULT 0')

def resolve_box_id(conn, uid, box_id):
    """Translate a trainer-visible collection ID into the internal global instance_id."""
    if box_id is None: return None
    row=conn.execute('SELECT instance_id FROM pokemon WHERE user_id=? AND box_id=?',(uid,int(box_id))).fetchone()
    return int(row[0]) if row else None

def get_box_id(conn, uid, instance_id):
    row=conn.execute('SELECT box_id FROM pokemon WHERE user_id=? AND instance_id=?',(uid,instance_id)).fetchone()
    return int(row[0]) if row and row[0] is not None else None

def assign_box_id(conn, uid, instance_id):
    if uid is None or int(uid)==0: return None
    current=get_box_id(conn,uid,instance_id)
    if current is not None: return current
    row=conn.execute('SELECT COALESCE(MAX(box_id),0)+1 FROM pokemon WHERE user_id=?',(uid,)).fetchone()
    new_id=int(row[0] or 1)
    conn.execute('UPDATE pokemon SET box_id=? WHERE instance_id=? AND user_id=?',(new_id,instance_id,uid))
    return new_id

def transfer_pokemon_owner(conn, instance_id, old_uid, new_uid):
    """Transfer internal Pokémon identity while assigning a fresh ID in the recipient's box."""
    if new_uid and int(new_uid)!=0:
        row=conn.execute('SELECT COALESCE(MAX(box_id),0)+1 FROM pokemon WHERE user_id=?',(new_uid,)).fetchone()
        new_box_id=int(row[0] or 1)
    else: new_box_id=None
    for table in ('team','boss_party','raid_party'):
        conn.execute(f'DELETE FROM {table} WHERE instance_id=?',(instance_id,))
    conn.execute('UPDATE pokemon SET user_id=?,box_id=? WHERE instance_id=? AND user_id=?',(new_uid,new_box_id,instance_id,old_uid))
    return new_box_id

def ensure_player(uid):
    with db() as c:
        c.execute('INSERT OR IGNORE INTO players(user_id) VALUES(?)',(uid,))
        c.execute("DELETE FROM inventory WHERE user_id=? AND item IN ('pokeball','greatball','ultraball','masterball')", (uid,))
def get_player(uid):
    ensure_player(uid)
    with db() as c: return c.execute('SELECT coins,xp,level,daily,daily_streak FROM players WHERE user_id=?',(uid,)).fetchone()
def add_progress(uid,coins=0,xp=0):
    coins0,xp0,level,daily,*_=get_player(uid); xp0+=xp
    while xp0>=level*100: xp0-=level*100; level+=1
    with db() as c: c.execute('UPDATE players SET coins=?,xp=?,level=? WHERE user_id=?',(coins0+coins,xp0,level,uid))
    return level
def inventory_amount(uid,item):
    ensure_player(uid)
    with db() as c:
        r=c.execute('SELECT amount FROM inventory WHERE user_id=? AND item=?',(uid,item)).fetchone(); return r[0] if r else 0
def change_item(uid,item,delta):
    with db() as c:
        c.execute('INSERT OR IGNORE INTO inventory VALUES(?,?,0)',(uid,item,0))
        current=c.execute('SELECT amount FROM inventory WHERE user_id=? AND item=?',(uid,item)).fetchone()[0]
        if current + delta < 0:
            raise ValueError(f'Insufficient inventory quantity for {item}: have {current}, need {-delta}')
        c.execute('UPDATE inventory SET amount=amount+? WHERE user_id=? AND item=?',(delta,uid,item))

async def api_get(path):
    global SESSION
    if path in API_CACHE: return API_CACHE[path]
    if SESSION is None: SESSION=aiohttp.ClientSession()
    async with SESSION.get(API+path,timeout=aiohttp.ClientTimeout(total=25)) as r:
        if r.status!=200: raise RuntimeError(f'PokéAPI HTTP {r.status}')
        d=await r.json(); API_CACHE[path]=d; return d
async def load_pokemon_list():
    global POKEMON_LIST
    POKEMON_LIST=(await api_get('/pokemon-species?limit=10000&offset=0'))['results']
async def pokemon_data(x):
    """Fetch battle-ready Pokémon data, with a species fallback for old/stale DB IDs.

    Older database versions may store a Pokédex species ID that does not map
    directly to a /pokemon/{id} record (or a species/form name). If the direct
    endpoint returns 404, resolve the species' default variety instead.
    """
    key = str(x).strip().lower()
    try:
        return await api_get(f'/pokemon/{key}')
    except RuntimeError as exc:
        if 'HTTP 404' not in str(exc):
            raise
    species = await api_get(f'/pokemon-species/{key}')
    varieties = species.get('varieties') or []
    chosen = next((v.get('pokemon', {}).get('name') for v in varieties if v.get('is_default')), None)
    if not chosen and varieties:
        chosen = varieties[0].get('pokemon', {}).get('name')
    if not chosen:
        raise RuntimeError(f'PokéAPI has no Pokémon variety for species {key!r}')
    return await api_get(f'/pokemon/{chosen}')

async def move_data(x): return await api_get(f'/move/{x}')
def display_name(d): return d['name'].replace('-',' ').title()
def type_text(d): return ' / '.join(x['type']['name'].title() for x in d['types'])

def stats(d): return {x['stat']['name']:x['base_stat'] for x in d['stats']}
def sprite(d, shiny=False):
    s=d.get('sprites',{}); art=s.get('other',{}).get('official-artwork',{})
    if shiny:
        return art.get('front_shiny') or s.get('front_shiny') or art.get('front_default') or s.get('front_default')
    return art.get('front_default') or s.get('front_default')
def max_hp(d,lvl): return max(1,int((2*stats(d).get('hp',50)*lvl)/100+lvl+10))
def hp_bar(current, maximum, width=12):
    maximum=max(1,maximum); filled=max(0,min(width,round(current/maximum*width)))
    return f'`{"▰"*filled}{"▱"*(width-filled)}` **{max(0,current)}/{maximum}**'
def effectiveness(mt,dt):
    z=1
    for t in dt:z*=TYPE_CHART.get(mt,{}).get(t,1)
    return z
LEGENDARY_NAMES = {
'mewtwo','mew','lugia','ho-oh','celebi','regirock','regice','registeel','latias','latios','kyogre','groudon','rayquaza','jirachi','deoxys','uxie','mesprit','azelf','dialga','palkia','giratina','heatran','regigigas','cresselia','phione','manaphy','darkrai','shaymin','arceus','victini','cobalion','terrakion','virizion','tornadus','thundurus','reshiram','zekrom','landorus','kyurem','keldeo','meloetta','genesect','xerneas','yveltal','zygarde','diancie','hoopa','volcanion','type-null','silvally','tapu-koko','tapu-lele','tapu-bulu','tapu-fini','cosmog','cosmoem','solgaleo','lunala','necrozma','magearna','marshadow','zeraora','melmetal','zacian','zamazenta','eternatus','kubfu','urshifu','regieleki','regidrago','glastrier','spectrier','calyrex','enamorus','wo-chien','chien-pao','ting-lu','chi-yu','koraidon','miraidon','okidogi','munkidori','fezandipiti','ogerpon','terapagos','pecharunt','nihilego','buzzwole','pheromosa','xurkitree','celesteela','kartana','guzzlord','poipole','naganadel','stakataka','blacephalon'}


# Discord can show authentic type-symbol artwork inline only as server custom emojis.
# These names are used when the matching type emojis have been uploaded to the server.
def move_type_display(guild, move):
    typename = (move.get('type') or {}).get('name', 'unknown').lower()
    if guild is not None:
        emoji = discord.utils.get(guild.emojis, name=f'type_{typename}')
        if emoji is None:
            emoji = discord.utils.get(guild.emojis, name=typename)
        if emoji is not None:
            return str(emoji)
    return f'[{typename.title()}]'

async def saved_move_details(row, guild):
    # Re-read by ID so this works for both compact !info rows and full database rows.
    with db() as c:
        full = c.execute('SELECT * FROM pokemon WHERE instance_id=?', (row[0],)).fetchone()
    if not full:
        raise ValueError('Pokémon row no longer exists')
    species = full[3]
    fast_name = full[12] if len(full) > 12 else ''
    charged_name = full[13] if len(full) > 13 else ''
    if not fast_name:
        fast_pool = await move_pool(species, True)
        fast_name = random.choice(fast_pool)['name']
    if not charged_name:
        charged_pool = await move_pool(species, False)
        charged_name = random.choice(charged_pool)['name']
    with db() as c:
        c.execute('UPDATE pokemon SET fast_move=?, charged_move=? WHERE instance_id=?', (fast_name, charged_name, full[0]))
    fast = await move_data(fast_name)
    charged = await move_data(charged_name)
    return (f"{move_type_display(guild, fast)} **{fast.get('name', fast_name).replace('-', ' ').title()}**",
            f"{move_type_display(guild, charged)} **{charged.get('name', charged_name).replace('-', ' ').title()}**")

async def random_pokemon():
    # Regular encounters never include legendary, mythical, or Ultra Beast species.
    if not POKEMON_LIST: await load_pokemon_list()
    candidates=[x for x in POKEMON_LIST if x['name'] not in LEGENDARY_NAMES]
    if not candidates: raise RuntimeError('No regular Pokémon available in the species list.')
    return await pokemon_data(random.choice(candidates)['name'])
async def get_moves(d,limit=4):
    names=[]
    healing_moves={'recover','roost','moonlight','synthesis','soft-boiled','slack-off','shore-up'}
    for m in d.get('moves',[]):
        lv=[v['level_learned_at'] for v in m['version_group_details'] if v['move_learn_method']['name']=='level-up']
        if lv:names.append((max(lv),m['move']['name']))
    names=[x[1] for x in sorted(names)[-20:]]; random.shuffle(names); out=[]
    for n in names:
        try:
            m=await move_data(n)
            if (m.get('power') and m.get('damage_class',{}).get('name')!='status') or n in healing_moves: out.append(m)
        except: pass
        if len(out)>=limit: break
    if not out: out=[await move_data('tackle')]
    return out

MOVE_POOL_CACHE = {}

async def move_pool(species, fast=True):
    # Cache each species' move pool to avoid rebuilding it on every battle turn.
    cache_key=(str(species).lower(), bool(fast))
    if cache_key in MOVE_POOL_CACHE:
        return [dict(m) for m in MOVE_POOL_CACHE[cache_key]]
    d = await pokemon_data(species)
    names=[]
    for entry in d.get('moves',[]):
        details=entry.get('version_group_details',[])
        if not any(x.get('move_learn_method',{}).get('name') in ('level-up','machine','egg') for x in details):
            continue
        names.append(entry['move']['name'])
    out=[]
    for name in dict.fromkeys(names):
        try:
            m=await move_data(name)
            if not m.get('power') or m.get('damage_class',{}).get('name')=='status': continue
            power=m.get('power') or 0
            if (power <= 60) == fast: out.append(m)
        except Exception: pass
    if not out:
        out=[await move_data('tackle' if fast else 'swift')]
    MOVE_POOL_CACHE[cache_key]=[dict(m) for m in out]
    return [dict(m) for m in out]

async def saved_battle_moves(row):
    species=row[2]
    # pokemon schema: fast_move is column 12 and charged_move is column 13.
    # Read the full row by instance ID so compact query rows are safe too.
    with db() as c:
        saved = c.execute('SELECT fast_move, charged_move FROM pokemon WHERE instance_id=?', (row[0],)).fetchone()
    fast_name = (saved[0] or '') if saved else ''
    charged_name = (saved[1] or '') if saved else ''
    if not fast_name:
        pool=await move_pool(species,True); fast=random.choice(pool)
        fast_name=fast['name']
    else: fast=await move_data(fast_name)
    if not charged_name:
        pool=await move_pool(species,False); charged=random.choice(pool)
        charged_name=charged['name']
    else: charged=await move_data(charged_name)
    with db() as c: c.execute('UPDATE pokemon SET fast_move=?,charged_move=? WHERE instance_id=?',(fast_name,charged_name,row[0]))
    fast=dict(fast); fast['_battle_kind']='fast'
    charged=dict(charged); charged['_battle_kind']='charged'
    # Fast attacks are intentionally weaker; Charged attacks hit much harder.
    fast['power']=max(10,int((fast.get('power') or 40)*0.55))
    charged['power']=max(50,int((charged.get('power') or 60)*1.8))
    return [fast,charged]

def calc_damage(attacker, defender, move, level):
    a=stats(attacker); b=stats(defender); physical=move.get('damage_class',{}).get('name')=='physical'
    atk=a.get('attack' if physical else 'special-attack',50); defense=b.get('defense' if physical else 'special-defense',50)
    mt=move['type']['name']; at=[x['type']['name'] for x in attacker['types']]; dt=[x['type']['name'] for x in defender['types']]
    stab=1.5 if mt in at else 1; eff=effectiveness(mt,dt); crit=1.5 if random.random()<.0625 else 1
    damage=max(1,int((((2*level/5+2)*(move.get('power') or 40)*atk/max(1,defense))/50+2)*stab*eff*crit*random.uniform(.85,1)))
    return damage,eff,crit>1

TYPE_HELD_ITEMS = {'black-belt':'fighting','charcoal':'fire','mystic-water':'water','magnet':'electric','miracle-seed':'grass','never-melt-ice':'ice','spell-tag':'ghost','dragon-fang':'dragon','silk-scarf':'normal','sharp-beak':'flying','poison-barb':'poison','soft-sand':'ground','hard-stone':'rock','silver-powder':'bug','black-glasses':'dark','twisted-spoon':'psychic','metal-coat':'steel','pixie-plate':'fairy'}
def held_damage_multiplier(held, move, effectiveness_value=1):
    """Apply offensive held-item effects consistently in every battle mode."""
    kind=move.get('damage_class',{}).get('name','')
    mtype=(move.get('type') or {}).get('name','')
    mult=1.0
    if held=='choice-band' and kind=='physical': mult*=1.5
    if held=='choice-specs' and kind=='special': mult*=1.5
    if held=='life-orb': mult*=1.3
    if held=='choice-scarf': mult*=1.1  # speed is also boosted in turn-order calculations
    if held=='muscle-band' and kind=='physical': mult*=1.1
    if held=='wise-glasses' and kind=='special': mult*=1.1
    if held=='expert-belt' and effectiveness_value>1: mult*=1.2
    if TYPE_HELD_ITEMS.get(held)==mtype: mult*=1.2
    return mult

def held_incoming_multiplier(held):
    """Defensive held-item effects shared by NPC, legendary, raid and PvP battles."""
    mult=1.0
    if held=='assault-vest': mult*=0.8
    elif held=='heavy-duty-boots': mult*=0.9  # No entry hazards exist, so a small defensive perk is used.
    return mult

def held_prevents_status(held):
    return held in {'safety-goggles'}

async def owned_lead(uid):
    with db() as c: return c.execute('SELECT p.* FROM pokemon p JOIN team t ON t.instance_id=p.instance_id WHERE t.user_id=? ORDER BY t.slot LIMIT 1',(uid,)).fetchone()

STATUS_NAMES = {'poison':'poisoned','badly-poisoned':'badly poisoned','burn':'burned','paralysis':'paralyzed','sleep':'asleep','freeze':'frozen'}
def status_from_move(move):
    meta=move.get('meta') or {}; ail=(meta.get('ailment') or {}).get('name','none')
    chance=meta.get('ailment_chance') or 0
    if ail in STATUS_NAMES and chance>0 and random.randint(1,100)<=chance: return ail
    # PokéAPI also tags a few damaging moves with secondary-effect metadata inconsistently.
    fallback={'poison-sting':'poison','sludge-bomb':'poison','poison-jab':'poison','toxic':'badly-poisoned','thunder-shock':'paralysis','thunderbolt':'paralysis','thunder-wave':'paralysis','body-slam':'paralysis','flamethrower':'burn','fire-blast':'burn','ember':'burn','will-o-wisp':'burn','ice-beam':'freeze','blizzard':'freeze','ice-punch':'freeze','hypnosis':'sleep','sleep-powder':'sleep','spore':'sleep'}
    ail=fallback.get(move.get('name',''), '')
    return ail if ail and random.randint(1,100)<=30 else ''
def status_tick(status, hp, maximum):
    if not status or hp<=0: return hp, ''
    if status in ('poison','badly-poisoned'): damage=max(1,maximum//8 if status=='badly-poisoned' else maximum//12); return max(0,hp-damage), f'☠️ Status damage: {status.replace("-"," ")} dealt {damage} damage.'
    if status=='burn': damage=max(1,maximum//16); return max(0,hp-damage), f'🔥 Burn dealt {damage} damage.'
    return hp, ''
def status_label(status): return STATUS_NAMES.get(status, status.replace('-',' ') if status else 'healthy').title()

def battle_commentary(attacker, move, damage=0, effectiveness=1, critical=False, status=''):
    """Generate varied play-by-play commentary for battle actions."""
    pokemon_name = attacker if isinstance(attacker, str) else display_name(attacker)
    move_name = move.get('name', 'move').replace('-', ' ').title()
    openings = [
        f'🎙️ **Commentator:** {pokemon_name} springs into action with **{move_name}**!',
        f'🎙️ **Commentator:** What a moment! {pokemon_name} goes for **{move_name}**!',
        f'🎙️ **Commentator:** The crowd reacts as {pokemon_name} unleashes **{move_name}**!',
        f'🎙️ **Commentator:** {pokemon_name} finds an opening and fires off **{move_name}**!',
    ]
    line = random.choice(openings)
    if damage <= 0:
        line += ' The attack fails to connect!'
    elif critical:
        line += f' A clean hit for **{damage} damage**—that one really lands!'
    elif effectiveness > 1:
        line += f' It finds a weakness and deals **{damage} damage**! Super effective!'
    elif effectiveness == 0:
        line += ' But it has no effect!'
    elif effectiveness < 1:
        line += f' The hit deals **{damage} damage**, but the target holds firm.'
    else:
        line += f' The hit connects for **{damage} damage**!'
    if status:
        status_lines = {
            'poison': 'Poison takes hold—this could change the whole battle!',
            'badly-poisoned': 'Severe poison sets in! Every turn matters now!',
            'burn': 'A burn catches! The pressure is on!',
            'paralysis': 'The target is paralyzed—its next move may be in trouble!',
            'sleep': 'The target falls asleep! What a swing in momentum!',
            'freeze': 'The target is frozen solid! A huge opening appears!',
        }
        line += ' ' + status_lines.get(status, f'{status_label(status)} takes effect!')
    return line


class TimedView(discord.ui.View):
    """A view that removes expired buttons and replaces its message with a timeout notice."""
    def __init__(self, *, timeout=60, timeout_text='⏰ This interaction timed out.'):
        super().__init__(timeout=timeout)
        self.timeout_text = timeout_text
        self.message = None

    async def on_timeout(self):
        # Views with timeout=None never expire. For timed views, avoid editing a message
        # when no timeout notice was configured (used by persistent confirmations/battles).
        if not self.timeout_text:
            return
        msg = getattr(self, 'message', None)
        if msg is not None:
            try:
                await msg.edit(content=self.timeout_text, embed=None, view=None, attachments=[])
            except Exception:
                try:
                    await msg.edit(content=self.timeout_text, embed=None, view=None)
                except Exception:
                    pass


class NPCMovePicker(TimedView):
    def __init__(self, battle):
        super().__init__(timeout=None, timeout_text='')
        self.battle=battle; self.uid=battle.uid
        for i,m in enumerate(battle.moves):
            button=discord.ui.Button(label=(('⚡ ' if m.get('_battle_kind')=='fast' else '🔋 ') + m['name'].replace('-', ' ').title())[:80],style=discord.ButtonStyle.primary, disabled=((m.get('_battle_kind')=='charged' and getattr(self.battle,'energy',0)<2) or (m.get('_battle_kind')=='fast' and getattr(self.battle,'energy',0)>=2)))
            async def pick(inter,index=i):
                if inter.user.id!=self.uid:return await inter.response.send_message('These moves are private to the trainer who opened this menu.',ephemeral=True)
                if self.battle.busy:return await inter.response.send_message('Wait for the current turn to finish.',ephemeral=True)
                self.battle.busy=True
                try:
                    await inter.response.edit_message(content=f'✅ Selected **{self.battle.moves[index]["name"].replace("-", " ").title()}**.',view=None)
                    await self.battle.turn(inter,self.battle.moves[index])
                except Exception as e:
                    if not inter.response.is_done():await inter.response.send_message(f'Battle error: `{e}`',ephemeral=True)
                finally:self.battle.busy=False
            button.callback=pick;self.add_item(button)


class EliteChargedMoveView(TimedView):
    """Dropdown to choose an Elite Charged TM move; only the owner can use it."""
    def __init__(self, owner_id, pokemon_id, item_key, pokemon_name, pool):
        super().__init__(timeout=180, timeout_text='⏰ This move-selection menu expired. Run !giveitem again.')
        self.owner_id=owner_id; self.pokemon_id=pokemon_id; self.item_key=item_key; self.pokemon_name=pokemon_name
        options=[discord.SelectOption(label=m['name'].replace('-', ' ').title()[:100], value=m['name']) for m in pool[:25]]
        self.select=discord.ui.Select(placeholder='Choose a Charged Move', min_values=1, max_values=1, options=options)
        self.select.callback=self.choose
        self.add_item(self.select)
    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message('This move selection belongs to another trainer.', ephemeral=True); return False
        return True
    async def choose(self, interaction):
        selected=self.select.values[0]
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT amount FROM inventory WHERE user_id=? AND item=?',(self.owner_id,self.item_key)).fetchone()
            owned=c.execute('SELECT 1 FROM pokemon WHERE instance_id=? AND user_id=?',(self.pokemon_id,self.owner_id)).fetchone()
            if not row or row[0]<1 or not owned:
                c.rollback()
                return await interaction.response.edit_message(content='❌ The Pokémon or Elite Charged TM is no longer available. Nothing changed.', view=None)
            c.execute('UPDATE pokemon SET charged_move=? WHERE instance_id=? AND user_id=?',(selected,self.pokemon_id,self.owner_id))
            c.execute('UPDATE inventory SET amount=amount-1 WHERE user_id=? AND item=?',(self.owner_id,self.item_key))
            c.execute('DELETE FROM inventory WHERE user_id=? AND item=? AND amount<=0',(self.owner_id,self.item_key))
        await interaction.response.edit_message(content=f'✅ **{self.pokemon_name.title()}** learned **{selected.replace("-", " ").title()}** using Elite Charged TM.', view=None)


class PartySwitchPicker(TimedView):
    """Private dropdown for choosing a living teammate during a boss/raid battle."""
    def __init__(self, battle):
        super().__init__(timeout=120, timeout_text='⏰ Switch menu expired. Click Switch Pokémon again.')
        self.battle=battle; self.uid=battle.uid
        available=[r for r in battle.party if r[0]!=battle.row[0] and r[8]>0]
        options=[discord.SelectOption(label=f'{r[3].title()} Lv.{r[4]}', description=f'HP {r[8]}/{r[9]}', value=str(i)) for i,r in enumerate(battle.party) if r in available][:25]
        if options:
            select=discord.ui.Select(placeholder='Select a Pokémon to switch in',min_values=1,max_values=1,options=options)
            select.callback=self.choose
            self.add_item(select)
    async def choose(self, interaction):
        if interaction.user.id!=self.uid:
            return await interaction.response.send_message('This switch menu belongs to another trainer.',ephemeral=True)
        if self.battle.busy:
            return await interaction.response.send_message('Wait for the turn to finish.',ephemeral=True)
        index=int(interaction.data['values'][0])
        target=self.battle.party[index]
        if target[8]<=0 or target[0]==self.battle.row[0]:
            return await interaction.response.send_message('That Pokémon cannot be switched in. Choose a healthy teammate.',ephemeral=True)
        await interaction.response.defer()
        await self.battle.perform_switch(target)
        try: await interaction.edit_original_response(content=f'✅ Switched to **{target[3].title()}**.',view=None)
        except Exception: pass


class NPCBattleView(TimedView):
    def __init__(self,uid,row,enemy,boss=False,boss_shiny=False,active_boss_battles=None,raid=False):
        super().__init__(timeout=None, timeout_text=''); self.raid=raid; self.uid=uid; self.row=row; self.enemy=enemy; self.player_hp=row[8]; self.enemy_base_hp=max_hp(enemy,enemy['_level']); self.enemy_max_hp=self.enemy_base_hp*(4 if raid else 1); self.enemy_hp=self.enemy_max_hp; self.player_status=(row[11] or '') if len(row)>11 else ''; self.enemy_status=''; self.moves=[]; self.choice_lock=''; self.busy=False; self.boss=boss; self.boss_shiny=boss_shiny; self.party=[]; self.energy_by_pokemon={row[0]:0}; self.active_boss_battles=active_boss_battles
    async def on_timeout(self):
        if self.boss and self.active_boss_battles is not None:
            self.active_boss_battles.discard(self.uid)
        await super().on_timeout()
    async def build(self):
        # Rebuild controls every turn so unavailable moves are disabled immediately.
        self.clear_items()
        self.moves=await saved_battle_moves(self.row)
        self.energy=getattr(self,'energy',0)
        if self.boss or self.raid:
            party_table='raid_party' if self.raid else 'boss_party'
            with db() as c: rows=c.execute(f'SELECT p.* FROM {party_table} bp JOIN pokemon p ON p.instance_id=bp.instance_id WHERE bp.user_id=? ORDER BY bp.slot',(self.uid,)).fetchall()
            self.party=list(rows)
            for party_row in self.party: self.energy_by_pokemon.setdefault(party_row[0],0)
        # Put the actual available moves directly on the battle message.
        if self.player_hp > 0:
            for i,m in enumerate(self.moves):
                kind=m.get('_battle_kind','fast')
                locked=(kind=='charged' and self.energy<2) or (kind=='fast' and self.energy>=2)
                prefix='⚡ ' if kind=='fast' else '🔋 '
                button=discord.ui.Button(label=(prefix+m['name'].replace('-', ' ').title())[:80],style=discord.ButtonStyle.primary,disabled=locked,row=0 if i<5 else 1)
                async def pick(inter,index=i):
                    if inter.user.id!=self.uid:return await inter.response.send_message('This is not your battle.',ephemeral=True)
                    if self.busy:return await inter.response.send_message('Wait for the turn to finish.',ephemeral=True)
                    if self.player_hp<=0:return await inter.response.send_message('💥 This Pokémon fainted. Switch to a healthy teammate.',ephemeral=True)
                    move=self.moves[index]
                    if (move.get('_battle_kind')=='charged' and self.energy<2) or (move.get('_battle_kind')=='fast' and self.energy>=2):
                        return await inter.response.send_message('That move is not available yet.',ephemeral=True)
                    self.busy=True
                    try:
                        # Acknowledge immediately to keep turns responsive and avoid Discord interaction timeouts.
                        await inter.response.defer()
                        await self.turn(inter,move)
                    except Exception as e:
                        if not inter.response.is_done(): await inter.response.send_message(f'Battle error: `{e}`',ephemeral=True)
                        else: print(f'Battle turn failed: {e!r}')
                    finally:self.busy=False
                button.callback=pick; self.add_item(button)
        if self.boss or self.raid:
            healthy=[r for r in self.party if r[0]!=self.row[0] and r[8]>0]
            if healthy:
                switch=discord.ui.Button(label='Switch Pokémon',style=discord.ButtonStyle.secondary,row=2 if self.player_hp>0 else 0,emoji='🔄')
                async def open_switch(inter):
                    if inter.user.id!=self.uid:return await inter.response.send_message('This is not your battle.',ephemeral=True)
                    if self.busy:return await inter.response.send_message('Wait for the turn to finish.',ephemeral=True)
                    await inter.response.send_message('Select the healthy Pokémon to switch in:',view=PartySwitchPicker(self),ephemeral=True)
                switch.callback=open_switch; self.add_item(switch)
    def switch_cb(self,i):
        async def f(inter):
            if inter.user.id!=self.uid:return await inter.response.send_message('This is not your battle.',ephemeral=True)
            if self.busy:return await inter.response.send_message('Wait for the turn to finish.',ephemeral=True)
            await self.perform_switch(self.party[i], interaction=inter)
        return f
    async def perform_switch(self,target,interaction=None):
        if target[0]==self.row[0] or target[8]<=0:
            if interaction and not interaction.response.is_done():
                return await interaction.response.send_message('Choose a different, healthy teammate.',ephemeral=True)
            return
        with db() as c:c.execute('UPDATE pokemon SET hp=?,status_condition=? WHERE instance_id=?',(self.player_hp,self.player_status,self.row[0]))
        self.energy_by_pokemon[self.row[0]]=self.energy
        self.row=target; self.player_hp=target[8]; self.player_status=(target[11] or '') if len(target)>11 else ''
        self.energy=self.energy_by_pokemon.get(target[0],0); self.moves=await saved_battle_moves(target)
        for item in list(self.children): self.remove_item(item)
        await self.build()
        em=discord.Embed(title=('🌟 Raid Battle — Pokémon switched!' if self.raid else '🔥 Legendary 3v1 — Pokémon switched!'),description=f'**Active:** {target[3].title()} Lv.{target[4]}\nHP {hp_bar(self.player_hp,target[9])}\nStatus: **{status_label(self.player_status)}**\n**Boss:** {display_name(self.enemy)} Lv.{self.enemy["_level"]}\nHP {hp_bar(self.enemy_hp,self.enemy_max_hp)}\nStatus: **{status_label(self.enemy_status)}**\n🎙️ **Commentator:** {target[3].title()} enters the arena. Use the move buttons below, or Switch Pokémon to select a healthy teammate.')
        if sprite(self.enemy,shiny=self.boss_shiny):em.set_image(url=sprite(self.enemy,shiny=self.boss_shiny))
        if self.message is not None: await self.message.edit(embed=em,view=self)
        if interaction is not None and not interaction.response.is_done(): await interaction.response.send_message(f'✅ Switched to **{target[3].title()}**.',ephemeral=True)
    def cb(self,i):
        async def f(inter):
            if inter.user.id!=self.uid:return await inter.response.send_message('This is not your battle.',ephemeral=True)
            if self.busy:return await inter.response.send_message('Wait for the turn.',ephemeral=True)
            if self.player_hp<=0:return await inter.response.send_message('💥 This Pokémon has fainted and cannot move. Switch to a teammate.',ephemeral=True)
            self.busy=True
            try: await self.turn(inter,self.moves[i])
            except Exception as e:
                if not inter.response.is_done(): await inter.response.send_message(f'Battle error: `{e}`',ephemeral=True)
            finally:self.busy=False
        return f
    async def update_battle(self, inter, **kwargs):
        if kwargs.get('view', 'keep') is self and self.message is not None:
            await self.build()
        if self.message is not None:
            content=kwargs.get('content')
            view=kwargs.get('view', self)
            if content is not None and view is self:
                e=discord.Embed(title=('🌟 Shiny Raid Battle' if self.raid else ('🔥 Legendary Boss Battle' if self.boss else '⚔️ Pokémon Battle Arena')), description=content, color=discord.Color.dark_red() if self.boss else discord.Color.red())
                own=await pokemon_data(self.row[2])
                if sprite(own,shiny=bool(self.row[6])):e.set_thumbnail(url=sprite(own,shiny=bool(self.row[6])))
                if sprite(self.enemy,shiny=self.boss_shiny):e.set_image(url=sprite(self.enemy,shiny=self.boss_shiny))
                await self.message.edit(content=None, embed=e, view=self)
            elif content is not None:
                await self.message.edit(content=content, embed=None, view=None)
            else:
                await self.message.edit(**kwargs)
        if kwargs.get('view', 'keep') is None:
            ACTIVE_VIEWS.pop(self.uid, None)
            if self.boss and self.active_boss_battles is not None:self.active_boss_battles.discard(self.uid)

    async def turn(self,inter,move):
        p=await pokemon_data(self.row[2]); msg=''
        held=(self.row[10] or '') if len(self.row)>10 else ''
        move_name=move.get('name','').lower()
        battle_kind=move.get('_battle_kind','fast')
        if battle_kind=='charged' and self.energy<2: return await self.update_battle(inter,content='🔋 Your Charged Move is not ready. Use two Fast Moves first.')
        if battle_kind=='fast' and self.energy>=2: return await self.update_battle(inter,content='⚡ You have used two Fast Moves. Your Fast Move is locked until you use your Charged Move!')
        if battle_kind=='charged': self.energy=0
        else: self.energy=min(2,self.energy+1)
        self.energy_by_pokemon[self.row[0]]=self.energy
        healing_moves={'recover','roost','moonlight','synthesis','soft-boiled','slack-off','shore-up'}
        if move_name in healing_moves:
            before=self.player_hp
            heal=max(1,int(self.row[9]*0.5))
            self.player_hp=min(self.row[9],self.player_hp+heal)
            restored=self.player_hp-before
            msg=f'💚 **{self.row[3].title()}** used **{move_name.replace("-"," " ).title()}** and recovered **{restored} HP**!\nYour HP: {hp_bar(self.player_hp,self.row[9])}\n🎙️ **Commentator:** A timely recovery! {self.row[3].title()} regains its strength.'
        elif random.randint(1,100)>(move.get('accuracy') or 100): msg=f'💨 **{move["name"].title()}** missed!\n{battle_commentary(self.row[3], move, 0)}'
        else:
            dmg,eff,crit=calc_damage(p,self.enemy,move,self.row[4])
            dmg=int(dmg*held_damage_multiplier(held,move,eff))
            if self.raid: dmg=max(1,int(dmg*0.65))  # Raid bosses have raid-scale durability.
            # Simple species abilities with direct battle impact; Pokédex displays the full ability list.
            ability_names={a['ability']['name'] for a in p.get('abilities',[])}
            if 'adaptability' in ability_names and move.get('type',{}).get('name') in [t['type']['name'] for t in p['types']]: dmg=int(dmg*1.15)
            if 'huge-power' in ability_names or 'pure-power' in ability_names: dmg=int(dmg*1.15)
            enemyheld=self.enemy.get('_held_item','')
            if enemyheld=='assault-vest':dmg=int(dmg*.8)
            if enemyheld=='focus-sash' and self.enemy_hp>=self.enemy_max_hp and dmg>=self.enemy_hp: dmg=max(0,self.enemy_hp-1)
            self.enemy_hp=max(0,self.enemy_hp-dmg)
            status_msg=''
            inflicted=status_from_move(move)
            if inflicted and enemyheld!='safety-goggles' and not self.enemy_status:
                self.enemy_status=inflicted; status_msg=f'\n🧪 {display_name(self.enemy)} is now **{status_label(inflicted)}**!'
            if held=='shell-bell' and dmg>0:self.player_hp=min(self.row[9],self.player_hp+max(1,dmg//8))
            if held=='life-orb' and dmg>0:self.player_hp=max(0,self.player_hp-max(1,self.row[9]//10))
            msg=f'⚔️ **{move["name"].replace("-"," ").title()}** dealt **{dmg}** damage!'+status_msg
            if crit:msg+=' 💥 Critical hit!'
            if eff>1:msg+=' Super effective!'
            elif 0<eff<1:msg+=' Not very effective...'
            elif eff==0:msg+=' No effect!'
            msg += '\n' + battle_commentary(self.row[3], move, dmg, eff, crit, inflicted if inflicted and not status_msg == '' else '')
        if self.enemy_hp<=0:
            # Commit the active Pokémon's final HP/status on every completed battle,
            # regardless of whether the encounter was a regular, legendary, or raid battle.
            with db() as c:
                c.execute('UPDATE pokemon SET hp=?,status_condition=? WHERE instance_id=? AND user_id=?',
                          (max(0, min(self.row[9], self.player_hp)), self.player_status or '', self.row[0], self.uid))
            r=random.randint(80,220);x=random.randint(40,90);add_progress(self.uid,r,x)
            if self.raid:
                boss_level=int(self.enemy['_level']); caught_level=max(1,min(300,boss_level-75)); mh=max_hp(self.enemy,caught_level)
                with db() as c:
                    cur=c.execute('INSERT INTO pokemon(user_id,dex_id,name,level,shiny,hp,max_hp) VALUES(?,?,?,?,?,?,?)',(self.uid,self.enemy['id'],self.enemy['name'],caught_level,1,mh,mh)); iid=cur.lastrowid; assign_box_id(c,self.uid,iid)
                    c.execute("INSERT INTO inventory(user_id,item,amount) VALUES(?, 'rare-candy', 50) ON CONFLICT(user_id,item) DO UPDATE SET amount=amount+50",(self.uid,))
                    c.execute('DELETE FROM raid_encounters WHERE user_id=?',(self.uid,)); c.execute('DELETE FROM raid_party WHERE user_id=?',(self.uid,))
                if self.active_boss_battles is not None:self.active_boss_battles.discard(self.uid)
                return await self.update_battle(inter,content=f'🏆 **RAID VICTORY!**\n{msg}\n\n✨ Caught shiny **{display_name(self.enemy)}** Lv.{caught_level} — ID `{get_box_id(c,self.uid,iid)}` (raid boss was Lv.{boss_level})!\n🍬 **+50 Rare Candies** added to your inventory.\nUse `!candy {get_box_id(c,self.uid,iid)} <amount>` to level it or another Pokémon (max Lv. 300).',view=None)
            if self.boss:
                mh=self.enemy_max_hp
                with db() as c:
                    cur=c.execute('INSERT INTO pokemon(user_id,dex_id,name,level,shiny,hp,max_hp) VALUES(?,?,?,?,?,?,?)',(self.uid,self.enemy['id'],self.enemy['name'],self.enemy['_level'],int(self.boss_shiny),mh,mh)); iid=cur.lastrowid; assign_box_id(c,self.uid,iid)
                    if not c.execute('SELECT 1 FROM team WHERE user_id=?',(self.uid,)).fetchone(): c.execute('INSERT OR REPLACE INTO team(user_id,slot,instance_id) VALUES(?,?,?)',(self.uid,1,iid))
                    c.execute('DELETE FROM boss_encounters WHERE user_id=?',(self.uid,))
                    c.execute('DELETE FROM boss_party WHERE user_id=?',(self.uid,))
                if self.active_boss_battles is not None:self.active_boss_battles.discard(self.uid)
                jackpot=1_000_000 if self.boss_shiny else 0
                if jackpot: add_progress(self.uid,coins=jackpot)
                jackpot_text=f'\n\n🎰 JACKPOT! <@{self.uid}> won a shiny legendary boss! **1,000,000 {get_vantacoin_emoji()} VantaCoins (1 million)** have been credited to your balance! 💰' if jackpot else ''
                return await self.update_battle(inter, content=f'🏆 <@{self.uid}> won the legendary fight!\n{msg}\n\n🎉 You obtained {"✨ SHINY " if self.boss_shiny else ""}**{display_name(self.enemy)}** Lv. {self.enemy["_level"]} — ID `{get_box_id(c,self.uid,iid)}`!\n💰 +{r} {get_vantacoin_emoji()} VantaCoins • ⭐ +{x} XP{jackpot_text}',view=None)
            return await self.update_battle(inter, content=f'🏆 **Victory!**\n{msg}\n\nYour Pokémon: {hp_bar(self.player_hp,self.row[9])}\nOpponent: {hp_bar(self.enemy_hp,self.enemy_max_hp)}\n\n💰 +{r} {get_vantacoin_emoji()} VantaCoins • ⭐ +{x} XP',view=None)
        self.enemy_hp, tickmsg=status_tick(self.enemy_status,self.enemy_hp,self.enemy_max_hp)
        if tickmsg: msg+='\n'+tickmsg
        if self.enemy_hp<=0:
            r=random.randint(80,220);x=random.randint(40,90);add_progress(self.uid,r,x)
            if self.raid:
                boss_level=int(self.enemy['_level']); caught_level=max(1,min(300,boss_level-75)); mh=max_hp(self.enemy,caught_level)
                with db() as c:
                    cur=c.execute('INSERT INTO pokemon(user_id,dex_id,name,level,shiny,hp,max_hp) VALUES(?,?,?,?,?,?,?)',(self.uid,self.enemy['id'],self.enemy['name'],caught_level,1,mh,mh)); iid=cur.lastrowid; assign_box_id(c,self.uid,iid)
                    c.execute("INSERT INTO inventory(user_id,item,amount) VALUES(?, 'rare-candy', 50) ON CONFLICT(user_id,item) DO UPDATE SET amount=amount+50",(self.uid,))
                    c.execute('DELETE FROM raid_encounters WHERE user_id=?',(self.uid,)); c.execute('DELETE FROM raid_party WHERE user_id=?',(self.uid,))
                if self.active_boss_battles is not None:self.active_boss_battles.discard(self.uid)
                return await self.update_battle(inter,content=f'🏆 **RAID VICTORY!**\n{msg}\n\n✨ Caught shiny **{display_name(self.enemy)}** Lv.{caught_level} — ID `{get_box_id(c,self.uid,iid)}`!\n🍬 **+50 Rare Candies** added to your inventory.',view=None)
            if self.boss and self.active_boss_battles is not None:self.active_boss_battles.discard(self.uid)
            return await self.update_battle(inter, content=f'🏆 **Victory!**\n{msg}\n\nYour Pokémon: {hp_bar(self.player_hp,self.row[9])}\nOpponent: {hp_bar(self.enemy_hp,self.enemy_max_hp)}\n\n💰 +{r} {get_vantacoin_emoji()} VantaCoins • ⭐ +{x} XP',view=None)
        em=random.choice(await move_pool(self.enemy['name'],True)); em['power']=max(10,int((em.get('power') or 40)*(0.95 if self.raid else 0.55))); dmg,eff,crit=calc_damage(self.enemy,p,em,self.enemy['_level'])
        if self.raid: dmg=max(1,int(dmg*1.35))  # Raid boss strikes are substantially stronger.
        dmg=max(1,int(dmg*held_incoming_multiplier(held)))
        if held=='focus-sash' and self.player_hp>=self.row[9] and dmg>=self.player_hp: dmg=max(0,self.player_hp-1)
        if held=='rocky-helmet': self.enemy_hp=max(0,self.enemy_hp-max(1,int(dmg*.08)))
        self.player_hp=max(0,self.player_hp-dmg)
        inflicted=status_from_move(em)
        if inflicted and not held_prevents_status(held) and not self.player_status:
            self.player_status=inflicted; msg+=f'\n🧪 **{self.row[3].title()}** is now **{status_label(inflicted)}**!'
        self.player_hp,tickmsg=status_tick(self.player_status,self.player_hp,self.row[9])
        if tickmsg: msg+='\n'+tickmsg
        if held=='leftovers' and self.player_hp>0:self.player_hp=min(self.row[9],self.player_hp+max(1,self.row[9]//16))
        msg+=f'\n🔥 **{display_name(self.enemy)}** used **{display_name(em)}** for **{dmg}** damage.'
        msg+='\n'+battle_commentary(self.enemy, em, dmg, eff, crit, inflicted if inflicted and not self.player_status == '' else '')
        if self.player_hp<=0:
            # Persist final HP and any status effect on defeat as well as victory.
            with db() as c:
                c.execute('UPDATE pokemon SET hp=0,status_condition=? WHERE instance_id=? AND user_id=?',
                          (self.player_status or '', self.row[0], self.uid))
            if (self.boss or self.raid) and any(r[0]!=self.row[0] and r[8]>0 for r in self.party):
                for item in list(self.children): self.remove_item(item)
                await self.build()
                return await self.update_battle(inter, content=f'💥 **{self.row[3].title()} fainted!**\n{msg}\nUse **Switch Pokémon** and select a healthy teammate. Moves are unavailable until you switch.',view=self)
            if self.raid:
                with db() as c:
                    c.execute('DELETE FROM raid_encounters WHERE user_id=?',(self.uid,)); c.execute('DELETE FROM raid_party WHERE user_id=?',(self.uid,))
                if self.active_boss_battles is not None:self.active_boss_battles.discard(self.uid)
                return await self.update_battle(inter,content=f'💥 **Raid failed!**\n{msg}\n\nThe raid has ended. Your Raid Pass was spent, but no rewards were granted.',view=None)
            if self.boss:
                # A lost boss challenge is consumed: return to regular hunts, no retry.
                with db() as c:
                    c.execute('DELETE FROM boss_encounters WHERE user_id=?',(self.uid,))
                    c.execute('DELETE FROM boss_party WHERE user_id=?',(self.uid,))
                if self.active_boss_battles is not None:self.active_boss_battles.discard(self.uid)
                return await self.update_battle(inter, content=f'💥 **Boss challenge lost!**\n{msg}\n\nThe legendary escaped. You are back to normal `!hunt` encounters. Complete 10 more hunts to trigger another boss challenge.',view=None)
            return await self.update_battle(inter, content=f'💥 **Defeat!**\n{msg}\n\nYour Pokémon: {hp_bar(self.player_hp,self.row[9])}\nOpponent: {hp_bar(self.enemy_hp,self.enemy_max_hp)}\n\nUse `!useitem Potion <pokemon_id>` to heal HP, or a status-curing berry if needed.',view=None)
        with db() as c:c.execute('UPDATE pokemon SET hp=?,status_condition=? WHERE instance_id=?',(self.player_hp,self.player_status,self.row[0]))
        await self.update_battle(inter, content=f'⚔️ **NPC Battle**\n{msg}\n\nYour Pokémon: {hp_bar(self.player_hp,self.row[9])}\nStatus: **{status_label(self.player_status)}**\n👾 Enemy: {hp_bar(self.enemy_hp,self.enemy_max_hp)}\nStatus: **{status_label(self.enemy_status)}**',view=self)

class PvPMovePicker(TimedView):
    """Ephemeral move menu: only the trainer who opened it can see/use these moves."""
    def __init__(self, battle, uid):
        super().__init__(timeout=None, timeout_text='')
        self.battle=battle; self.uid=uid
        for i,m in enumerate(battle.moves[uid]):
            button=discord.ui.Button(label=(('⚡ ' if m.get('_battle_kind')=='fast' else '🔋 ') + m['name'].replace('-', ' ').title())[:80], style=discord.ButtonStyle.primary, disabled=((m.get('_battle_kind')=='charged' and self.battle.energy[self.uid]<2) or (m.get('_battle_kind')=='fast' and self.battle.energy[self.uid]>=2)))
            async def pick(interaction, index=i):
                if interaction.user.id != self.uid:
                    return await interaction.response.send_message('These moves are private to the trainer who opened this menu.', ephemeral=True)
                if self.battle.over:
                    return await interaction.response.edit_message(content='This battle is already over.', view=None)
                row=self.battle.ra if self.uid==self.battle.a else self.battle.rb
                if self.battle.hp[self.uid]<=0:
                    return await interaction.response.edit_message(content='💥 Your Pokémon has fainted and cannot use another move.', view=None)
                held=(row[10] or '') if len(row)>10 else ''
                move_name=self.battle.moves[self.uid][index].get('name','').lower()
                if self.battle.moves[self.uid][index].get('_battle_kind')=='charged' and self.battle.energy[self.uid]<2:
                    return await interaction.response.send_message('🔋 Use two Fast Moves to charge this attack.',ephemeral=True)
                move_label=self.battle.moves[self.uid][index]["name"].replace('-', ' ').title()
                # Acknowledge immediately so later battle/API work cannot trigger an interaction timeout.
                await interaction.response.defer()
                try:
                    await interaction.edit_original_response(content=f'✅ You selected **{move_label}**.', view=None)
                except Exception as exc:
                    print(f'PvP picker response update failed for {self.uid}: {exc!r}')
                try:
                    await self.battle.submit_move(self.uid, index)
                except Exception as exc:
                    print(f'PvP move resolution failed: {exc!r}')
                    self.battle.last_text='⚠️ A temporary battle update error occurred. Please try choosing a move again.'
                    try:
                        if self.battle.message:
                            await self.battle.message.edit(embed=await self.battle.make_embed(), view=self.battle.view())
                    except Exception as update_exc:
                        print(f'PvP recovery update failed: {update_exc!r}')
            button.callback=pick; self.add_item(button)

class PvPBattle:
    def __init__(self,a,b,ra,rb): self.a=a;self.b=b;self.ra=ra;self.rb=rb;self.hp={a:ra[8],b:rb[8]};self.status={a:(ra[11] or ''),b:(rb[11] or '')};self.moves={};self.energy={a:0,b:0};self.picks={};self.choice_locks={};self.message=None;self.lock=asyncio.Lock();self.over=False;self.last_text='🎙️ **Commentator:** The trainers step into the arena—this battle is underway!'
    async def setup(self):
        for uid,row in [(self.a,self.ra),(self.b,self.rb)]:self.moves[uid]=await saved_battle_moves(row)
    async def render(self):
        lines=[f'⚔️ **Pokémon Trainer Battle** <@{self.a}> vs <@{self.b}>','',f'🔴 **{self.ra[3].title()}** Lv.{self.ra[4]} — {hp_bar(self.hp[self.a],self.ra[9])}\nStatus: **{status_label(self.status[self.a])}**',f'🔵 **{self.rb[3].title()}** Lv.{self.rb[4]} — {hp_bar(self.hp[self.b],self.rb[9])}\nStatus: **{status_label(self.status[self.b])}**','',f'🎮 Moves selected: **{len(self.picks)}/2**',self.last_text,'Choose Move opens your private move buttons so the other trainer cannot see your selection.']
        return '\n'.join(lines)
    async def make_embed(self):
        e=discord.Embed(title='⚔️ Pokémon Battle Arena', description=await self.render(), color=discord.Color.red())
        da=await pokemon_data(self.ra[2]); dbb=await pokemon_data(self.rb[2])
        if sprite(da,shiny=bool(self.ra[6])): e.set_thumbnail(url=sprite(da,shiny=bool(self.ra[6])))
        if sprite(dbb,shiny=bool(self.rb[6])): e.set_image(url=sprite(dbb,shiny=bool(self.rb[6])))
        e.set_footer(text='Left sprite: challenger • Main sprite: opponent')
        return e
    def view(self):
        v=TimedView(timeout=None, timeout_text='')
        button=discord.ui.Button(label='Choose Move',style=discord.ButtonStyle.primary,disabled=(self.hp[self.a]<=0 or self.hp[self.b]<=0))
        async def open_picker(interaction):
            trainer=interaction.user.id
            if trainer not in (self.a,self.b):
                return await interaction.response.send_message('Only the two trainers can choose a move.', ephemeral=True)
            if self.over:
                return await interaction.response.send_message('This battle is over.', ephemeral=True)
            if trainer in self.picks:
                return await interaction.response.send_message('You already chose a move this turn. Wait for the other trainer.', ephemeral=True)
            await interaction.response.send_message('Choose one of your Pokémon’s moves (only you can see this menu):', view=PvPMovePicker(self,trainer), ephemeral=True)
        button.callback=open_picker;v.add_item(button)
        return v
    async def submit_move(self,uid,index):
        async with self.lock:
            if self.over or uid in self.picks:return
            self.picks[uid]=index
            if len(self.picks)<2:
                self.last_text=f'<@{uid}> has locked in a move. Waiting for the other trainer…'
                try:
                    await self.message.edit(embed=await self.make_embed(),view=self.view())
                except Exception as exc:
                    print(f'PvP waiting-state update failed: {exc!r}')
                    await self.message.edit(content=await self.render(), embed=None, view=self.view())
                return
            await self.resolve()
    async def resolve(self):
        speeds={}
        for uid in (self.a,self.b):
            row=self.ra if uid==self.a else self.rb
            speeds[uid]=stats(await pokemon_data(row[2])).get('speed',0)*(1.5 if len(row)>10 and row[10]=='choice-scarf' else 1)
        order=sorted([self.a,self.b],key=lambda u:speeds[u],reverse=True)
        # Keep action messages visible in the public battle log, but never reveal a move before both trainers have selected.
        log=[]
        for uid in order:
            if self.hp[uid]<=0:continue
            opp=self.b if uid==self.a else self.a; row=self.ra if uid==self.a else self.rb; orow=self.rb if uid==self.a else self.ra
            attacker=await pokemon_data(row[2]); defender=await pokemon_data(orow[2]); move=self.moves[uid][self.picks[uid]]
            if move.get('_battle_kind')=='charged':
                if self.energy[uid] < 2:
                    self.picks = {}
                    self.last_text = '🔋 Charged Move is not ready; use two Fast Moves first.'
                    await self.message.edit(embed=await self.make_embed(), view=self.view())
                    return
                self.energy[uid]=0
            else:
                if self.energy[uid] >= 2:
                    self.picks = {}
                    self.last_text = '⚡ Two Fast Moves used! The Fast Move is locked until you use your Charged Move.'
                    await self.message.edit(embed=await self.make_embed(), view=self.view())
                    return
                self.energy[uid]=min(2,self.energy[uid]+1)
            move_name=move.get('name','').lower()
            healing_moves={'recover','roost','moonlight','synthesis','soft-boiled','slack-off','shore-up'}
            if move_name in healing_moves:
                before=self.hp[uid]; maximum=row[9]; self.hp[uid]=min(maximum,self.hp[uid]+max(1,int(maximum*0.5))); restored=self.hp[uid]-before
                log.append(f'💚 **{row[3].title()}** used **{move_name.replace("-"," " ).title()}** and recovered **{restored} HP**!\nHP: {hp_bar(self.hp[uid],maximum)}\n🎙️ **Commentator:** A timely recovery! {row[3].title()} regains its strength.')
                continue
            if random.randint(1,100)>(move.get('accuracy') or 100): log.append(f'💨 **{row[3].title()}** used **{move["name"].title()}**, but missed!\n{battle_commentary(row[3], move, 0)}');continue
            before_hp=self.hp[opp]
            held=(row[10] or '') if len(row)>10 else ''
            enemyheld=(orow[10] or '') if len(orow)>10 else ''
            dmg,eff,crit=calc_damage(attacker,defender,move,row[4]);dmg=int(dmg*held_damage_multiplier(held,move,eff))
            dmg=max(1,int(dmg*held_incoming_multiplier(enemyheld)))
            if enemyheld=='focus-sash' and self.hp[opp]>=orow[9] and dmg>=self.hp[opp]: dmg=max(0,self.hp[opp]-1)
            self.hp[opp]=max(0,self.hp[opp]-dmg)
            if held=='shell-bell' and dmg>0:self.hp[uid]=min(row[9],self.hp[uid]+max(1,dmg//8))
            if held=='life-orb' and dmg>0:self.hp[uid]=max(0,self.hp[uid]-max(1,row[9]//10))
            if enemyheld=='rocky-helmet' and dmg>0:self.hp[uid]=max(0,self.hp[uid]-max(1,int(dmg*.08)))
            if held=='leftovers' and self.hp[uid]>0:self.hp[uid]=min(row[9],self.hp[uid]+max(1,row[9]//16))
            inflicted=status_from_move(move)
            status_msg=''
            if inflicted and not held_prevents_status(enemyheld) and not self.status[opp]:
                self.status[opp]=inflicted
                status_msg=f' 🧪 {orow[3].title()} is now **{status_label(inflicted)}**!'
            extra=' 💥 Critical hit!' if crit else ''
            if eff>1:extra+=' It was super effective!'
            elif eff==0:extra+=' It had no effect!'
            elif eff<1:extra+=' It was not very effective.'
            log.append(f'⚔️ **{row[3].title()}** used **{move["name"].replace("-", " ").title()}** → **{dmg} damage**!{extra}{status_msg}\n{orow[3].title()} HP: {hp_bar(self.hp[opp],orow[9])} (−{before_hp-self.hp[opp]} HP)')
            log.append(battle_commentary(row[3], move, dmg, eff, crit, inflicted if inflicted and not status_msg == '' else ''))
            if self.hp[opp]<=0:break
        for uid in (self.a,self.b):
            self.hp[uid], tickmsg=status_tick(self.status[uid],self.hp[uid],(self.ra if uid==self.a else self.rb)[9])
            if tickmsg: log.append(f'<@{uid}>: {tickmsg}')
        self.picks={};winner=None
        if self.hp[self.a]<=0:winner=self.b
        elif self.hp[self.b]<=0:winner=self.a
        self.last_text='\n'.join(log)
        if winner:
            self.over=True;ACTIVE_VIEWS.pop(self.a,None);ACTIVE_VIEWS.pop(self.b,None);loser=self.b if winner==self.a else self.a;add_progress(winner,coins=250,xp=100);self.last_text+='\n\n'+f'🏆 <@{winner}> won the fight! +250 {get_vantacoin_emoji()} VantaCoins +100 XP'
            with db() as c:
                c.execute('UPDATE pokemon SET hp=?,status_condition=? WHERE instance_id=?',(self.hp[self.a],self.status[self.a],self.ra[0]));c.execute('UPDATE pokemon SET hp=?,status_condition=? WHERE instance_id=?',(self.hp[self.b],self.status[self.b],self.rb[0]))
            await self.message.edit(embed=await self.make_embed(),view=None)
        else:
            await self.message.edit(embed=await self.make_embed(),view=self.view())

stats_cache={}

class ShopView(TimedView):
    """Paged shop catalogue with globally hosted item artwork (no server emoji setup)."""
    ITEMS_PER_PAGE = 10

    def __init__(self, owner_id, category='all', guild=None):
        super().__init__(timeout=180, timeout_text='⏰ This menu timed out. Run the command again to reopen it.')
        self.owner_id = owner_id
        self.category = category
        self.guild = guild
        self.entries = [(pid, item) for pid, item in SHOP_ITEMS.items() if self.matches_category(item[0])]
        self.page = 0
        self.pages = max(1, (len(self.entries) + self.ITEMS_PER_PAGE - 1) // self.ITEMS_PER_PAGE)
        self.update_buttons()

    def matches_category(self, key):
        if self.category == 'berries':
            return 'berry' in key
        if self.category == 'potions':
            return key in {'potion', 'super-potion', 'hyper-potion', 'max-potion', 'full-restore'}
        if self.category == 'held':
            return 'berry' not in key and key not in {'potion', 'super-potion', 'hyper-potion', 'max-potion', 'full-restore'}
        return True

    def update_buttons(self):
        self.previous.disabled = self.page <= 0
        self.next.disabled = self.page >= self.pages - 1

    def make_embed(self):
        """Render one Discord embed containing up to ten shop items."""
        start = self.page * self.ITEMS_PER_PAGE
        current = self.entries[start:start + self.ITEMS_PER_PAGE]
        labels = {'all': 'All Items', 'berries': 'Berries', 'potions': 'Potions', 'held': 'Held Items'}
        embed = discord.Embed(
            title=f'🛒 Poké Mart — {labels.get(self.category, "All Items")}',
            color=discord.Color.orange()
        )
        if not current:
            embed.description = 'No items found in this category.'
        else:
            lines = []
            for pid, (key, label, cost, desc, shortform) in current:
                # Use the actual uploaded Discord custom emoji for this item.
                # ITEM_EMOJI is populated from item_emojis.json by !setupitememojis;
                # do not replace a missing custom mapping with a generic Unicode emoji.
                saved_item_emoji = SHOP_ITEM_EMOJI.get(key) or ITEM_EMOJI.get(key)
                emoji_prefix = f'{saved_item_emoji} ' if saved_item_emoji else '▫️ '
                lines.append(
                    f'{emoji_prefix}**{label}** — **{cost:,} {get_vantacoin_emoji()} VantaCoins**\n'
                    f'ID: `{pid}` • Shortform: `{shortform}`\n'
                    f'{desc}'
                )
            embed.description = '\n\n'.join(lines)[:4096]
        embed.set_footer(text=f'Page {self.page + 1}/{self.pages} • {len(self.entries)} items • Buy: !shop buy <item> [quantity]')
        return embed

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message('Only the player who opened this shop can change pages.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Previous', emoji='⬅️', style=discord.ButtonStyle.secondary)
    async def previous(self, interaction, button):
        self.page = max(0, self.page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label='Next', emoji='➡️', style=discord.ButtonStyle.primary)
    async def next(self, interaction, button):
        self.page = min(self.pages - 1, self.page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)


class InventoryView(TimedView):
    """Inventory pages show ten inventory/equipped entries at a time."""
    ITEMS_PER_PAGE = 10

    def __init__(self, owner_id, entries):
        super().__init__(timeout=180, timeout_text='⏰ This menu timed out. Run the command again to reopen it.')
        self.owner_id = owner_id
        self.entries = entries
        self.page = 0
        self.pages = max(1, (len(entries) + self.ITEMS_PER_PAGE - 1) // self.ITEMS_PER_PAGE)
        self.update_buttons()

    def update_buttons(self):
        self.previous.disabled = self.page <= 0
        self.next.disabled = self.page >= self.pages - 1

    def make_embed(self):
        embed = discord.Embed(title='🎒 Pokémon Inventory', color=discord.Color.green())
        start = self.page * self.ITEMS_PER_PAGE
        current = self.entries[start:start + self.ITEMS_PER_PAGE]
        if current:
            for label, detail in current:
                embed.add_field(name=label[:256], value=detail[:1024], inline=False)
        else:
            embed.description = 'Your inventory is empty. Visit `!shop` to buy items.'
        embed.set_footer(text=f'Page {self.page + 1}/{self.pages} • 10 entries per page')
        return embed

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message('Only the player who opened this inventory can change pages.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Previous', emoji='⬅️', style=discord.ButtonStyle.secondary)
    async def previous(self, interaction, button):
        self.page = max(0, self.page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label='Next', emoji='➡️', style=discord.ButtonStyle.primary)
    async def next(self, interaction, button):
        self.page = min(self.pages - 1, self.page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)


async def ensure_box_pokemon_emojis(guild, entries):
    """Ensure current-page Pokémon have tiny inline custom emojis when server slots allow."""
    if guild is None or not getattr(guild, 'me', None):
        return
    try:
        if not guild.me.guild_permissions.manage_emojis_and_stickers and not guild.me.guild_permissions.manage_emojis:
            return
    except Exception:
        return
    # One emoji per species + variant; only current page is attempted to conserve slots.
    for row in entries:
        try:
            dex_id = int(row[8])
            shiny = bool(row[3])
            emoji_name = f"poke_{'shiny_' if shiny else ''}{dex_id}"
            if discord.utils.get(guild.emojis, name=emoji_name):
                continue
            sprite_url = (f'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/shiny/{dex_id}.png' if shiny else f'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{dex_id}.png')
            async with aiohttp.ClientSession() as session:
                async with session.get(sprite_url, timeout=aiohttp.ClientTimeout(total=12)) as response:
                    if response.status != 200:
                        continue
                    image_bytes = await response.read()
            # Keep the image comfortably below Discord's emoji upload size limit.
            if len(image_bytes) > 256 * 1024:
                continue
            await guild.create_custom_emoji(name=emoji_name, image=image_bytes, reason='Inline Pokémon Box sprite')
            await asyncio.sleep(0.35)
        except Exception:
            # If slots/permissions/network prevent an upload, the box still works normally.
            continue

class BoxView(TimedView):
    """Paged Pokémon collection with ten Pokémon grouped into one embed per page."""
    ITEMS_PER_PAGE = 10
    def __init__(self, owner_id, entries, category='all', guild=None):
        super().__init__(timeout=180, timeout_text='⏰ This menu timed out. Run the command again to reopen it.')
        self.owner_id=owner_id; self.entries=entries; self.page=0; self.category=category; self.guild=guild
        self.pages=max(1, (len(entries)+self.ITEMS_PER_PAGE-1)//self.ITEMS_PER_PAGE)
        self.update_buttons()
    def update_buttons(self):
        self.previous.disabled=self.page<=0
        self.next.disabled=self.page>=self.pages-1
    def make_embed(self):
        labels={'all':'All Pokémon','hp':'Highest max HP first','status':'Pokémon with status conditions','legendary':'Legendary Pokémon','shiny':'Shiny Pokémon','mythical':'Mythical Pokémon','ultrabeast':'Ultra Beasts','damaged':'Pokémon below max HP','items':'Pokémon Holding Items','name':'Named Pokémon'}
        current=self.entries[self.page*self.ITEMS_PER_PAGE:(self.page+1)*self.ITEMS_PER_PAGE]
        embed=discord.Embed(title=f'📦 Pokémon Box — {labels.get(self.category, "All Pokémon")}', color=discord.Color.blurple())
        if not current:
            embed.description='No Pokémon found for this category. Try `!box` to see your full collection.'
        else:
            for row in current:
                iid,name,level,shiny,held=row[:5]
                display=name.replace('-', ' ').title()
                details=f'**ID:** `{iid}`  •  **Level:** {level}'
                if len(row)>7:
                    hp,maxhp,status=row[5],row[6],row[7]
                    if self.category in ('hp','damaged'): details+=f'\n**HP:** {hp}/{maxhp}'
                    if status: details+=f'\n🧪 **Status:** {status.replace("-", " ").title()}'
                if held:
                    details+=f'\n{item_emoji(held)} **Held item:** {ITEM_BY_KEY[held][2] if held in ITEM_BY_KEY else held.replace(chr(45), chr(32)).title()}'
                dex_id = row[8] if len(row)>8 else None
                # Keep the shiny sparkle before the Pokémon name, without a Pokémon emoji.
                shiny_marker = '✨ ' if shiny else ''
                field_name=f'{shiny_marker}{display}'.strip()
                embed.add_field(name=field_name[:256], value=details[:1024], inline=False)
        embed.set_footer(text=f'Pokémon Box — {labels.get(self.category, "All Pokémon")} • Page {self.page+1}/{self.pages} • {len(self.entries)} Pokémon')
        return embed
    async def interaction_check(self, interaction):
        if interaction.user.id!=self.owner_id:
            await interaction.response.send_message('Only the player who opened this box can change pages.',ephemeral=True); return False
        return True
    @discord.ui.button(label='Previous',emoji='⬅️',style=discord.ButtonStyle.secondary)
    async def previous(self,interaction,button):
        self.page=max(0,self.page-1); self.update_buttons(); current=self.entries[self.page*self.ITEMS_PER_PAGE:(self.page+1)*self.ITEMS_PER_PAGE]; await ensure_box_pokemon_emojis(self.guild,current); await interaction.response.edit_message(embed=self.make_embed(),view=self)
    @discord.ui.button(label='Next',emoji='➡️',style=discord.ButtonStyle.primary)
    async def next(self,interaction,button):
        self.page=min(self.pages-1,self.page+1); self.update_buttons(); current=self.entries[self.page*self.ITEMS_PER_PAGE:(self.page+1)*self.ITEMS_PER_PAGE]; await ensure_box_pokemon_emojis(self.guild,current); await interaction.response.edit_message(embed=self.make_embed(),view=self)


class DexView(TimedView):
    """Paginated Pokédex showing registered and missing species together."""
    ITEMS_PER_PAGE = 25
    def __init__(self, owner_id, entries, shiny, title, registered_count, total_count):
        super().__init__(timeout=180, timeout_text='⏰ Pokédex pages expired. Run the same `!dex` command again.')
        self.owner_id=owner_id
        self.entries=entries  # (dex_id, name, registered)
        self.shiny=shiny
        self.dex_title=title
        self.registered_count=registered_count
        self.total_count=total_count
        self.page=0
        self.pages=max(1,(len(entries)+self.ITEMS_PER_PAGE-1)//self.ITEMS_PER_PAGE)
        self.update_buttons()
    def update_buttons(self):
        self.previous.disabled=self.page<=0
        self.next.disabled=self.page>=self.pages-1
    def make_embed(self):
        current=self.entries[self.page*self.ITEMS_PER_PAGE:(self.page+1)*self.ITEMS_PER_PAGE]
        embed=discord.Embed(title=('✨ Shiny ' if self.shiny else '📘 ')+self.dex_title,
            color=discord.Color.gold() if self.shiny else discord.Color.blurple())
        embed.description=(f'**Registered:** {self.registered_count}/{self.total_count}  •  **Missing:** {self.total_count-self.registered_count}\n'
            f'**Entries — page {self.page+1}/{self.pages}**\n' +
            ('\n'.join(f"{'✅' if caught else '⬜'} `#{dex_id:04}` {name.replace('-', ' ').title()}" for dex_id,name,caught in current) if current else 'No species found for this category.'))
        embed.set_footer(text='✅ Registered • ⬜ Not registered • Normal and shiny entries are separate')
        return embed
    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message('Only the player who opened this Pokédex can change pages.', ephemeral=True)
            return False
        return True
    @discord.ui.button(label='Previous',emoji='⬅️',style=discord.ButtonStyle.secondary)
    async def previous(self,interaction,button):
        self.page=max(0,self.page-1); self.update_buttons(); await interaction.response.edit_message(embed=self.make_embed(),view=self)
    @discord.ui.button(label='Next',emoji='➡️',style=discord.ButtonStyle.primary)
    async def next(self,interaction,button):
        self.page=min(self.pages-1,self.page+1); self.update_buttons(); await interaction.response.edit_message(embed=self.make_embed(),view=self)


class Game(commands.Cog):
    def __init__(self,bot):self.bot=bot;self.challenges={};self.coin_bets={};self.active_boss_battles=set()

    async def cog_check(self, ctx):
        """Only hunt, legendary battle, and raid battle exclude one another; all other commands stay usable."""
        uid = ctx.author.id
        name = ctx.command.qualified_name.lower() if ctx.command else ''
        action = str(ctx.kwargs.get('action', '') or '').strip().lower()
        message_content = (getattr(getattr(ctx, 'message', None), 'content', '') or '').strip().lower()

        # Players must explicitly start their adventure before gameplay commands.
        # Utility/moderation commands and the onboarding/profile commands remain available.
        gameplay_commands = {
            'hunt','h','search','hint','i','clue','catch','c','guess','cancel','stop','quit',
            'fix','repair','legendarybattle','lbattle','lgbattle','bossfight','battle','fight','b',
            'challenge','pvp','duel','chall','shinyhunt','spawnshiny','shinyspawn','setteam','teamset','slotteam',
            'select','s','sel','team','myteam','tm','usetm','tmuse','shop','market','store','giveitem','equip','holditem',
            'takeitem','unequip','removehelditem','useitem','use','itemuse','inventory','inv','bag','raid','candy',
            'daily','d','claim','balance','bal','money','bet','trade','tradeadd','ta','traderemove','tr','tradeconfirm',
            'tradeaccept','trconfirm','pokemonadd','pokeadd','addboss','bossadd','removeboss','bossremove',
            'pokedex','pd','dex','box','pokemon','pc','storage','info','pinfo','stats','moves','pmoves',
            'leaderboard','lb','top','coinsadd','addcoins','removecoins','takecoins','removepokemon','removepoke',
            'usetm','tmuse','pass','raid','hint','i','clue','profile','prof','me'
        }
        if name in gameplay_commands:
            with db() as c:
                row = c.execute('SELECT started FROM players WHERE user_id=?', (uid,)).fetchone()
            if not row or not row[0]:
                await ctx.send('🧭 You need to start your adventure first! Use `!start` to begin.')
                return False

        # Normalize the three mutually exclusive encounter activities.
        is_hunt = name in {'hunt', 'h', 'search'}
        is_legendary = name in {'legendarybattle', 'lbattle', 'lgbattle', 'bossfight'}
        is_raid_battle = (name == 'raid' and action in {'battle', 'fight'}) or message_content in {'!raid battle', '!raid fight', '/raid battle', '/raid fight'}

        with db() as c:
            raid_active = bool(c.execute('SELECT 1 FROM raid_encounters WHERE user_id=?', (uid,)).fetchone())
            legendary_active = bool(c.execute('SELECT 1 FROM boss_encounters WHERE user_id=?', (uid,)).fetchone())
            hunt_active = bool(c.execute('SELECT 1 FROM encounters WHERE user_id=?', (uid,)).fetchone())

        # Live views also count as active even if an encounter row was cleared early.
        view = ACTIVE_VIEWS.get(uid)
        raid_battle_active = isinstance(view, NPCBattleView) and bool(getattr(view, 'raid', False))
        legendary_battle_active = (uid in self.active_boss_battles and isinstance(view, NPCBattleView) and bool(getattr(view, 'boss', False)) and not bool(getattr(view, 'raid', False)))
        hunt_active = hunt_active or (isinstance(view, NPCBattleView) and not getattr(view, 'boss', False) and not getattr(view, 'raid', False))
        raid_active = raid_active or raid_battle_active
        legendary_active = legendary_active or legendary_battle_active

        if is_hunt and (legendary_active or raid_active):
            await ctx.send('⚠️ You cannot start a hunt while a legendary battle or raid is active. Finish that encounter first.')
            return False
        if is_legendary and (hunt_active or raid_active):
            await ctx.send('⚠️ You cannot start a legendary battle while a hunt or raid is active. Finish that encounter first.')
            return False
        if is_raid_battle and (hunt_active or legendary_active):
            await ctx.send('⚠️ You cannot start a raid battle while a hunt or legendary battle is active. Finish that encounter first.')
            return False

        # No global lock for ordinary commands: inventory, healing, shop, dex, box,
        # team management, and all unrelated commands remain available during encounters.
        return True
    @commands.command(name='start',aliases=['begin','st'],description='Start your adventure.')
    async def start(self,ctx):
        ensure_player(ctx.author.id)
        with db() as c:
            row=c.execute('SELECT started FROM players WHERE user_id=?',(ctx.author.id,)).fetchone()
            if row and row[0]:
                return await ctx.send('🧭 **Your journey is already started!** See `!profile` to view your adventure stats.')
            c.execute('UPDATE players SET started=1 WHERE user_id=?',(ctx.author.id,))
        e=discord.Embed(title='🎒 Adventure Started!', description=f'Welcome to **PokéVanta**, {ctx.author.mention}!\n\nYour adventure has begun and your trainer profile has been created.\n\n🌿 Use `!hunt` to find Pokémon\n👤 Use `!profile` to view your stats\n🪙 Use `!daily` to claim your daily reward', color=discord.Color.green())
        e.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=e)

    @commands.command(name='profile',aliases=['prof','me'],description='View your trainer adventure profile.')
    async def profile(self,ctx,member:discord.Member=None):
        member=member or ctx.author
        with db() as c:
            row=c.execute('SELECT coins,xp,level,daily_streak,started FROM players WHERE user_id=?',(member.id,)).fetchone()
            pokemon_count=c.execute('SELECT COUNT(*) FROM pokemon WHERE user_id=?',(member.id,)).fetchone()[0]
            shiny_count=c.execute('SELECT COUNT(*) FROM pokemon WHERE user_id=? AND shiny=1',(member.id,)).fetchone()[0]
            dex_count=c.execute('SELECT COUNT(DISTINCT dex_id) FROM pokedex_entries WHERE user_id=?',(member.id,)).fetchone()[0]
            hunts=c.execute('SELECT count FROM hunt_counts WHERE user_id=?',(member.id,)).fetchone()
            team_count=c.execute('SELECT COUNT(*) FROM team WHERE user_id=?',(member.id,)).fetchone()[0]
        if not row:
            e=discord.Embed(title='🧭 Journey Not Started',description=f'{member.mention} has not started their adventure yet. Use `!start` first.',color=discord.Color.orange())
        else:
            coins,xp,level,streak,started=row
            e=discord.Embed(title=f'🧑‍🚀 {member.display_name}’s Trainer Profile',description='A snapshot of this trainer’s PokéVanta journey.',color=discord.Color.blurple())
            e.set_thumbnail(url=member.display_avatar.url)
            e.add_field(name='🌟 Progress', value=f'**Level:** {level}\n**XP:** {xp}/{max(1,level)*100}\n**Adventure:** {"Started ✅" if started else "Not started"}', inline=True)
            e.add_field(name='🪙 Wallet', value=f'**{coins:,}** VantaCoins\n**Daily streak:** {streak} day(s)', inline=True)
            e.add_field(name='📚 Collection', value=f'**Pokémon:** {pokemon_count}\n**✨ Shiny:** {shiny_count}\n**Pokédex:** {dex_count} species\n**Team slots:** {team_count}/6', inline=True)
            e.add_field(name='🌿 Exploration',value=f'**Successful hunts:** {hunts[0] if hunts else 0}',inline=True)
            e.set_footer(text='Keep exploring — your next discovery is waiting!')
        await ctx.send(embed=e)

    @commands.command(name='hunt',aliases=['h','search'],description='Find a wild Pokémon; every tenth hunt triggers a boss battle.')
    async def hunt(self,ctx):
        try:
            uid=ctx.author.id
            with db() as c:
                # Never overwrite an encounter: the current Pokémon/boss must be resolved first.
                wild=c.execute('SELECT 1 FROM encounters WHERE user_id=?',(uid,)).fetchone()
                active=c.execute('SELECT 1 FROM boss_encounters WHERE user_id=?',(uid,)).fetchone()
                if wild:
                    return await ctx.send('⚠️ You already have a wild Pokémon waiting! Catch it with `!catch <name>` before using `!hunt` again.')
                if active:
                    return await ctx.send('⚠️ You already have an active legendary boss! Defeat it with `!legendarybattle` before hunting again.')
                c.execute('INSERT OR IGNORE INTO hunt_counts(user_id,count) VALUES(?,0)',(uid,))
                count=c.execute('SELECT count FROM hunt_counts WHERE user_id=?',(uid,)).fetchone()[0]
            # Starting a hunt does not advance catch progress. Only a successful catch does.
            d=await random_pokemon(); shiny=random.random()<1/128; lvl=random.randint(3,20)
            with db() as c:c.execute('INSERT OR REPLACE INTO encounters(user_id,dex_id,name,shiny,level,hints_used) VALUES(?,?,?,?,?,0)',(uid,d['id'],d['name'],int(shiny),lvl))
            e=discord.Embed(title='🌿 A wild Pokémon appeared!',description=f'**Catch progress:** {count}/50 • **Level:** {lvl}\n**Type:** ???\n\n👀 Look at the picture and guess the Pokémon!\nUse `!hint` for up to 2 missing-letter hints and `!catch <name>` to catch it. Every 10 successful catches unlocks a legendary boss!')
            if shiny:e.description='✨ **A rare shiny Pokémon appeared!**\n'+e.description
            art=sprite(d,shiny=shiny)
            if art:e.set_image(url=art)
            await ctx.reply(embed=e, mention_author=False)
        except Exception as e:await ctx.send(f'❌ Hunt error: `{e}`')

    @commands.command(name='add',aliases=['addboss','bossadd'])
    async def add_boss_pokemon(self,ctx,*pokemon_ids:int):
        """Add owned Pokémon to the active raid team (six) or legendary boss team (three)."""
        uid=ctx.author.id
        if not pokemon_ids:
            return await ctx.send('Usage: `!add <pokemon_id> [pokemon_id ...]` — example: `!add 1 2 3`.')
        with db() as c:
            raid=c.execute('SELECT 1 FROM raid_encounters WHERE user_id=?',(uid,)).fetchone()
            boss=c.execute('SELECT 1 FROM boss_encounters WHERE user_id=?',(uid,)).fetchone()
            if not raid and not boss:return await ctx.send('❌ Spawn a raid with `!raid spawn` or unlock a legendary boss first.')
            table='raid_party' if raid else 'boss_party'; limit=6 if raid else 3
            added=[]; errors=[]
            for requested_id in pokemon_ids:
                pokemon_id=resolve_box_id(c,uid,requested_id)
                if pokemon_id is None:
                    errors.append(f'ID `{requested_id}` is not yours (check `!box`)'); continue
                existing_rows=c.execute(f'SELECT slot,instance_id FROM {table} WHERE user_id=? ORDER BY slot',(uid,)).fetchall()
                if any(r[1]==pokemon_id for r in existing_rows):
                    errors.append(f'ID `{requested_id}` is already on the team'); continue
                if len(existing_rows)>=limit:
                    errors.append(f'ID `{requested_id}` not added: team is full'); continue
                row=c.execute('SELECT instance_id,name,level FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,uid)).fetchone()
                if not row:
                    errors.append(f'ID `{requested_id}` is not yours (check `!box`)'); continue
                used={r[0] for r in existing_rows}
                slot=next(i for i in range(1,limit+1) if i not in used)
                c.execute(f'INSERT INTO {table}(user_id,slot,instance_id) VALUES(?,?,?)',(uid,slot,pokemon_id))
                added.append(f'**{row[1].title()}** Lv.{row[2]} (ID `{requested_id}`)')
            count=c.execute(f'SELECT COUNT(*) FROM {table} WHERE user_id=?',(uid,)).fetchone()[0]
        lines=[]
        if added:
            team_label='Raid team' if raid else 'Boss team'
            lines.append('✅ Added: '+', '.join(added)+f'. {team_label}: **{count}/{limit}**.')
        if errors: lines.append('⚠️ '+ '; '.join(errors)+'.')
        if count==limit: lines.append('Team complete! Use `!raid battle`.' if raid else 'Team complete! Use `!legendarybattle`.')
        await ctx.send('\n'.join(lines) if lines else 'No Pokémon were added.')

    @commands.command(name='remove',aliases=['removeboss','bossremove'])
    async def remove_boss_pokemon(self,ctx,*args:str):
        """Remove Pokémon IDs from the boss team, or use !remove pass @user <quantity> as the developer."""
        uid=ctx.author.id
        if args and args[0].lower() == 'pass':
            if ctx.author.id not in OWNER_IDS:
                return await ctx.send('❌ This command is restricted to the bot developer.')
            mentions=list(getattr(ctx.message,'mentions',[]) or [])
            if len(args) != 3 or not mentions:
                return await ctx.send('Usage: `!remove pass @user <quantity>`.')
            try: quantity=int(args[2])
            except (TypeError,ValueError): return await ctx.send('❌ Quantity must be a whole number.')
            member=mentions[0]
            if quantity <= 0 or quantity > 100000:
                return await ctx.send('❌ Quantity must be between 1 and 100,000.')
            def remove_pass_action():
                with db() as c:
                    row=c.execute("SELECT amount FROM inventory WHERE user_id=? AND item='raid-pass'",(member.id,)).fetchone()
                    old=row[0] if row else 0
                    removed=min(old,quantity); new=old-removed
                    if row: c.execute("UPDATE inventory SET amount=? WHERE user_id=? AND item='raid-pass'",(new,member.id))
                return f'Removed **{removed:,} Raid Pass(es)** from {member.mention}. New balance: **{new:,}**.'
            with db() as c: current=c.execute("SELECT amount FROM inventory WHERE user_id=? AND item='raid-pass'",(member.id,)).fetchone()
            current_amount=current[0] if current else 0
            return await self.dev_confirmation(ctx,'Confirm Raid Pass removal',f'Remove up to **{quantity:,} Raid Pass(es)** from {member.mention}? Current balance: **{current_amount:,}**.',remove_pass_action)
        try: pokemon_ids=tuple(int(x) for x in args)
        except (TypeError,ValueError): return await ctx.send('Usage: `!remove <pokemon_id> [pokemon_id ...]` or `!remove pass @user <quantity>`.')
        if not pokemon_ids:
            return await ctx.send('Usage: `!remove <pokemon_id> [pokemon_id ...]` — example: `!remove 1 2`.')
        with db() as c:
            raid=c.execute('SELECT 1 FROM raid_encounters WHERE user_id=?',(uid,)).fetchone()
            boss=c.execute('SELECT 1 FROM boss_encounters WHERE user_id=?',(uid,)).fetchone()
            if not raid and not boss:return await ctx.send('❌ You do not have an active raid or legendary encounter team to edit.')
            table='raid_party' if raid else 'boss_party'; limit=6 if raid else 3; label='Raid team' if raid else 'Boss team'
            removed=[]; missing=[]
            for requested_id in pokemon_ids:
                pokemon_id=resolve_box_id(c,uid,requested_id)
                if pokemon_id is None:
                    missing.append(str(requested_id)); continue
                row=c.execute(f'SELECT bp.slot,p.name FROM {table} bp JOIN pokemon p ON p.instance_id=bp.instance_id WHERE bp.user_id=? AND bp.instance_id=?',(uid,pokemon_id)).fetchone()
                if not row:
                    missing.append(str(requested_id)); continue
                c.execute(f'DELETE FROM {table} WHERE user_id=? AND instance_id=?',(uid,pokemon_id))
                removed.append(f'**{row[1].title()}** (ID `{requested_id}`)')
            # Re-pack slots so new additions fill the first available slots.
            remaining=c.execute(f'SELECT instance_id FROM {table} WHERE user_id=? ORDER BY slot',(uid,)).fetchall()
            c.execute(f'DELETE FROM {table} WHERE user_id=?',(uid,))
            for slot,row in enumerate(remaining,1):
                c.execute(f'INSERT INTO {table}(user_id,slot,instance_id) VALUES(?,?,?)',(uid,slot,row[0]))
            count=len(remaining)
        lines=[]
        if removed: lines.append('✅ Removed: '+', '.join(removed)+f'. {label}: **{count}/{limit}**.')
        if missing: lines.append('⚠️ Not on your active team: '+', '.join(f'`{x}`' for x in missing)+'.')
        if count<limit: lines.append('Add replacements with `!add <pokemon_id> [pokemon_id ...]`.')
        await ctx.send('\n'.join(lines) if lines else 'No Pokémon were removed.')

    @commands.command(name='legendarybattle',aliases=['lbattle','lgbattle','bossfight'])
    async def legendarybattle(self,ctx):
        uid=ctx.author.id
        dev_override=self.is_dev(ctx)
        if uid in self.active_boss_battles:
            return await ctx.send('⚔️ Your legendary battle is already in progress! Finish that battle before using `!legendarybattle` again.')
        with db() as c:
            boss=c.execute('SELECT dex_id,name,level,shiny FROM boss_encounters WHERE user_id=?',(uid,)).fetchone()
        # The configured dev can test boss battles without completing 10 hunts.
        # Dev-created/started bosses are guaranteed shiny, so winning grants the existing 1,000,000-coin jackpot.
        if dev_override and not boss:
            candidates=[x for x in POKEMON_LIST if x['name'] in LEGENDARY_NAMES]
            if not candidates:
                return await ctx.send('❌ Legendary list is not loaded yet. Try `!legendarybattle` again shortly.')
            d=await pokemon_data(random.choice(candidates)['name'])
            with db() as c:
                c.execute('INSERT OR REPLACE INTO boss_encounters(user_id,dex_id,name,level,shiny) VALUES(?,?,?,?,1)',(uid,d['id'],d['name'],0))
                c.execute('DELETE FROM boss_party WHERE user_id=?',(uid,))
            boss=(d['id'],d['name'],0,1)
            await ctx.send(f'🛠️ **Dev override enabled:** you can start this boss without completing 10 hunts. This boss is guaranteed shiny; defeating it awards the **1,000,000 {get_vantacoin_emoji()} jackpot**. Build your team with `!add <pokemon_id>` if needed.')
        elif dev_override and boss and not boss[3]:
            with db() as c:
                c.execute('UPDATE boss_encounters SET shiny=1 WHERE user_id=?',(uid,))
            boss=(boss[0],boss[1],boss[2],1)
            await ctx.send(f'🛠️ **Dev override enabled:** this boss is now guaranteed shiny. Defeating it awards the **1,000,000 {get_vantacoin_emoji()} jackpot**.')
        with db() as c:
            # Re-read in case the dev override created/updated the encounter above.
            boss=c.execute('SELECT dex_id,name,level,shiny FROM boss_encounters WHERE user_id=?',(uid,)).fetchone()
            party=c.execute('SELECT p.* FROM boss_party bp JOIN pokemon p ON p.instance_id=bp.instance_id WHERE bp.user_id=? ORDER BY bp.slot',(uid,)).fetchall()
        if not boss:return await ctx.send('❌ No active boss encounter. Every 10th hunt triggers one (devs can use `!legendarybattle` directly).')
        if len(party)!=3:return await ctx.send(f'🧩 Your boss team has **{len(party)}/3 Pokémon**. Add them with `!add <pokemon_id>`; use `!box` to see IDs.')
        if all(r[8]<=0 for r in party):return await ctx.send('💤 All three Pokémon have fainted. Use a potion with `!useitem Potion <pokemon_id>` or a status berry before starting the boss battle.')
        lead=next((r for r in party if r[8]>0),party[0])
        # Scale boss level to the strongest of all three selected Pokémon, not the active lead.
        boss_level=min(300, max(r[4] for r in party)+random.randint(18,25))
        with db() as c:c.execute('UPDATE boss_encounters SET level=? WHERE user_id=?',(boss_level,uid))
        d=await pokemon_data(boss[0]);d['_level']=boss_level
        self.active_boss_battles.add(uid)
        v=NPCBattleView(uid,lead,d,boss=True,boss_shiny=bool(boss[3]),active_boss_battles=self.active_boss_battles)
        try:
            await v.build()
        except Exception:
            self.active_boss_battles.discard(uid)
            raise
        e=discord.Embed(title='🔥 LEGENDARY BOSS — 3 VS 1',description=f'**Boss:** {display_name(d)} Lv. **{boss_level}**\nHP {hp_bar(max_hp(d,boss_level),max_hp(d,boss_level))}\nStatus: **Healthy**\n**Your squad:**\n'+'\n'.join(f'• **{r[3].title()}** Lv.{r[4]}\n  HP {hp_bar(r[8],r[9])}\n  Status: **{status_label(r[11] or "")}**' for r in party)+'\n\nChoose a move using the move buttons below. If a Pokémon faints, only the Switch button remains; select a healthy teammate to continue. Boss level is 18–25 levels above your highest-level teammate. Shiny status and odds were determined when this boss appeared.')
        e.color=discord.Color.dark_red()
        if sprite(d,shiny=bool(boss[3])):e.set_image(url=sprite(d,shiny=bool(boss[3])))
        v.message=await ctx.send(embed=e,view=v); ACTIVE_VIEWS[uid]=v

    @commands.command(name='hint',aliases=['i','clue'],description='Get one of two hints for your current wild Pokémon.')
    async def hint(self,ctx):
        uid=ctx.author.id
        with db() as c:enc=c.execute('SELECT dex_id,name,shiny,level,hints_used FROM encounters WHERE user_id=?',(uid,)).fetchone()
        if not enc:return await ctx.send('❌ You have no active hunt. Use `!hunt` first.')
        if enc[4]>=2:return await ctx.send('❌ You have already used both hints for this Pokémon.')
        d=await pokemon_data(enc[0]); used=enc[4]
        # Progressive letter-reveal hints: both hints show missing letters inside the name.
        # Spaces and hyphens stay visible; hint 2 reveals more internal letters than hint 1.
        answer=display_name(d)
        chars=list(answer)
        letter_positions=[i for i,ch in enumerate(chars) if ch.isalpha()]
        if len(letter_positions)<=2:
            masked=''.join(ch if ch.isalpha() or not ch.isalpha() else ch for ch in chars)
        else:
            first,last=letter_positions[0],letter_positions[-1]
            for rank,pos in enumerate(letter_positions):
                if pos in (first,last):
                    continue
                # Hint 1 reveals about one third of inner letters; hint 2 reveals about two thirds.
                revealed = (rank % 3 == 0) if used == 0 else (rank % 3 == 0 or rank % 2 == 0)
                if not revealed:
                    chars[pos]='_'
            masked=' '.join(chars) if ' ' not in chars else ''.join(chars)
            # Keep the name readable with spaces between masked letters, e.g. P _ k _ _ n.
            if ' ' not in answer and '-' not in answer:
                masked=' '.join(chars)
        hint_number=used+1
        remaining=1-used
        msg=f'🔎 **Hint {hint_number}/2:** Pokémon name: **{masked}**'
        if used==0:
            msg+='\n*One more hint is available and will reveal more letters.*'
        with db() as c:c.execute('UPDATE encounters SET hints_used=? WHERE user_id=?',(used+1,uid))
        await ctx.send(msg)

    @commands.command(name='catch',aliases=['c','guess'],description='Guess and automatically catch a wild Pokémon.')
    async def catch(self,ctx,*,name:str):
        uid=ctx.author.id
        def norm(value):
            return re.sub(r'[^a-z0-9]', '', value.lower().replace('♀','f').replace('♂','m'))
        guess=norm(name)

        # Global shiny encounter takes priority. A SQLite write lock makes the
        # claim atomic, so only the first correct user can receive this Pokémon.
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            global_enc=c.execute('SELECT dex_id,name,shiny,level FROM global_encounter WHERE id=1').fetchone()
            if global_enc:
                if guess != norm(global_enc[1]) and guess != str(global_enc[0]):
                    c.commit()
                    return await ctx.send(f'❌ **{name}** is incorrect! The server-wide shiny is still available — keep guessing!')
                # Remove it while holding the write lock so no second user can claim it.
                c.execute('DELETE FROM global_encounter WHERE id=1')
                c.commit()
                enc=(global_enc[0],global_enc[1],global_enc[2],global_enc[3],0)
                is_global=True
            else:
                c.commit()
                enc=c.execute('SELECT dex_id,name,shiny,level,hints_used FROM encounters WHERE user_id=?',(uid,)).fetchone()
                is_global=False
        if not enc:
            return await ctx.send('❌ No active Pokémon to catch. Use `!hunt` — or wait for a server-wide shiny spawn!')
        if not is_global and guess != norm(enc[1]) and guess != str(enc[0]):
            return await ctx.send(f'❌ **{name}** is incorrect! The wild Pokémon is still there — try again or use `!hint`.')
        try:
            d=await pokemon_data(enc[0]); mh=max_hp(d,enc[3])
        except Exception as exc:
            # Leave the encounter untouched so the player can retry once the API responds.
            print(f'Catch data lookup failed for user {uid}, dex_id={enc[0]!r}: {type(exc).__name__}: {exc}')
            return await ctx.send('⚠️ I could not load this Pokémon from PokéAPI right now. Your encounter is still saved—please try `!catch <name>` again in a moment.')
        with db() as c:
            cur=c.execute('INSERT INTO pokemon(user_id,dex_id,name,level,shiny,hp,max_hp) VALUES(?,?,?,?,?,?,?)',(uid,d['id'],d['name'],enc[3],enc[2],mh,mh)); iid=cur.lastrowid; box_id=assign_box_id(c,uid,iid)
            # Register only the first catch of this species + variant; repeats do not change the Dex.
            c.execute('INSERT OR IGNORE INTO pokedex_entries(user_id,dex_id,name,shiny) VALUES(?,?,?,?)',(uid,int(enc[0]),d['name'],int(bool(enc[2]))))
            if not c.execute('SELECT 1 FROM team WHERE user_id=?',(uid,)).fetchone():
                c.execute('INSERT OR REPLACE INTO team(user_id,slot,instance_id) VALUES(?,?,?)',(uid,1,iid))
            if not is_global:
                c.execute('DELETE FROM encounters WHERE user_id=?',(uid,))
        add_progress(uid,coins=50,xp=25)
        boss_unlocked=False
        catch_progress=None
        if not is_global:
            with db() as c:
                c.execute('INSERT OR IGNORE INTO hunt_counts(user_id,count) VALUES(?,0)',(uid,))
                previous=c.execute('SELECT count FROM hunt_counts WHERE user_id=?',(uid,)).fetchone()[0]
                progressed=previous+1
                # Every 10th successful catch unlocks a boss, including catch 50.
                # After the 50th catch, progress rolls over to 0 for the next cycle.
                boss_unlocked = (progressed % 10 == 0)
                catch_progress = progressed % 50
                is_fiftieth_catch = (progressed == 50)
                c.execute('UPDATE hunt_counts SET count=? WHERE user_id=?',(catch_progress,uid))
        note=' **You were the first to guess it!**' if is_global else ''
        response=f'🎉 {ctx.author.mention} caught {"✨ SHINY " if enc[2] else ""}{display_name(d)}!{note} ID: `{box_id}`\n💰 +50 coins! Check `!box`.'
        if not is_global:
            response+=f'\n📈 Catch progress: **{catch_progress}/50**.'
        if boss_unlocked:
            candidates=[x for x in POKEMON_LIST if x['name'] in LEGENDARY_NAMES]
            if candidates:
                boss_data=await pokemon_data(random.choice(candidates)['name'])
                # The 50th successful catch gets improved shiny odds for its boss: 1/250.
                shiny_denominator = 250 if is_fiftieth_catch else 1000
                boss_shiny = (random.randint(1, shiny_denominator) == 1)
                with db() as c:
                    c.execute('INSERT OR REPLACE INTO boss_encounters(user_id,dex_id,name,level,shiny) VALUES(?,?,?,?,?)',(uid,boss_data['id'],boss_data['name'],0,int(boss_shiny)))
                    c.execute('DELETE FROM boss_party WHERE user_id=?',(uid,))
                odds_text = '1/250 (50th-catch bonus!)' if is_fiftieth_catch else '1/1000'
                boss_embed=discord.Embed(title='🔥 LEGENDARY BOSS CHALLENGE UNLOCKED!',description=f'**{display_name(boss_data)}** has appeared!\n**Type:** {type_text(boss_data)}\n**Boss level will be revealed after you select all 3 Pokémon.**\nShiny odds: **{odds_text}**.\n\nYou completed {progressed} successful catches in this cycle! Build a team of exactly **3 Pokémon** with `!add <pokemon_id>` (use `!box` for IDs), then start with `!legendarybattle`. The boss level will be 10–15 levels higher than your highest-level teammate.')
                if sprite(boss_data,shiny=boss_shiny): boss_embed.set_image(url=sprite(boss_data,shiny=boss_shiny))
                response+='\n\n'+f'🔥 **Legendary boss unlocked!** Your next encounter is ready — use `!add <pokemon_id>` to select three Pokémon, then `!legendarybattle`.'
                await ctx.send(response)
                return await ctx.send(embed=boss_embed)
        return await ctx.send(response)

    @commands.command(name='cancel',aliases=['stop','quit'])
    async def cancel(self,ctx):
        """Cancel a scheduled match, trade, or this user's pending encounter/battle."""
        # Match announcements share this existing !cancel command to avoid duplicate registration.
        if ctx.guild:
            active = getattr(self.bot, 'active_match_announces', {})
            state = active.get(ctx.guild.id)
            if state:
                extensions = self.bot.get_cog('CarlStyleExtensions')
                if not extensions or not await extensions.require_dev(ctx):
                    return
                task = state.get('task')
                if task and task is not asyncio.current_task():
                    task.cancel()
                    return await ctx.send('🛑 Match setup/schedule cancelled.')
                return await ctx.send('ℹ️ There is no cancellable match task running right now.')
        trade = ACTIVE_TRADES.get(TRADE_BY_USER.get(ctx.author.id))
        if trade:
            if ctx.author.id != trade['starter']:
                return await ctx.send('Only the person who initiated this trade can cancel it.')
            await end_trade(trade, '🚫 Trade cancelled by its initiator.')
            return
        uid=ctx.author.id; changes=[]
        with db() as c:
            if c.execute('DELETE FROM encounters WHERE user_id=?',(uid,)).rowcount: changes.append('wild hunt')
            if c.execute('DELETE FROM boss_encounters WHERE user_id=?',(uid,)).rowcount: changes.append('boss encounter')
            c.execute('DELETE FROM boss_party WHERE user_id=?',(uid,))
            if c.execute('DELETE FROM raid_encounters WHERE user_id=?',(uid,)).rowcount:
                c.execute("INSERT INTO inventory(user_id,item,amount) VALUES(?, 'raid-pass', 1) ON CONFLICT(user_id,item) DO UPDATE SET amount=amount+1",(uid,))
                changes.append('raid (Raid Pass refunded)')
            c.execute('DELETE FROM raid_party WHERE user_id=?',(uid,))
        partner=self.challenges.pop(uid,None)
        if partner is not None:
            self.challenges.pop(partner,None); changes.append('challenge')
        view=ACTIVE_VIEWS.pop(uid,None)
        if view:
            try:
                if isinstance(view,PvPBattle):
                    view.over=True
                    ACTIVE_VIEWS.pop(view.a,None);ACTIVE_VIEWS.pop(view.b,None)
                    if view.message: await view.message.edit(content=f'🛑 Battle cancelled by <@{uid}>.',embed=None,view=None)
                elif getattr(view,'message',None):
                    if hasattr(view,'active_boss_battles') and view.active_boss_battles is not None:view.active_boss_battles.discard(uid)
                    await view.message.edit(content=f'🛑 Battle cancelled by <@{uid}>.',embed=None,view=None)
                else:view.stop()
                changes.append('battle/menu')
            except Exception: pass
        if changes:return await ctx.send('🛑 Cancelled: **'+', '.join(changes)+'**. You can start again whenever you are ready.')
        await ctx.send('ℹ️ You do not have an active hunt, challenge, or battle to cancel.')

    @commands.command(name='fix',aliases=['repair'])
    async def fix(self,ctx):
        """Dev-only recovery tool; reply to the bot's stuck message with !fix."""
        if not self.is_dev(ctx): return
        ref=ctx.message.reference
        if not ref or not ref.message_id:
            return await ctx.send('Reply directly to the bot message that is stuck, then type `!fix`.')
        try: target=ref.resolved or await ctx.channel.fetch_message(ref.message_id)
        except Exception:return await ctx.send('❌ I could not access that replied-to message. Check bot permissions and try again.')
        if target.author.id != self.bot.user.id:
            return await ctx.send('❌ Reply to a message sent by this bot, then run `!fix`.')
        # Recover temporary state for the dev; for another user's stuck interaction, mention that user in the bot message.
        affected=ctx.author.id
        target_text=(target.content or '')+'\n'+'\n'.join((e.description or '') for e in target.embeds)
        match=re.search(r'<@!?(\d+)>',target_text)
        if match: affected=int(match.group(1))
        changes=[]
        with db() as c:
            if c.execute('DELETE FROM encounters WHERE user_id=?',(affected,)).rowcount:changes.append('wild encounter')
            if c.execute('DELETE FROM boss_encounters WHERE user_id=?',(affected,)).rowcount:changes.append('boss encounter')
            c.execute('DELETE FROM boss_party WHERE user_id=?',(affected,))
        partner=self.challenges.pop(affected,None)
        if partner is not None:self.challenges.pop(partner,None);changes.append('challenge state')
        view=ACTIVE_VIEWS.pop(affected,None)
        if view:
            try:
                if isinstance(view,PvPBattle):
                    view.over=True;ACTIVE_VIEWS.pop(view.a,None);ACTIVE_VIEWS.pop(view.b,None)
                    if view.message:await view.message.edit(content='🛠️ This battle was reset by a developer. Start a new one.',embed=None,view=None)
                elif getattr(view,'message',None):
                    if hasattr(view,'active_boss_battles') and view.active_boss_battles is not None:view.active_boss_battles.discard(affected)
                    await view.message.edit(content='🛠️ This interaction was reset by a developer. Run the command again.',embed=None,view=None)
                else:view.stop()
                changes.append('stuck buttons/battle')
            except Exception:pass
        if not changes:changes.append('temporary state checked; no stuck state was found')
        await ctx.send(f'🛠️ **Fix applied for <@{affected}>:** '+', '.join(changes)+'. This resets common temporary glitches; it cannot automatically repair every possible code/database error.')

    @commands.command(name='help', aliases=['commands', '?'], description='Show help categories, or all commands in one category.')
    async def help_command(self, ctx, *, category: str = None):
        """Show one general help embed, or one embed for a selected category."""
        developer_only = {
            'add', 'remove', 'pokemonadd', 'shinyhunt', 'pass', 'banbot', 'unbanbot',
            'ban', 'unban', 'coinsadd', 'removecoins', 'removepokemon',
            'setupitememojis', 'setupvantacoin', 'tagset', 'tagdelete', 'ccset',
            'ccdelete'
        }
        categories = {
            'start': 'Adventure', 'profile': 'Adventure', 'hunt': 'Adventure', 'hint': 'Adventure', 'catch': 'Adventure', 'cancel': 'Adventure', 'fix': 'Adventure',
            'pokedex': 'Box & Pokédex', 'dex': 'Box & Pokédex', 'box': 'Box & Pokédex', 'info': 'Box & Pokédex', 'moves': 'Box & Pokédex',
            'select': 'Teams & Battles', 'setteam': 'Teams & Battles', 'team': 'Teams & Battles', 'legendarybattle': 'Teams & Battles', 'battle': 'Teams & Battles', 'challenge': 'Teams & Battles',
            'raid': 'Raids & Candies', 'candy': 'Raids & Candies',
            'add': 'Developer Controls', 'remove': 'Developer Controls',
            'trade': 'Trading', 'tradeadd': 'Trading', 'traderemove': 'Trading', 'tradeconfirm': 'Trading',
            'shop': 'Coins & Shop', 'market': 'Coins & Shop', 'give': 'Coins & Shop', 'daily': 'Coins & Shop', 'balance': 'Coins & Shop', 'bal': 'Coins & Shop', 'leaderboard': 'Coins & Shop', 'bet': 'Coins & Shop', 'speak': 'Server Setup',
            'inventory': 'Inventory & Items', 'giveitem': 'Inventory & Items', 'takeitem': 'Inventory & Items', 'useitem': 'Inventory & Items', 'usetm': 'Inventory & Items',
            'roll': 'Utilities', 'choose': 'Utilities', 'poll': 'Utilities', 'serverinfo': 'Utilities', 'userinfo': 'Utilities', 'remind': 'Utilities',
            'tag': 'Tags & Custom Commands', 'tags': 'Tags & Custom Commands', 'tagset': 'Tags & Custom Commands', 'tagdelete': 'Tags & Custom Commands', 'ccset': 'Tags & Custom Commands', 'ccdelete': 'Tags & Custom Commands',
            'mute': 'Moderation', 'unmute': 'Moderation', 'kick': 'Moderation', 'clear': 'Moderation', 'slowmode': 'Moderation', 'lock': 'Moderation', 'unlock': 'Moderation', 'warn': 'Moderation', 'warnings': 'Moderation', 'clearwarnings': 'Moderation', 'removewarn': 'Moderation', 'role': 'Moderation', 'dump': 'Moderation',
            'ping': 'Utilities',
            'setwelcome': 'Server Setup', 'setgoodbye': 'Server Setup', 'setlog': 'Server Setup', 'setautorole': 'Server Setup', 'setstarboard': 'Server Setup', 'rradd': 'Server Setup', 'rrremove': 'Server Setup', 'automodword': 'Server Setup', 'automodwords': 'Server Setup', 'setnick': 'Server Setup', 'roleadd': 'Server Setup', 'roleremove': 'Server Setup', 'rolecreate': 'Server Setup', 'roledelete': 'Server Setup', 'announce': 'Server Setup',
            'banbot': 'Developer Controls', 'unbanbot': 'Developer Controls', 'ban': 'Developer Controls', 'unban': 'Developer Controls', 'coinsadd': 'Developer Controls', 'removecoins': 'Developer Controls', 'removepokemon': 'Developer Controls', 'pokemonadd': 'Developer Controls', 'shinyhunt': 'Developer Controls', 'pass': 'Developer Controls', 'setupitememojis': 'Developer Setup', 'setupvantacoin': 'Developer Setup'
        }
        category_aliases = {
            'box': 'Box & Pokédex', 'dex': 'Box & Pokédex', 'pokedex': 'Box & Pokédex', 'pokemon': 'Box & Pokédex',
            'adventure': 'Adventure', 'hunt': 'Adventure', 'battle': 'Teams & Battles', 'teams': 'Teams & Battles',
            'raid': 'Raids & Candies', 'candy': 'Raids & Candies', 'trade': 'Trading', 'shop': 'Coins & Shop', 'market': 'Coins & Shop', 'm': 'Coins & Shop', 'coins': 'Coins & Shop',
            'items': 'Inventory & Items', 'inventory': 'Inventory & Items', 'utility': 'Utilities', 'utilities': 'Utilities', 'fun': 'Utilities',
            'tags': 'Tags & Custom Commands', 'custom': 'Tags & Custom Commands', 'mod': 'Moderation', 'moderation': 'Moderation',
            'config': 'Server Setup', 'setup': 'Server Setup', 'server': 'Server Setup', 'dev': 'Developer Controls', 'developer': 'Developer Controls',
            'developer setup': 'Developer Setup', 'giveaway': 'Giveaways', 'giveawaystart': 'Giveaways', 'gstart': 'Giveaways', 'giveawayend': 'Giveaways', 'gend': 'Giveaways', 'giveawayreroll': 'Giveaways', 'greroll': 'Giveaways', 'removewarn': 'Moderation', 'removewarning': 'Moderation', 'delwarn': 'Moderation', 'rwarn': 'Moderation'
        }
        requested = (category or '').strip().lower()
        requested_category = category_aliases.get(requested)
        if requested and not requested_category:
            requested_category = next((v for v in set(categories.values()) if v.lower() == requested), None)
        if requested and not requested_category:
            requested_category = None
        if requested and not requested_category:
            return await ctx.send('Unknown help category. Use `!help` to see the available categories. Example: `!help box`.')

        command_rows = []
        for command in self.bot.walk_commands():
            if command.hidden:
                continue
            root_name = command.qualified_name.split()[0]
            cat = categories.get(root_name, 'Utilities')
            if requested_category and cat != requested_category:
                continue
            is_dev = root_name in developer_only
            # Build readable usage from registered parameters; avoid exposing generic <args> placeholders.
            signature = (getattr(command, 'signature', '') or '').strip()
            params = getattr(command, 'clean_params', {}) or {}
            if params:
                usage_parts = []
                for param_name, param in params.items():
                    name = param_name.replace('_', ' ')
                    annotation = getattr(param, 'annotation', None)
                    if annotation is discord.Member or annotation is discord.User:
                        name = 'user'
                    elif annotation is int:
                        name = 'number' if name in ('amount', 'count', 'quantity', 'seconds') else name
                    if getattr(param, 'kind', None) == inspect.Parameter.KEYWORD_ONLY:
                        usage_parts.append(f'<{name}...>')
                    elif getattr(param, 'default', inspect.Parameter.empty) is not inspect.Parameter.empty:
                        usage_parts.append(f'[{name}]')
                    else:
                        usage_parts.append(f'<{name}>')
                usage = f'!{command.qualified_name} ' + ' '.join(usage_parts)
            else:
                usage = f'!{command.qualified_name}'
            desc = next((line.strip() for line in (command.help or command.description or '').splitlines() if line.strip()), '')
            if not desc:
                known_descriptions = {
                    'box': 'View your Pokémon collection and manage stored Pokémon.',
                    'pokedex': 'Look up a Pokémon species, stats, types, abilities, and artwork.',
                    'dex': 'Browse the Pokédex by generation or category.',
                    'select': 'Select a Pokémon from your collection for your active team.',
                    'setteam': 'Set a Pokémon into a team slot.',
                    'team': 'View your current Pokémon team.',
                    'start': 'Begin your PokéVanta adventure.',
                    'hunt': 'Search for a wild Pokémon encounter.',
                    'hint': 'Get a hint about the current encounter.',
                    'catch': 'Attempt to catch the currently encountered Pokémon.',
                    'cancel': 'Cancel your current hunt, challenge, or battle.',
                    'raid': 'View or start available raid content.',
                    'candy': 'Use Rare Candies to level up a Pokémon.',
                    'trade': 'Start a Pokémon trade with another trainer.',
                    'tradeadd': 'Add one of your Pokémon or items to the active trade.',
                    'traderemove': 'Remove an offer from the active trade.',
                    'tradeconfirm': 'Confirm the active trade when both trainers are ready.',
                    'shop': 'Browse the shop and purchase available items.',
                    'market': 'Browse the player-to-player Pokémon market. Use !m as a short alias; supports view, offer, buy, listings, remove, and claim.',
                    'give': 'Transfer VantaCoins to another trainer from your balance.',
                    'profile': 'View your adventure stats, trainer progress, coins, and Pokémon collection.',
                    'speak': 'Post an announcement embed with text and optional attached GIF, image, or video to a chosen channel.',
                    'daily': 'Claim your daily rewards.',
                    'balance': 'View your VantaCoin balance and trainer progress.',
                    'inventory': 'View items in your inventory.',
                    'giveitem': 'Give an item to a Pokémon in your collection.',
                    'takeitem': 'Remove a held item from a Pokémon.',
                    'useitem': 'Use an item on a Pokémon.',
                    'usetm': 'Teach a Pokémon a move using a TM.',
                    'lock': 'Prevent the default server role from sending messages in this channel.',
                    'unlock': 'Restore the default server role’s normal channel permissions.',
                    'slowmode': 'Set the channel slowmode delay.',
                    'clear': 'Delete a specified number of recent messages.',
                    'kick': 'Kick a member from this server.',
                    'mute': 'Timeout a member in this server.',
                    'unmute': 'Remove a member timeout.',
                    'warn': 'Issue a moderation warning to a member.',
                    'warnings': 'View a member’s moderation warnings.',
                    'clearwarnings': 'Clear a member’s stored warnings.',
                    'role': 'Toggle a role for a member. Requires Manage Roles and respects role hierarchy.',
                    'dump': 'List usernames and user IDs of everyone with a role, without mentioning them.',
                    'ping': 'Show WebSocket latency and command response time.',
                    'serverinfo': 'Show information about this server.',
                    'userinfo': 'Show information about a server member.',
                    'roll': 'Roll a random number.',
                    'choose': 'Choose one option at random from the provided choices.',
                    'poll': 'Create a poll for server members.',
                    'leaderboard': 'Show the top trainers by VantaCoins.',
                    'fix': 'Developer-only tool to reset common stuck game interactions.',
                }
                desc = known_descriptions.get(root_name, f'{root_name.replace("_", " ").capitalize()} command. See its usage above for the required arguments.')
            alias_list = [f'!{a}' for a in getattr(command, 'aliases', []) if a]
            alias_text = f" (aliases: {', '.join(alias_list)})" if alias_list else ''
            access = ' **[BOT DEVELOPERS ONLY]**' if is_dev else ''
            command_rows.append((cat, f'`{usage}`{alias_text}{access} — {desc[:130]}'))

        embed = discord.Embed(color=discord.Color.blurple())
        if not requested:
            embed.title = '📘 PokéVanta Help'
            embed.description = ('Choose a category below. Run the matching command to see every command in that category, all in one embed.\n'
                                 'Example: `!help box` · `!help coins`\nMarket shortcut: `!m view recent`, `!m offer <Pokémon ID> <price>`, `!m buy <listing ID>`, `!m claim <listing ID>`.\n\n'
                                 '**Developer-only commands are marked clearly and can only be used by configured PokéVanta bot developers.**')
            all_categories = sorted({cat for cat, _ in command_rows}, key=lambda x: x.lower())
            for cat in all_categories:
                shortcut = cat.lower().replace('&', '').replace('é', 'e').replace(' ', '-')
                # Friendly, short category commands are accepted by the alias map above.
                example = {
                    'Box & Pokédex': '`!help box`', 'Adventure': '`!help adventure`',
                    'Teams & Battles': '`!help battle`', 'Raids & Candies': '`!help raid`',
                    'Trading': '`!help trade`', 'Coins & Shop': '`!help shop`',
                    'Inventory & Items': '`!help items`', 'Utilities': '`!help utilities`',
                    'Tags & Custom Commands': '`!help tags`', 'Moderation': '`!help moderation`',
                    'Server Setup': '`!help setup`', 'Developer Controls': '`!help developer`',
                    'Developer Setup': '`!help developer setup`', 'Giveaways': '`!help giveaways`'
                }.get(cat, f'`!help {shortcut}`')
                embed.add_field(name=cat, value=example, inline=True)
        else:
            embed.title = f'📘 PokéVanta Help — {requested_category}'
            rows = [line for cat, line in command_rows if cat == requested_category]
            if not rows:
                rows = ['No visible commands are registered in this category.']
            # Keep all category commands in one embed, using multiple fields if needed.
            chunks, current, current_len = [], [], 0
            for line in rows:
                if current and (current_len + len(line) + 1 > 1000):
                    chunks.append(current); current = []; current_len = 0
                current.append(line); current_len += len(line) + 1
            if current:
                chunks.append(current)
            for index, chunk in enumerate(chunks[:25], 1):
                embed.add_field(name=f'Commands' + (f' ({index})' if len(chunks) > 1 else ''), value='\n'.join(chunk), inline=False)
            embed.description = 'Commands marked **[BOT DEVELOPERS ONLY]** are restricted to configured PokéVanta bot developers. Server setup and moderation commands use the relevant Discord permissions.'
        embed.set_footer(text='Prefix: ! • Use !help <category> for category commands')
        await ctx.send(embed=embed)

    @commands.command(name='pokedex',aliases=['pd'],description='View normal or shiny Pokémon species information.')
    async def pokedex(self,ctx,*,name:str):
        try:
            shiny=name.lower().replace(' ', '').startswith('shiny')
            lookup=name[5:] if shiny else name
            lookup=lookup.strip().replace(' ','-')
            d=await pokemon_data(lookup); s=stats(d)
            species=await api_get(f'/pokemon-species/{d["id"]}')
            gen=species.get('generation',{}).get('name','unknown-generation').replace('generation-', '').upper()
            gen_label={'I':'Generation I','II':'Generation II','III':'Generation III','IV':'Generation IV','V':'Generation V','VI':'Generation VI','VII':'Generation VII','VIII':'Generation VIII','IX':'Generation IX'}.get(gen, f'Generation {gen}')
            label=('✨ Shiny ' if shiny else '')+display_name(d)
            abilities=', '.join(a['ability']['name'].replace('-', ' ').title() + (' (Hidden)' if a.get('is_hidden') else '') for a in d.get('abilities',[])) or 'Unknown'
            e=discord.Embed(title=f'#{d["id"]} — {label}',description=f'**Type:** {type_text(d)}\n**BST:** {sum(s.values())}\n**Generation:** {gen_label}\n**Abilities:** {abilities}')
            for k,l in [('hp','❤️ HP'),('attack','⚔️ Attack'),('defense','🛡️ Defense'),('special-attack','✨ Sp. Atk'),('special-defense','🔰 Sp. Def'),('speed','💨 Speed')]:e.add_field(name=l,value=str(s[k]))
            art=sprite(d,shiny=shiny)
            if art:e.set_image(url=art)
            await ctx.send(embed=e)
        except Exception: await ctx.send('❌ Pokémon not found. Try `!pokedex eternatus` or `!pokedex shinyeternatus`.')
    @commands.command(name='dex',description='View normal/shiny Pokédex by generation or category.')
    async def dex(self,ctx,*,query:str=''):
        query=query.lower().strip().replace('_',' ').replace('-',' ')
        # Bare !dex and !dex shiny are command menus, not full dex listings.
        if not query:
            e=discord.Embed(title='📘 Normal Pokédex Commands', color=discord.Color.blue(), description=(
                '`!dex kanto` / `!dex gen 1` — Kanto\n'
                '`!dex johto` / `!dex gen 2` — Johto\n'
                '`!dex hoenn` / `!dex gen 3` — Hoenn\n'
                '`!dex sinnoh` / `!dex gen 4` — Sinnoh\n'
                '`!dex unova` / `!dex gen 5` — Unova\n'
                '`!dex kalos` / `!dex gen 6` — Kalos\n'
                '`!dex alola` / `!dex gen 7` — Alola\n'
                '`!dex galar` / `!dex gen 8` — Galar\n'
                '`!dex paldea` / `!dex gen 9` — Paldea\n'
                '`!dex legendary` — Legendary Pokémon\n'
                '`!dex mythical` — Mythical Pokémon\n'
                '`!dex ultrabeast` — Ultra Beasts\n\n'
                '`!dex <pokemon name>` — Pokémon stats and info\n'
                'Each Pokédex page shows 25 entries. ✅ = registered; ⬜ = not registered.\n'
                'Use `!dex shiny` to see shiny Pokédex commands.'
            ))
            return await ctx.send(embed=e)
        if query.strip().lower() in ('shiny', 'shinies'):
            e=discord.Embed(title='✨ Shiny Pokédex Commands', color=discord.Color.gold(), description=(
                '`!dex shiny kanto` / `!dex shiny gen 1` — Kanto shinies\n'
                '`!dex shiny johto` / `!dex shiny gen 2` — Johto shinies\n'
                '`!dex shiny hoenn` / `!dex shiny gen 3` — Hoenn shinies\n'
                '`!dex shiny sinnoh` / `!dex shiny gen 4` — Sinnoh shinies\n'
                '`!dex shiny unova` / `!dex shiny gen 5` — Unova shinies\n'
                '`!dex shiny kalos` / `!dex shiny gen 6` — Kalos shinies\n'
                '`!dex shiny alola` / `!dex shiny gen 7` — Alola shinies\n'
                '`!dex shiny galar` / `!dex shiny gen 8` — Galar shinies\n'
                '`!dex shiny paldea` / `!dex shiny gen 9` — Paldea shinies\n'
                '`!dex shiny legendary` — Shiny Legendary Pokémon\n'
                '`!dex shiny mythical` — Shiny Mythical Pokémon\n'
                '`!dex shiny ultrabeast` — Shiny Ultra Beasts\n\n'
                '`!dex shiny <pokemon name>` — Shiny Pokémon stats and info\n'
                'Each Pokédex page shows 25 entries. ✅ = registered; ⬜ = not registered.'
            ))
            return await ctx.send(embed=e)
        tokens=query.split()
        shiny=False
        if tokens and tokens[0] in ('shiny','shinies'):
            shiny=True; tokens=tokens[1:]
        elif tokens and tokens[-1] in ('shiny','shinies'):
            shiny=True; tokens=tokens[:-1]
        key=' '.join(tokens).strip()
        gen_ranges={1:(1,151,'Kanto (Gen 1)'),2:(152,251,'Johto (Gen 2)'),3:(252,386,'Hoenn (Gen 3)'),4:(387,493,'Sinnoh (Gen 4)'),5:(494,649,'Unova (Gen 5)'),6:(650,721,'Kalos (Gen 6)'),7:(722,809,'Alola (Gen 7)'),8:(810,905,'Galar (Gen 8)'),9:(906,1025,'Paldea (Gen 9)')}
        region_aliases={'kanto':1,'johto':2,'hoenn':3,'sinnoh':4,'unova':5,'kalos':6,'alola':7,'galar':8,'paldea':9}
        if key in region_aliases: key=f'gen {region_aliases[key]}'
        if key.startswith('generation '): key='gen '+key.split()[-1]
        category_ids={
            'ultrabeast':{793,794,795,796,797,798,799,803,804,805,806},
            'mythical':set()
        }
        # Explicit National Dex lists for special species categories.
        category_ids['mythical']={151,251,385,386,489,490,491,492,493,494,647,648,649,719,720,721,801,802,807,808,809,1025}
        category_ids['legendary']={144,145,146,150,243,244,245,249,250,377,378,379,380,381,382,383,384,480,481,482,483,484,485,486,487,488}
        category_ids['legendary'].update({638,639,640,641,642,643,644,645,646,716,717,718,772,773,785,786,787,788,789,790,791,792,800,888,889,890,891,892,894,895,896,897,898,905,1001,1002,1003,1004,1007,1008,1012,1013,1024})
        valid_dex_query = key in ('', 'all', 'national', 'legendary', 'mythical', 'ultrabeast') or (key.startswith('gen ') and key[4:].isdigit())
        if not valid_dex_query:
            # Backward-compatible species lookup: !dex pikachu / !dex shiny pikachu.
            try:
                lookup=key.strip().replace(' ','-')
                d=await pokemon_data(lookup); s=stats(d)
                species_data=await api_get(f'/pokemon-species/{d["id"]}')
                gen=species_data.get('generation',{}).get('name','unknown-generation').replace('generation-', '').upper()
                gen_label={'I':'Generation I','II':'Generation II','III':'Generation III','IV':'Generation IV','V':'Generation V','VI':'Generation VI','VII':'Generation VII','VIII':'Generation VIII','IX':'Generation IX'}.get(gen, f'Generation {gen}')
                label=('✨ Shiny ' if shiny else '')+display_name(d)
                abilities=', '.join(a['ability']['name'].replace('-', ' ').title() + (' (Hidden)' if a.get('is_hidden') else '') for a in d.get('abilities',[])) or 'Unknown'
                e=discord.Embed(title=f'#{d["id"]} — {label}',description=f'**Type:** {type_text(d)}\n**BST:** {sum(s.values())}\n**Generation:** {gen_label}\n**Abilities:** {abilities}')
                for stat_key,stat_label in [('hp','❤️ HP'),('attack','⚔️ Attack'),('defense','🛡️ Defense'),('special-attack','✨ Sp. Atk'),('special-defense','🔰 Sp. Def'),('speed','💨 Speed')]: e.add_field(name=stat_label,value=str(s[stat_key]))
                art=sprite(d,shiny=shiny)
                if art: e.set_image(url=art)
                return await ctx.send(embed=e)
            except Exception:
                return await ctx.send('❌ Pokémon not found. Try `!dex pikachu`, `!dex shiny pikachu`, or `!pokedex pikachu`.')
        if key.startswith('gen ') and (not key[4:].isdigit() or int(key[4:]) not in gen_ranges):
            return await ctx.send('❌ Generation must be from 1 to 9.')
        try:
            if not POKEMON_LIST: await load_pokemon_list()
            species=[]
            for item in POKEMON_LIST:
                match=re.search(r'/pokemon-species/(\d+)/?$',item.get('url',''))
                if match:
                    dex_id=int(match.group(1))
                    if 1 <= dex_id <= 1025: species.append((dex_id,item['name']))
            species=sorted({i:n for i,n in species}.items())
            if not species: return await ctx.send('⚠️ I could not load the National Pokédex list. Please try again shortly.')
            title='National Pokédex'
            if key.startswith('gen '):
                lo,hi,title=gen_ranges[int(key[4:])]; species=[x for x in species if lo<=x[0]<=hi]
            elif key in ('legendary','mythical','ultrabeast'):
                ids=category_ids[key]; species=[x for x in species if x[0] in ids]; title={'ultrabeast':'Ultra Beasts','mythical':'Mythical Pokémon','legendary':'Legendary Pokémon'}[key]
            with db() as c:
                # Migrate old catches into the separate normal/shiny registries, without duplicates.
                c.execute('INSERT OR IGNORE INTO pokedex_entries(user_id,dex_id,name,shiny) SELECT user_id,dex_id,name,shiny FROM pokemon WHERE user_id=? AND dex_id BETWEEN 1 AND 1025',(ctx.author.id,))
                rows=c.execute('SELECT dex_id FROM pokedex_entries WHERE user_id=? AND shiny=?',(ctx.author.id,int(shiny))).fetchall()
            registered={int(r[0]) for r in rows}
            entries=[(i,n,i in registered) for i,n in species]
            count=sum(1 for _,_,caught in entries if caught)
            view=DexView(ctx.author.id,entries,shiny,title,count,len(entries))
            msg=await ctx.send(embed=view.make_embed(),view=view); view.message=msg
        except Exception as exc:
            print(f'Pokédex lookup failed for user {ctx.author.id}: {type(exc).__name__}: {exc}')
            await ctx.send('⚠️ Could not load your Pokédex right now. Please try again.')

    @commands.command(name='box',aliases=['pokemon','pc','storage'],description='View or sort your Pokémon collection.')
    async def box(self,ctx,category:str='all',*,pokemon_name:str=None):
        category=category.lower().replace('-', '').replace('_','')
        if category == 'name' and not pokemon_name:
            return await ctx.send('Usage: `!box name <pokemon>` — for example, `!box name Pikachu`.')
        aliases={'hl':'highlevel','highlevels':'highlevel','highlevelpokemon':'highlevel','maxhp':'hp','highesthp':'hp','condition':'status','statuscondition':'status','legendaries':'legendary','shinies':'shiny','ultrabeasts':'ultrabeast','injured':'damaged','notfullhp':'damaged','belowmaxhp':'damaged','helditems':'items','item':'items'}
        category=aliases.get(category,category)
        allowed={'all','hp','status','legendary','shiny','mythical','ultrabeast','damaged','items','highlevel','name'}
        if category not in allowed:
            return await ctx.send('❌ Unknown box category. Try: `!box all`, `!box hp`, `!box status`, `!box legendary`, `!box shiny`, `!box mythical`, `!box ultrabeast`, or `!box damaged`, or `!box items`, `!box highlevel` / `!box hl` (level above 50), or `!box name <pokemon>`.')
        with db() as c:
            rows=c.execute('SELECT box_id,dex_id,name,level,shiny,held_item,hp,max_hp,status_condition FROM pokemon WHERE user_id=? ORDER BY box_id',(ctx.author.id,)).fetchall()
        if not rows:return await ctx.send('📦 Your box is empty. Use `!hunt` to find Pokémon!')
        if category == 'name':
            wanted=pokemon_name.strip().lower().replace('-', ' ')
            rows=[r for r in rows if r[2].strip().lower().replace('-', ' ') == wanted]
            if not rows:
                return await ctx.send(f'❌ No Pokémon named **{pokemon_name.strip()}** found in your box. Check the spelling or run `!box` to browse your collection.')
        ultra_ids=set(range(793,807))
        if category=='items': rows=[r for r in rows if r[5]]
        elif category=='highlevel': rows=sorted([r for r in rows if (r[3] or 0)>50],key=lambda r:(r[3],r[2].lower()),reverse=True)
        elif category=='hp': rows=sorted(rows,key=lambda r:(r[7] or 0,r[6] or 0),reverse=True)
        elif category=='status': rows=[r for r in rows if r[8]]
        elif category=='shiny': rows=[r for r in rows if r[4]]
        elif category=='damaged': rows=[r for r in rows if (r[6] or 0)<(r[7] or 0)]
        elif category=='ultrabeast': rows=[r for r in rows if r[1] in ultra_ids]
        elif category in ('legendary','mythical'):
            filtered=[]
            for r in rows:
                try:
                    species=await api_get(f'/pokemon-species/{r[1]}')
                    if species.get('is_legendary' if category=='legendary' else 'is_mythical'): filtered.append(r)
                except Exception: continue
            rows=filtered
        if category=='items' and not rows:
            return await ctx.send('🎒 None of your Pokémon are holding items yet. Use `!giveitem <item> <pokemon_id>` to equip one.')
        entries=[(r[0],r[2],r[3],r[4],r[5],r[6],r[7],r[8],r[1]) for r in rows]
        await ensure_box_pokemon_emojis(ctx.guild, entries[:BoxView.ITEMS_PER_PAGE])
        view=BoxView(ctx.author.id,entries,category,ctx.guild)
        view.message=await ctx.send(embed=view.make_embed(),view=view)

    @commands.command(name='info',aliases=['pinfo','stats'],description="Show a Pokémon's current HP, stats and status conditions.")
    async def info(self,ctx,pokemon_id:Optional[int]=None):
        with db() as c:
            if pokemon_id is None:
                row=c.execute('SELECT p.instance_id,p.dex_id,p.name,p.level,p.shiny,p.hp,p.max_hp,p.held_item,p.status_condition FROM pokemon p JOIN team t ON t.instance_id=p.instance_id WHERE p.user_id=? ORDER BY CASE WHEN t.slot=1 THEN 0 ELSE 1 END,t.slot LIMIT 1',(ctx.author.id,)).fetchone()
            else:
                internal_id=resolve_box_id(c,ctx.author.id,pokemon_id)
                row=c.execute('SELECT instance_id,dex_id,name,level,shiny,hp,max_hp,held_item,status_condition FROM pokemon WHERE instance_id=? AND user_id=?',(internal_id,ctx.author.id)).fetchone() if internal_id else None
        if not row:
            return await ctx.send('❌ No Pokémon selected/found. Use `!select <ID>` first, or `!info <ID>`.')
        iid,dex_id,name,level,shiny,hp,maxhp,held,status=row
        with db() as c: display_iid=get_box_id(c,ctx.author.id,iid) or iid
        try:
            d=await pokemon_data(str(dex_id)); base=stats(d); types=type_text(d); abilities=', '.join(a['ability']['name'].replace('-',' ').title() for a in d.get('abilities',[])) or 'Unknown'
        except Exception:
            base={}; types='Unknown'; abilities='Unknown'; d=None
        hp=max(0,min(hp,maxhp)); maxhp=max(1,maxhp); ratio=hp/maxhp
        filled=max(0,min(10,round(ratio*10))); bar='▰'*filled+'▱'*(10-filled)
        e=discord.Embed(title=f'{"✨ Shiny " if shiny else ""}{name.replace("-"," ").title()} · Lv. {level}',description=f'**Pokémon ID:** `{display_iid}`\n**Type:** {types}\n**HP** `{hp}/{maxhp}`\n`{bar}` **{round(ratio*100)}%**',color=discord.Color.green() if ratio>.5 else discord.Color.orange() if hp>0 else discord.Color.dark_red())
        e.add_field(name='Battle Stats',value='\n'.join(f'**{label}:** {base.get(key,"?")}' for key,label in [('hp','HP Base'),('attack','Attack'),('defense','Defense'),('special-attack','Sp. Attack'),('special-defense','Sp. Defense'),('speed','Speed')]),inline=True)
        held_label=(ITEM_BY_KEY[held][2] if held in ITEM_BY_KEY else held.replace('-', ' ').title()) if held else 'None'
        e.add_field(name='Condition',value=f'**Status:** {(status or "healthy").replace("-"," ").title()}\n**Held item:** {item_emoji(held) + " " if held else ""}{held_label}\n**Ability:** {abilities}',inline=True)
        # Set art before move lookup, so move/API/DB errors cannot remove the Pokémon picture.
        if d:
            art = sprite(d, shiny=bool(shiny))
            if art:
                e.set_image(url=art)
        e.set_footer(text=f'Pokémon species / Pokédex ID: {dex_id} • Live collection data • !info defaults to your selected Pokémon')
        await ctx.send(embed=e)

    @commands.command(name='moves', aliases=['pmoves'], description="Show a Pokémon's saved Fast and Charged Moves.")
    async def moves(self, ctx, pokemon_id: Optional[int] = None):
        with db() as c:
            if pokemon_id is None:
                row = c.execute('SELECT * FROM pokemon WHERE user_id=? AND instance_id IN (SELECT instance_id FROM team WHERE user_id=? ORDER BY slot LIMIT 1)', (ctx.author.id, ctx.author.id)).fetchone()
            else:
                internal_id=resolve_box_id(c,ctx.author.id,pokemon_id)
                row = c.execute('SELECT * FROM pokemon WHERE instance_id=? AND user_id=?', (internal_id, ctx.author.id)).fetchone() if internal_id else None
        if not row:
            return await ctx.send('❌ Pokémon not found. Use `!moves <pokemon_id>` or add a Pokémon to your team first.')
        try:
            fast_display, charged_display = await saved_move_details(row, ctx.guild)
            # Read names from the saved row, then show useful battle stats for each move.
            with db() as c:
                saved = c.execute('SELECT fast_move, charged_move FROM pokemon WHERE instance_id=?', (row[0],)).fetchone()
            fast = await move_data(saved[0])
            charged = await move_data(saved[1])
        except Exception:
            return await ctx.send('❌ Could not load this Pokémon’s saved moves. Try again in a moment.')
        shiny = '✨ Shiny ' if row[6] else ''
        with db() as c: display_iid=get_box_id(c,ctx.author.id,row[0]) or row[0]
        name = str(row[3]).replace('-', ' ').title()
        description = (
            f"**Pokémon ID:** `{display_iid}`  •  **Level:** {row[4]}\n\n"
            f"⚡ **FAST MOVE**\n{fast_display}\n"
            f"{fast.get('power') if fast.get('power') is not None else '—'} base power  •  {fast.get('accuracy') or '—'}% accuracy\n\n"
            f"🔋 **CHARGED MOVE**\n{charged_display}\n"
            f"{charged.get('power') if charged.get('power') is not None else '—'} base power  •  {charged.get('accuracy') or '—'}% accuracy"
        )
        embed = discord.Embed(title=f'{shiny}{name} · Move Set', description=description, color=discord.Color.blurple())
        embed.add_field(name='Battle flow', value='Use **Fast Move twice** to charge your attack. Then the Fast Move locks and the **Charged Move** becomes available. Using the Charged Move resets the cycle.', inline=False)
        embed.add_field(name='Changing moves', value='Your moves are saved permanently for this Pokémon. They only change when you use a matching TM: `!usetm fast-tm <pokemon_id>` or `!usetm charged-tm <pokemon_id>`. Elite Charged TM lets you choose the new Charged Move.', inline=False)
        try:
            d = await pokemon_data(str(row[2]))
            image_url = sprite(d, shiny=bool(row[6]))
            if image_url: embed.set_thumbnail(url=image_url)
            embed.add_field(name='Type', value=type_text(d), inline=True)
        except Exception:
            pass
        embed.set_footer(text='Saved moves • !moves defaults to your team lead')
        await ctx.send(embed=embed)

    @commands.command(name='pokemonadd',aliases=['pokeadd'])
    async def pokemonadd(self,ctx,member:discord.Member,*,pokemon_name:str):
        if ctx.author.id not in OWNER_IDS:
            return
        shiny=pokemon_name.lower().replace(' ','').startswith('shiny')
        lookup=pokemon_name[5:] if shiny else pokemon_name
        lookup=lookup.strip().lower().replace(' ','-')
        try:
            d=await pokemon_data(lookup)
        except Exception:
            return await ctx.send('❌ Pokémon not found. Example: `!pokemonadd @user shinyeternatus`')
        mh=max_hp(d,50); label=('✨ Shiny ' if shiny else '')+display_name(d)
        # Admin Pokémon-add confirmations stay available until confirmed or cancelled.
        view=TimedView(timeout=None, timeout_text='')
        yes=discord.ui.Button(label='Confirm add',style=discord.ButtonStyle.success)
        no=discord.ui.Button(label='Cancel',style=discord.ButtonStyle.danger)
        async def confirm(interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message('Only the command user can confirm this.',ephemeral=True)
            if interaction.data.get('custom_id') == 'pokemonadd_cancel':
                await interaction.response.edit_message(content='❎ Addition cancelled.',embed=None,view=None); return
            with db() as c:
                cur=c.execute('INSERT INTO pokemon(user_id,dex_id,name,level,shiny,hp,max_hp) VALUES(?,?,?,?,?,?,?)',(member.id,d['id'],d['name'],50,int(shiny),mh,mh)); iid=cur.lastrowid; assign_box_id(c,member.id,iid)
                if not c.execute('SELECT 1 FROM team WHERE user_id=?',(member.id,)).fetchone(): c.execute('INSERT OR REPLACE INTO team(user_id,slot,instance_id) VALUES(?,?,?)',(member.id,1,iid))
            await interaction.response.edit_message(content=f'✅ Added **{label}** to {member.mention} (ID `{get_box_id(c,member.id,iid)}`).',embed=None,view=None)
        async def yes_cb(interaction):
            if interaction.user.id != ctx.author.id: return await interaction.response.send_message('Only the command user can confirm this.',ephemeral=True)
            with db() as c:
                cur=c.execute('INSERT INTO pokemon(user_id,dex_id,name,level,shiny,hp,max_hp) VALUES(?,?,?,?,?,?,?)',(member.id,d['id'],d['name'],50,int(shiny),mh,mh)); iid=cur.lastrowid; assign_box_id(c,member.id,iid)
                if not c.execute('SELECT 1 FROM team WHERE user_id=?',(member.id,)).fetchone(): c.execute('INSERT OR REPLACE INTO team(user_id,slot,instance_id) VALUES(?,?,?)',(member.id,1,iid))
            await interaction.response.edit_message(content=f'✅ Added **{label}** to {member.mention} (ID `{get_box_id(c,member.id,iid)}`).',embed=None,view=None)
        async def no_cb(interaction):
            if interaction.user.id != ctx.author.id: return await interaction.response.send_message('Only the command user can cancel this.',ephemeral=True)
            await interaction.response.edit_message(content='❎ Addition cancelled.',embed=None,view=None)
        yes.callback=yes_cb; no.callback=no_cb; view.add_item(yes); view.add_item(no)
        art=sprite(d,shiny=shiny); embed=discord.Embed(title='Confirm Pokémon addition',description=f'Add **{label}** Lv. 50 to {member.mention}?')
        if art: embed.set_image(url=art)
        view.message=await ctx.send(embed=embed,view=view)

    @commands.command(name='shinyhunt', aliases=['spawnshiny','shinyspawn'])
    async def shinyhunt(self, ctx, *, pokemon_name: str = None):
        """Owner-only: spawn a random shiny, or specify one; first correct server guess wins."""
        if ctx.author.id not in OWNER_IDS:
            return

        # No name supplied = choose a random Pokémon. A name supplied = spawn that one.
        if pokemon_name and pokemon_name.strip():
            lookup=pokemon_name.strip().lower().replace(' ', '-').removeprefix('shiny-')
            try:
                d=await pokemon_data(lookup)
            except Exception:
                return await ctx.send('❌ Pokémon not found. Use `!shinyhunt` for a random shiny or `!shinyhunt eternatus` for a specific one.')
        else:
            try:
                d=await random_pokemon()
            except Exception as e:
                return await ctx.send(f'❌ Could not choose a random Pokémon: `{e}`')

        lvl=random.randint(3,20)
        with db() as c:
            existing=c.execute('SELECT name FROM global_encounter WHERE id=1').fetchone()
            if existing:
                return await ctx.send(f'⚠️ A server-wide shiny (**{existing[0].title()}**) is already active. Let someone catch it first!')
            c.execute('INSERT INTO global_encounter(id,dex_id,name,shiny,level,spawned_by) VALUES(1,?,?,1,?,?)', (d['id'],d['name'],lvl,ctx.author.id))
        embed=discord.Embed(title='✨ A SERVER-WIDE SHINY Pokémon appeared!', description=f'**A wild shiny appeared!**\n**Level:** {lvl}\n**Type:** ???\n\nLook at the artwork and guess its name with `!catch <pokemon name>`.\n💰 First correct guess wins and gets **50 {get_vantacoin_emoji()} VantaCoins**. Only one user can catch it!')
        art=sprite(d,shiny=True)
        if art: embed.set_image(url=art)
        await ctx.send(embed=embed)

    @commands.command(name='setteam',aliases=['teamset','slotteam'],description='Set a Pokémon into team slot 1-6.')
    async def setteam(self,ctx,pokemon_id:int,slot:int):
        if slot not in range(1,7):return await ctx.send('❌ Slot must be 1-6.')
        with db() as c: pokemon_id=resolve_box_id(c,ctx.author.id,pokemon_id)
        if pokemon_id is None:return await ctx.send('❌ That Pokémon ID is not yours. Use `!box` to check your personal IDs.')
        with db() as c:r=c.execute('SELECT 1 FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,ctx.author.id)).fetchone()
        if not r:return await ctx.send('❌ That Pokémon ID is not yours.')
        with db() as c:c.execute('INSERT OR REPLACE INTO team VALUES(?,?,?)',(ctx.author.id,slot,pokemon_id))
        await ctx.send(f'✅ Team slot {slot} updated.')
    @commands.command(name='select',aliases=['s','sel'],description='Select one of your Pokémon as your active battle Pokémon.')
    async def select(self,ctx,pokemon_id:Optional[int]=None):
        if pokemon_id is None:return await ctx.send('Usage: `!select <id>` — use `!box` to see your Pokémon IDs.')
        with db() as c: pokemon_id=resolve_box_id(c,ctx.author.id,pokemon_id)
        if pokemon_id is None:return await ctx.send('❌ That Pokémon ID is not in your collection. Check `!box`.')
        with db() as c: row=c.execute('SELECT instance_id,name,level,hp,max_hp,shiny FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,ctx.author.id)).fetchone()
        if not row:return await ctx.send('❌ That Pokémon ID is not in your collection. Check `!box`.')
        with db() as c:c.execute('INSERT OR REPLACE INTO team(user_id,slot,instance_id) VALUES(?,?,?)',(ctx.author.id,1,pokemon_id))
        shiny_marker = '✨ ' if bool(row[5]) else ''
        await ctx.send(f'✅ Selected {shiny_marker}**{row[1].replace(chr(45), chr(32)).title()}** Lv. {row[2]} (ID `{pokemon_id}`) as your active battle Pokémon.')

    @commands.command(name='team',aliases=['myteam','tm'],description='Show or edit your team.')
    async def team(self,ctx,action:Optional[str]=None,pokemon_id:Optional[int]=None,slot:Optional[int]=None):
        action=(action or 'show').lower()
        if action in ('add','remove') and pokemon_id is not None:
            with db() as c: pokemon_id=resolve_box_id(c,ctx.author.id,pokemon_id)
            if pokemon_id is None:return await ctx.send('❌ That Pokémon ID is not yours. Check `!box`.')
        if action=='add':
            if pokemon_id is None or slot is None:return await ctx.send('Usage: `!team add <pokemon_id> <slot>`')
            if slot not in range(1,7):return await ctx.send('❌ Slot must be 1-6.')
            with db() as c:
                owned=c.execute('SELECT 1 FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,ctx.author.id)).fetchone()
                if not owned:return await ctx.send('❌ That Pokémon ID is not yours.')
                c.execute('DELETE FROM team WHERE user_id=? AND instance_id=?',(ctx.author.id,pokemon_id))
                c.execute('INSERT OR REPLACE INTO team(user_id,slot,instance_id) VALUES(?,?,?)',(ctx.author.id,slot,pokemon_id))
            return await ctx.send(f'✅ Added Pokémon ID `{pokemon_id}` to team slot **{slot}**.')
        if action=='remove':
            if pokemon_id is None:return await ctx.send('Usage: `!team remove <pokemon_id>`')
            with db() as c: cur=c.execute('DELETE FROM team WHERE user_id=? AND instance_id=?',(ctx.author.id,pokemon_id))
            return await ctx.send('✅ Pokémon removed from your team.' if cur.rowcount else '❌ That Pokémon is not in your team.')
        if action not in ('show','list','view'):return await ctx.send('Use `!team`, `!team add <pokemon_id> <slot>`, or `!team remove <pokemon_id>`.')
        with db() as c:r=c.execute('SELECT t.slot,p.box_id,p.name,p.level,p.shiny,p.hp,p.max_hp FROM team t JOIN pokemon p ON p.instance_id=t.instance_id WHERE t.user_id=? ORDER BY t.slot',(ctx.author.id,)).fetchall()
        embed=discord.Embed(title=f'🎒 {ctx.author.display_name}’s Team',description=('\n'.join(f'**Slot {x[0]}** · ID `{x[1]}` · {"✨ " if x[4] else ""}**{x[2].title()}** Lv.{x[3]}\n{hp_bar(x[5],x[6])}' for x in r) if r else 'Your team is empty. Use `!setteam <pokemon_id> <slot>` to add Pokémon.'),color=discord.Color.blurple())
        embed.set_footer(text=f'{len(r)}/6 slots filled • Pokémon level cap: 300')
        await ctx.send(embed=embed)

    @commands.command(name='usetm',aliases=['tmuse'])
    async def usetm(self,ctx,tm:str,pokemon_id:int,*,chosen_move:Optional[str]=None):
        public_box_id=pokemon_id
        pid=resolve_shop_product(tm)
        with db() as c: pokemon_id=resolve_box_id(c,ctx.author.id,pokemon_id)
        if pokemon_id is None:return await ctx.send('❌ That Pokémon ID is not yours. Check `!box`.')
        if pid not in (52,53,54):return await ctx.send('Usage: `!usetm fast-tm|charged-tm|elite-charged-tm <pokemon_id> [move name]`')
        item=SHOP_ITEMS[pid][0]
        with db() as c:
            row=c.execute('SELECT * FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,ctx.author.id)).fetchone()
            inv=c.execute('SELECT amount FROM inventory WHERE user_id=? AND item=?',(ctx.author.id,item)).fetchone()
            if not row:return await ctx.send('❌ That Pokémon ID is not yours.')
            if not inv or inv[0]<1:return await ctx.send(f'❌ You do not have a {SHOP_ITEMS[pid][1]}. Buy one with `!shop buy {item}`.')
        fast=pid==52; pool=await move_pool(row[2],fast=fast)
        if pid==54: pool=await move_pool(row[2],fast=False)
        if chosen_move:
            target=chosen_move.lower().replace(' ','-')
            selected=next((m for m in pool if m['name'].lower()==target),None)
            if not selected:return await ctx.send('❌ That move is not available in this Pokémon’s move pool.')
        else:selected=random.choice(pool)
        column='fast_move' if fast else 'charged_move'
        with db() as c:
            c.execute('UPDATE pokemon SET '+column+'=? WHERE instance_id=?',(selected['name'],pokemon_id))
            c.execute('UPDATE inventory SET amount=amount-1 WHERE user_id=? AND item=?',(ctx.author.id,item))
            c.execute('DELETE FROM inventory WHERE user_id=? AND item=? AND amount<=0',(ctx.author.id,item))
        return await ctx.send(f'✅ **{row[3].title()}** learned **{selected["name"].replace("-"," ").title()}** using {SHOP_ITEMS[pid][1]}.')
    @commands.command(name='battle',aliases=['fight','b'],description='Battle an NPC with move buttons.')
    async def battle(self,ctx):
        if isinstance(ACTIVE_VIEWS.get(ctx.author.id), (NPCBattleView, PvPBattle)):
            return await ctx.send('⚠️ You already have an active battle. Finish it or use `!cancel` first.')
        row=await owned_lead(ctx.author.id)
        if not row:return await ctx.send('❌ Catch a Pokémon and put it in your team with `!setteam ID 1`.')
        if row[8]<=0:return await ctx.send('❌ Your lead is fainted. Use `!useitem Potion <pokemon_id>` or a healing berry.')
        enemy=await random_pokemon(); low=max(3,min(50,row[4]-2)); high=max(low,min(50,row[4]+3)); enemy['_level']=random.randint(low,high);v=NPCBattleView(ctx.author.id,row,enemy);await v.build();own_data=await pokemon_data(row[2])
        e=discord.Embed(title=f'⚔️ Pokémon Battle Arena — {row[3].title()} vs {display_name(enemy)}',description=f'''🔴 **Your Pokémon:** {row[3].title()} Lv. {row[4]}
HP {hp_bar(row[8],row[9])}

🔵 **Opponent:** {display_name(enemy)} Lv. {enemy['_level']}
HP {hp_bar(v.enemy_hp,max_hp(enemy,enemy['_level']))}
Type: **{type_text(enemy)}**

Click **Choose Move**. Your move options are private, just like trainer challenges.''')
        e.color=discord.Color.red()
        if sprite(own_data,shiny=bool(row[6])):e.set_thumbnail(url=sprite(own_data,shiny=bool(row[6])))
        if sprite(enemy):e.set_image(url=sprite(enemy))
        v.message=await ctx.send(embed=e,view=v); ACTIVE_VIEWS[ctx.author.id]=v
    @commands.command(name='challenge',aliases=['pvp','duel','chall'],description='Challenge another trainer to a PvP battle.')
    async def challenge(self,ctx,opponent:discord.Member):
        if opponent.bot or opponent.id==ctx.author.id:return await ctx.send('❌ Choose another human trainer.')
        if opponent.id in self.challenges or ctx.author.id in self.challenges:return await ctx.send('❌ One of you is already in a challenge.')
        ra,rb=await owned_lead(ctx.author.id),await owned_lead(opponent.id)
        if not ra or not rb:return await ctx.send('❌ Both trainers need a Pokémon in team slot 1.')
        if ra[8]<=0 or rb[8]<=0:return await ctx.send('❌ Both lead Pokémon must have HP.')
        self.challenges[ctx.author.id]=opponent.id;self.challenges[opponent.id]=ctx.author.id
        view=TimedView(timeout=30, timeout_text='⏰ Challenge timed out.');accept=discord.ui.Button(label='Accept Battle',style=discord.ButtonStyle.success);decline=discord.ui.Button(label='Decline',style=discord.ButtonStyle.danger);view.add_item(accept);view.add_item(decline)
        async def challenge_timeout():
            self.challenges.pop(ctx.author.id,None);self.challenges.pop(opponent.id,None)
            ACTIVE_VIEWS.pop(ctx.author.id,None);ACTIVE_VIEWS.pop(opponent.id,None)
            await TimedView.on_timeout(view)
        view.on_timeout=challenge_timeout
        async def acc(i):
            if i.user.id!=opponent.id:return await i.response.send_message('Only the challenged player can accept.',ephemeral=True)
            # Acknowledge before move data/sprite lookups, which can take longer than Discord's 3-second limit.
            await i.response.defer()
            view.stop()
            self.challenges.pop(ctx.author.id,None);self.challenges.pop(opponent.id,None)
            p=PvPBattle(ctx.author.id,opponent.id,ra,rb)
            try:
                await p.setup()
                pv=p.view()
                p.message=i.message;pv.message=i.message
                await i.edit_original_response(content=None,embed=await p.make_embed(),view=pv)
                ACTIVE_VIEWS[ctx.author.id]=p;ACTIVE_VIEWS[opponent.id]=p
            except Exception as exc:
                print(f'PvP challenge acceptance failed: {exc!r}')
                ACTIVE_VIEWS.pop(ctx.author.id,None);ACTIVE_VIEWS.pop(opponent.id,None)
                try:
                    await i.edit_original_response(content='⚠️ The battle could not load right now. Please run `!pvp @user` again.',embed=None,view=None)
                except Exception as update_exc:
                    print(f'PvP challenge recovery update failed: {update_exc!r}')
        async def dec(i):
            if i.user.id!=opponent.id:return await i.response.send_message('Only the challenged player can decline.',ephemeral=True)
            view.stop()
            self.challenges.pop(ctx.author.id,None);self.challenges.pop(opponent.id,None);ACTIVE_VIEWS.pop(ctx.author.id,None);ACTIVE_VIEWS.pop(opponent.id,None);await i.response.edit_message(content='❌ Challenge declined.',view=None)
        accept.callback=acc;decline.callback=dec
        view.message=await ctx.send(f'⚔️ <@{ctx.author.id}> challenged <@{opponent.id}> to a Pokémon battle!\n⏳ They have 30 seconds to accept or decline. After acceptance, the battle stays active until it ends or is cancelled.',view=view); ACTIVE_VIEWS[ctx.author.id]=view; ACTIVE_VIEWS[opponent.id]=view
    @commands.command(name='shop',aliases=['store'],description='Browse the item shop or buy items by name, shortform, or ID.')
    async def shop(self,ctx,action:Optional[str]=None,*,product:Optional[str]=None):
        if action and action.lower()=='buy':
            if not product:
                return await ctx.send('Usage: `!shop buy <item name|shortform|id>`\nExamples: `!shop buy Oran Berry`, `!shop buy ora1`, `!shop buy 1`')
            quantity=1
            bits=product.rsplit(maxsplit=1)
            if len(bits)==2 and bits[1].isdigit(): product,quantity=bits[0],int(bits[1])
            if quantity<1 or quantity>1000:return await ctx.send('❌ Quantity must be between 1 and 1000.')
            product_id=resolve_shop_product(product)
            if product_id is None:
                return await ctx.send(f'❌ I could not find **{product}**. Use `!shop` to see item names, unique shortforms, and IDs.')
            key,label,cost,desc,shortform=SHOP_ITEMS[product_id]; total=cost*quantity
            try:
                with db() as c:
                    c.execute('BEGIN IMMEDIATE')
                    row=c.execute('SELECT coins FROM players WHERE user_id=?',(ctx.author.id,)).fetchone()
                    balance_before=row[0] if row else 0
                    if balance_before < total:
                        c.rollback()
                        return await ctx.send(f'❌ {item_emoji(key)} **{label} ×{quantity}** costs {total:,} {get_vantacoin_emoji()} VantaCoins, but you have {balance_before:,}.')
                    c.execute('UPDATE players SET coins=coins-? WHERE user_id=?',(total,ctx.author.id))
                    c.execute('INSERT INTO inventory(user_id,item,amount) VALUES(?,?,?) ON CONFLICT(user_id,item) DO UPDATE SET amount=amount+excluded.amount',(ctx.author.id,key,quantity))
                    balance=balance_before-total
                    c.commit()
            except Exception as exc:
                print(f'Shop purchase failed for user {ctx.author.id}, product {product_id}: {exc!r}')
                return await ctx.send('❌ Purchase failed. Please try again; if it repeats, send the Termux error.')
            consumable = ('berry' in key) or key in {'potion','super-potion','hyper-potion','max-potion','full-restore'}
            howto = f'Use `!useitem {shortform} <pokemon_id>`' if consumable else f'Equip with `!giveitem {shortform} <pokemon_id>`'
            return await ctx.send(f'🛒 **Purchase successful!**\nBought {item_emoji(key)} **{label} ×{quantity}** for **{total:,} {get_vantacoin_emoji()} VantaCoins**.\n🎒 Added to your inventory. Shortform: `{shortform}`.\n💰 Remaining balance: **{balance:,} {get_vantacoin_emoji()} VantaCoins**.\n{howto}.')
        if action and action.lower() in ('sell','sellback'):
            if not product:
                return await ctx.send('Usage: `!market sell <item name|shortform|id> [quantity]`')
            quantity=1
            bits=product.rsplit(maxsplit=1)
            if len(bits)==2 and bits[1].isdigit(): product,quantity=bits[0],int(bits[1])
            if quantity<1 or quantity>1000:
                return await ctx.send('❌ Quantity must be between 1 and 1000.')
            product_id=resolve_shop_product(product)
            if product_id is None:
                return await ctx.send(f'❌ I could not find **{product}**. Use `!market` to browse the market.')
            key,label,cost,desc,shortform=SHOP_ITEMS[product_id]
            payout=max(1, cost//2)*quantity
            try:
                with db() as c:
                    c.execute('BEGIN IMMEDIATE')
                    row=c.execute('SELECT amount FROM inventory WHERE user_id=? AND item=?',(ctx.author.id,key)).fetchone()
                    owned=int(row[0]) if row else 0
                    if owned < quantity:
                        c.rollback()
                        return await ctx.send(f'❌ You only have **{owned}× {label}** to sell.')
                    if owned == quantity:
                        c.execute('DELETE FROM inventory WHERE user_id=? AND item=?',(ctx.author.id,key))
                    else:
                        c.execute('UPDATE inventory SET amount=amount-? WHERE user_id=? AND item=?',(quantity,ctx.author.id,key))
                    c.execute('UPDATE players SET coins=coins+? WHERE user_id=?',(payout,ctx.author.id))
                    c.commit()
            except sqlite3.Error:
                return await ctx.send('❌ Sale failed. Please try again.')
            e=discord.Embed(title='💎 Vanta Market — Sale Complete', description=f'Sold {item_emoji(key)} **{label} ×{quantity}** for **{payout:,} {get_vantacoin_emoji()} VantaCoins**.', color=discord.Color.green())
            e.set_footer(text='Market resale value: 50% of the listed purchase price.')
            return await ctx.send(embed=e)
        category = 'all'
        if action and action.lower() == 'view':
            requested = (product or 'all').strip().lower().replace('-', ' ').replace('_', ' ')
            aliases = {
                'all':'all', 'any':'all', 'ally':'all', 'everything':'all',
                'berry':'berries', 'berries':'berries', 'berrys':'berries',
                'potion':'potions', 'potions':'potions',
                'held':'held', 'held item':'held', 'held items':'held', 'items':'held', 'equipment':'held'
            }
            category = aliases.get(requested)
            if category is None:
                return await ctx.send('❌ Category not found. Use `!shop view berries`, `!shop view potions`, `!shop view held`, or `!shop view all`.')
        view=ShopView(ctx.author.id, category, guild=ctx.guild)
        view.message=await ctx.send(embed=view.make_embed(),view=view)

    @commands.command(name='market', aliases=['m','trademarket','globaltrade'], description='List, browse, buy, or sell Pokémon on the Vanta global market.')
    async def market(self, ctx, action: Optional[str] = None, *, details: Optional[str] = None):
        """PokéMeow-inspired player-to-player Pokémon listings market."""
        with db() as c:
            c.execute("CREATE TABLE IF NOT EXISTS market_listings (listing_id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER NOT NULL, pokemon_id INTEGER NOT NULL, pokemon_name TEXT NOT NULL, price INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active', buyer_id INTEGER, proceeds INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL DEFAULT 0)")
            cols={r[1] for r in c.execute('PRAGMA table_info(market_listings)').fetchall()}
            if 'shiny' not in cols: c.execute('ALTER TABLE market_listings ADD COLUMN shiny INTEGER NOT NULL DEFAULT 0')
            if 'level' not in cols: c.execute('ALTER TABLE market_listings ADD COLUMN level INTEGER NOT NULL DEFAULT 1')
        action = (action or '').lower().strip()
        details = (details or '').strip()
        if not action:
            e=discord.Embed(title='🌐 Vanta Global Market',description='Trade Pokémon with other trainers using VantaCoins.',color=discord.Color.blurple())
            e.add_field(name='🔎 Browse',value='`!market view recent`\n`!market view <Pokémon name>`\n`!market view user @user`',inline=False)
            e.add_field(name='💰 List a Pokémon',value='`!market offer <Pokémon ID> <price>`\nExample: `!market offer 12 2500`',inline=False)
            e.add_field(name='🛒 Buy / your listings',value='`!market buy <listing ID>`\n`!market listings`',inline=True)
            e.add_field(name='↩️ Remove / claim',value='`!market remove <listing ID>`\n`!market claim <listing ID>`\n`!m claim all`',inline=True)
            e.set_footer(text='5% market fee applies when claiming sold listings. Use !shop for items.')
            return await ctx.send(embed=e)
        if action == 'offer':
            bits=details.split()
            if len(bits)!=2 or not all(x.isdigit() for x in bits): return await ctx.send('Usage: `!market offer <Pokémon ID> <price>`')
            pokemon_id,price=map(int,bits)
            if price<1 or price>2_000_000_000: return await ctx.send('❌ Price must be between 1 and 2,000,000,000 VantaCoins.')
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                requested_id=pokemon_id; pokemon_id=resolve_box_id(c,ctx.author.id,requested_id)
                mon=c.execute('SELECT instance_id,name,level,shiny,nickname,held_item FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,ctx.author.id)).fetchone() if pokemon_id else None
                if not mon: c.rollback(); return await ctx.send('❌ That Pokémon ID is not yours. Use `!box` to find its ID.')
                if mon[5]: c.rollback(); return await ctx.send('❌ Remove its held item before listing this Pokémon.')
                for table in ('team','boss_party','raid_party'): c.execute(f'DELETE FROM {table} WHERE instance_id=?',(pokemon_id,))
                transfer_pokemon_owner(c,pokemon_id,ctx.author.id,0)
                cur=c.execute("INSERT INTO market_listings(seller_id,pokemon_id,pokemon_name,price,status,created_at,shiny,level) VALUES(?,?,?,?,'active',?,?,?)",(ctx.author.id,pokemon_id,mon[1],price,int(time.time()),int(mon[3]),int(mon[2])))
                lid=cur.lastrowid; c.commit()
            shiny='✨ Shiny ' if mon[3] else ''
            e=discord.Embed(title='📦 Pokémon listed successfully!',description=f'{shiny}**{mon[1].title()}** (Lv. {mon[2]}) is now on the global market.',color=discord.Color.green())
            e.add_field(name='Listing ID',value=f'`{lid}`',inline=True); e.add_field(name='Asking price',value=f'**{price:,}** {get_vantacoin_emoji()} VantaCoins',inline=True)
            e.set_footer(text='The Pokémon is held safely by the market until purchased or removed.')
            return await ctx.send(embed=e)
        if action in ('view','browse','search'):
            if not details or details.lower()=='recent':
                with db() as c: rows=c.execute("SELECT listing_id,seller_id,pokemon_name,price,shiny,level FROM market_listings WHERE status='active' ORDER BY listing_id DESC LIMIT 10").fetchall()
                title='🆕 Recent Pokémon Listings'
            elif details.lower().startswith('user '):
                target=ctx.message.mentions[0].id if ctx.message.mentions else None
                if target is None:
                    val=details[5:].strip().strip('<@!>')
                    if val.isdigit(): target=int(val)
                if target is None: return await ctx.send('Usage: `!market view user @user`')
                with db() as c: rows=c.execute("SELECT listing_id,seller_id,pokemon_name,price,shiny,level FROM market_listings WHERE status='active' AND seller_id=? ORDER BY listing_id DESC LIMIT 10",(target,)).fetchall()
                title=f'🧑‍💼 Active listings by <@{target}>'
            else:
                with db() as c: rows=c.execute("SELECT listing_id,seller_id,pokemon_name,price,shiny,level FROM market_listings WHERE status='active' AND lower(pokemon_name) LIKE ? ORDER BY listing_id DESC LIMIT 10",(f'%{details.lower()}%',)).fetchall()
                title=f'🔎 Market search: {details[:80]}'
            e=discord.Embed(title=title,color=discord.Color.blurple())
            e.description='\n\n'.join(f'{"✨ " if shiny else ""}**#{lid} · {name.replace("-", " " ).title()}** · Lv. **{level}** — **{price:,}** {get_vantacoin_emoji()}\nSeller: <@{seller}> · `!market buy {lid}`' for lid,seller,name,price,shiny,level in rows) if rows else 'No active listings found. Try `!market view recent`.'
            e.set_footer(text='Showing up to 10 active listings.')
            return await ctx.send(embed=e,allowed_mentions=discord.AllowedMentions(users=True))
        if action in ('listings','offers'):
            with db() as c: rows=c.execute("SELECT listing_id,pokemon_name,price,status FROM market_listings WHERE seller_id=? AND status IN ('active','sold') ORDER BY listing_id DESC LIMIT 15",(ctx.author.id,)).fetchall()
            e=discord.Embed(title=f'📋 {ctx.author.display_name}’s Market Listings',color=discord.Color.blurple())
            with db() as c:
                shiny_map={int(r[0]):bool(r[1]) for r in c.execute("SELECT listing_id,shiny FROM market_listings WHERE seller_id=? AND status IN ('active','sold')",(ctx.author.id,)).fetchall()}
            e.description='\n\n'.join(((f'✨ ' if shiny_map.get(int(lid),False) else '') + (f'**#{lid} · {name.replace(chr(45), chr(32)).title()}** — {price:,} coins · Active\nRemove: `!market remove {lid}`' if status=='active' else f'**#{lid} · {name.replace(chr(45), chr(32)).title()}** — Sold · Claim: `!market claim {lid}`')) for lid,name,price,status in rows) if rows else 'You have no active or unclaimed sold listings.'
            return await ctx.send(embed=e)
        if action=='buy':
            if not details.isdigit() or int(details)<1: return await ctx.send('Usage: `!market buy <listing ID>`')
            lid=int(details)
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                listing=c.execute("SELECT seller_id,pokemon_id,pokemon_name,price,shiny FROM market_listings WHERE listing_id=? AND status='active'",(lid,)).fetchone()
                if not listing: c.rollback(); return await ctx.send('❌ That listing is no longer available.')
                seller,pokemon_id,pname,price,listing_shiny=listing
                if seller==ctx.author.id: c.rollback(); return await ctx.send('❌ You cannot buy your own listing. Use `!market remove {lid}`.')
                row=c.execute('SELECT coins FROM players WHERE user_id=?',(ctx.author.id,)).fetchone(); balance=int(row[0]) if row else 0
                if balance<price: c.rollback(); return await ctx.send(f'❌ Not enough balance. Price: **{price:,}** coins; your balance: **{balance:,}**.')
                if not c.execute('SELECT 1 FROM pokemon WHERE instance_id=? AND user_id=0',(pokemon_id,)).fetchone(): c.rollback(); return await ctx.send('❌ Listing could not be verified. Please contact an administrator.')
                c.execute('UPDATE players SET coins=coins-? WHERE user_id=?',(price,ctx.author.id))
                new_box_id=transfer_pokemon_owner(c,pokemon_id,0,ctx.author.id)
                c.execute("UPDATE market_listings SET status='sold',buyer_id=?,proceeds=? WHERE listing_id=? AND status='active'",(ctx.author.id,price,lid)); c.commit()
            e=discord.Embed(title='🎉 Market purchase successful!',description=f'{ctx.author.mention} bought {"✨ " if listing_shiny else ""}**{pname.replace('-', ' ').title()}** from <@{seller}>!',color=discord.Color.green())
            e.add_field(name='Paid',value=f'**{price:,}** {get_vantacoin_emoji()} VantaCoins',inline=True); e.add_field(name='Pokémon ID',value=f'`{new_box_id}`',inline=True)
            e.set_footer(text=f'Listing #{lid} · Seller can claim proceeds with !market claim {lid}')
            return await ctx.send(embed=e,allowed_mentions=discord.AllowedMentions(users=True))
        if action=='remove':
            if not details.isdigit(): return await ctx.send('Usage: `!market remove <listing ID>`')
            lid=int(details)
            with db() as c:
                c.execute('BEGIN IMMEDIATE'); row=c.execute("SELECT pokemon_id,pokemon_name,shiny FROM market_listings WHERE listing_id=? AND seller_id=? AND status='active'",(lid,ctx.author.id)).fetchone()
                if not row: c.rollback(); return await ctx.send('❌ No active listing with that ID belongs to you.')
                pokemon_id,pname,listing_shiny=row; transfer_pokemon_owner(c,pokemon_id,0,ctx.author.id); c.execute("UPDATE market_listings SET status='removed' WHERE listing_id=?",(lid,)); c.commit()
            return await ctx.send(embed=discord.Embed(title='↩️ Listing removed',description=f'{"✨ " if listing_shiny else ""}**{pname.replace('-', ' ').title()}** has been returned to your collection.',color=discord.Color.orange()))
        if action=='claim':
            if details.lower()=='all':
                with db() as c:
                    c.execute('BEGIN IMMEDIATE')
                    rows=c.execute("SELECT listing_id,proceeds,pokemon_name,shiny FROM market_listings WHERE seller_id=? AND status='sold' ORDER BY listing_id",(ctx.author.id,)).fetchall()
                    if not rows:
                        c.rollback(); return await ctx.send('❌ You have no sold listings to claim.')
                    gross=sum(max(0,int(r[1])) for r in rows); fee=(gross*5)//100; payout=gross-fee
                    ids=[int(r[0]) for r in rows]
                    c.execute('UPDATE players SET coins=coins+? WHERE user_id=?',(payout,ctx.author.id))
                    c.executemany("UPDATE market_listings SET status='claimed',proceeds=0 WHERE listing_id=? AND seller_id=? AND status='sold'",[(lid,ctx.author.id) for lid in ids])
                    c.commit()
                names=', '.join((('✨ ' if shiny else '')+name.replace('-', ' ').title()) for _,_,name,shiny in rows[:5])
                if len(rows)>5: names+=f' and {len(rows)-5} more'
                e=discord.Embed(title='💰 All Market Proceeds Claimed!',description=f'Claimed **{len(rows)}** sold listing(s): {names}.',color=discord.Color.green())
                e.add_field(name='Total sale value',value=f'{gross:,} coins',inline=True); e.add_field(name='Market fee (5%)',value=f'{fee:,} coins',inline=True); e.add_field(name='You received',value=f'**{payout:,}** {get_vantacoin_emoji()} VantaCoins',inline=True)
                return await ctx.send(embed=e)
            if not details.isdigit(): return await ctx.send('Usage: `!m claim <listing ID>` or `!m claim all`')
            lid=int(details)
            with db() as c:
                c.execute('BEGIN IMMEDIATE'); row=c.execute("SELECT proceeds,pokemon_name,shiny FROM market_listings WHERE listing_id=? AND seller_id=? AND status='sold'",(lid,ctx.author.id)).fetchone()
                if not row: c.rollback(); return await ctx.send('❌ No unclaimed sold listing with that ID belongs to you.')
                gross,pname,shiny=row; fee=(gross*5)//100; payout=gross-fee
                c.execute('UPDATE players SET coins=coins+? WHERE user_id=?',(payout,ctx.author.id)); c.execute("UPDATE market_listings SET status='claimed',proceeds=0 WHERE listing_id=?",(lid,)); c.commit()
            e=discord.Embed(title='💰 Market proceeds claimed!',description=f'Your {"✨ " if shiny else ""}**{pname.replace("-", " ").title()}** listing sold successfully.',color=discord.Color.green())
            e.add_field(name='Sale price',value=f'{gross:,} coins',inline=True); e.add_field(name='Market fee (5%)',value=f'{fee:,} coins',inline=True); e.add_field(name='You received',value=f'**{payout:,}** {get_vantacoin_emoji()} VantaCoins',inline=True)
            return await ctx.send(embed=e)
        return await ctx.send('Unknown market action. Use `!market` to see all market commands.')

    @commands.command(name='giveitem',aliases=['equip','holditem'])
    async def giveitem(self,ctx,*,args:str):
        parts=args.rsplit(maxsplit=1)
        if len(parts)!=2 or (not parts[1].isdigit() and parts[1].lower() != 'all'):
            return await ctx.send('Usage: `!giveitem <item name|shortform|id> <pokemon_id>` — example: `!giveitem Choice Band 12`')
        product,pokemon_text=parts; public_box_id=int(pokemon_text) if pokemon_text.isdigit() else None; pokemon_id=public_box_id
        if pokemon_id is not None:
            with db() as c: pokemon_id=resolve_box_id(c,ctx.author.id,pokemon_id)
            if pokemon_id is None:return await ctx.send('❌ That Pokémon ID is not yours. Check `!box`.')
        product_id=resolve_shop_product(product)
        if product_id is None:
            return await ctx.send('❌ Unknown item. Use `!shop` to see item names and shortforms.')
        key,label,cost,desc,shortform=SHOP_ITEMS[product_id]
        if product_id in (52, 53, 54):
            with db() as c:
                row=c.execute('SELECT * FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,ctx.author.id)).fetchone()
                stock=c.execute('SELECT amount FROM inventory WHERE user_id=? AND item=?',(ctx.author.id,key)).fetchone()
            if not row:return await ctx.send('❌ That Pokémon ID is not yours. Use `!box` to check your Pokémon IDs.')
            if not stock or stock[0]<1:return await ctx.send(f'❌ You do not own {item_emoji(key)} **{label}**. Buy it with `!shop buy {shortform}`.')
            if product_id == 54:
                pool=await move_pool(row[2],fast=False)
                view=EliteChargedMoveView(ctx.author.id,pokemon_id,key,row[3],pool)
                return await ctx.send(f'✨ Choose the new Charged Move for **{row[3].title()}** (ID `{public_box_id}`). Your current move stays until you select one.',view=view)
            fast=(product_id==52); pool=await move_pool(row[2],fast=fast); selected=random.choice(pool)
            column='fast_move' if fast else 'charged_move'
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                current=c.execute('SELECT amount FROM inventory WHERE user_id=? AND item=?',(ctx.author.id,key)).fetchone()
                if not current or current[0]<1:
                    c.rollback(); return await ctx.send(f'❌ You no longer have {item_emoji(key)} **{label}** in your inventory.')
                c.execute('UPDATE pokemon SET '+column+'=? WHERE instance_id=? AND user_id=?',(selected['name'],pokemon_id,ctx.author.id))
                c.execute('UPDATE inventory SET amount=amount-1 WHERE user_id=? AND item=?',(ctx.author.id,key))
                c.execute('DELETE FROM inventory WHERE user_id=? AND item=? AND amount<=0',(ctx.author.id,key))
            kind='Fast' if fast else 'Charged'
            return await ctx.send(f'✅ **{row[3].title()}** (ID `{public_box_id}`) changed its {kind} Move to **{selected["name"].replace("-", " ").title()}** using {item_emoji(key)} {label}.')
        if 'berry' in key or key in {'potion','super-potion','hyper-potion','max-potion','full-restore'}:
            return await ctx.send('🧪 This is a consumable; use `!useitem <item> <pokemon_id>`.')
        try:
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                row=c.execute('SELECT instance_id,name,held_item FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,ctx.author.id)).fetchone()
                if not row:
                    c.rollback()
                    return await ctx.send('❌ That Pokémon ID is not yours. Use `!box` to check your Pokémon IDs.')
                old_item=row[2] or ''
                if old_item==key:
                    c.rollback()
                    return await ctx.send(f'{item_emoji(key)} **{row[1].title()}** (ID `{public_box_id}`) is already holding **{label}**.')
                stock=c.execute('SELECT amount FROM inventory WHERE user_id=? AND item=?',(ctx.author.id,key)).fetchone()
                if not stock or stock[0] <= 0:
                    c.rollback()
                    return await ctx.send(f'❌ You do not own {item_emoji(key)} **{label}** in your inventory. Buy it with `!shop buy {shortform} 1`.')
                # Held items are stackable: each inventory copy can be equipped to a different Pokémon.
                # Do not reject an item just because another Pokémon holds the same item type;
                # the inventory quantity check above is the source of truth.
                c.execute('UPDATE inventory SET amount=amount-1 WHERE user_id=? AND item=?',(ctx.author.id,key))
                if old_item:
                    c.execute('INSERT INTO inventory(user_id,item,amount) VALUES(?,?,1) ON CONFLICT(user_id,item) DO UPDATE SET amount=amount+1',(ctx.author.id,old_item))
                c.execute('UPDATE pokemon SET held_item=? WHERE instance_id=? AND user_id=?',(key,pokemon_id,ctx.author.id))
                c.commit()
        except Exception as exc:
            print(f'giveitem failed for user {ctx.author.id}, Pokémon {pokemon_id}: {exc!r}')
            return await ctx.send('❌ Could not equip that item because of a database error. No changes were saved; please try again.')
        previous=f'\n↩️ {item_emoji(old_item)} Returned **{ITEM_BY_KEY[old_item][2] if old_item in ITEM_BY_KEY else old_item.replace("-", " ").title()}** to your inventory.' if old_item else ''
        await ctx.send(f'{item_emoji(key)} **{label}** is now held by **{row[1].title()}** (Pokémon ID `{public_box_id}`).\n🎒 Inventory: **−1 {item_emoji(key)} {label}**.'+previous)

    @commands.command(name='takeitem',aliases=['unequip','removehelditem'])
    async def takeitem(self,ctx,pokemon_id:int):
        """Remove a Pokémon's held item and return it to the owner's inventory."""
        public_box_id=pokemon_id
        with db() as c: pokemon_id=resolve_box_id(c,ctx.author.id,pokemon_id)
        if pokemon_id is None:return await ctx.send('❌ That Pokémon ID is not yours. Check `!box`.')
        try:
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                row=c.execute('SELECT instance_id,name,held_item FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,ctx.author.id)).fetchone()
                if not row:
                    c.rollback()
                    return await ctx.send('❌ That Pokémon ID is not yours. Use `!box` to check your Pokémon IDs.')
                held=row[2] or ''
                if not held:
                    c.rollback()
                    return await ctx.send(f'ℹ️ **{row[1].title()}** (Pokémon ID `{public_box_id}`) is not holding an item.')
                c.execute('INSERT INTO inventory(user_id,item,amount) VALUES(?,?,1) ON CONFLICT(user_id,item) DO UPDATE SET amount=amount+1',(ctx.author.id,held))
                c.execute("UPDATE pokemon SET held_item='' WHERE instance_id=? AND user_id=?",(pokemon_id,ctx.author.id))
                c.commit()
        except Exception as exc:
            print(f'takeitem failed for user {ctx.author.id}, Pokémon {pokemon_id}: {exc!r}')
            return await ctx.send('❌ Could not remove that held item because of a database error. No changes were saved; please try again.')
        label=ITEM_BY_KEY[held][2] if held in ITEM_BY_KEY else held.replace('-', ' ').title()
        await ctx.send(f'🎒 Took {item_emoji(held)} **{label}** from **{row[1].title()}** (Pokémon ID `{public_box_id}`). The item was returned to your inventory (+1).')

    @commands.command(name='useitem',aliases=['use','itemuse'])
    async def useitem(self,ctx,*,args:str):
        parts=args.rsplit(maxsplit=1)
        if len(parts)!=2 or (not parts[1].isdigit() and parts[1].lower() != 'all'):
            return await ctx.send('Usage: `!useitem <berry/potion name|shortform|id> <pokemon_id|all>` — example: `!useitem Potion 12` or `!use 51 all` for bulk Full Restore')
        product,pokemon_text=parts
        public_box_id=None if pokemon_text.lower()=='all' else int(pokemon_text)
        pokemon_id=public_box_id
        if pokemon_id is not None:
            with db() as c: pokemon_id=resolve_box_id(c,ctx.author.id,pokemon_id)
            if pokemon_id is None:return await ctx.send('❌ That Pokémon ID is not yours. Check `!box`.')
        product_id=resolve_shop_product(product)
        if product_id is None:return await ctx.send('❌ Unknown item. Use `!shop` or `!inventory` to see item names, shortforms, and IDs.')
        key,label,cost,desc,shortform=SHOP_ITEMS[product_id]
        consumable_keys={k for k,*_ in SHOP_ITEMS.values() if 'berry' in k}
        consumable_keys.update({'potion','super-potion','hyper-potion','max-potion','full-restore'})
        if key not in consumable_keys:return await ctx.send('❌ This is a held item. Equip it with `!giveitem <item_id> <pokemon_id>`.')
        with db() as c:
            row=c.execute('SELECT instance_id,name,hp,max_hp,status_condition FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,ctx.author.id)).fetchone()
            stock=c.execute('SELECT amount FROM inventory WHERE user_id=? AND item=?',(ctx.author.id,key)).fetchone()
        if pokemon_text.lower() == 'all':
            if key not in {'potion','super-potion','hyper-potion','max-potion','full-restore'}:
                return await ctx.send('❌ Bulk use with `all` is available for potions and restores only.')
            if not stock or stock[0] <= 0:
                return await ctx.send(f'❌ You do not own {item_emoji(key)} **{label}**. Buy it with `!shop buy {shortform} 1`.')
            heal_amount = {'potion': 20, 'super-potion': 50, 'hyper-potion': 120}.get(key)
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                current = c.execute('SELECT amount FROM inventory WHERE user_id=? AND item=?', (ctx.author.id, key)).fetchone()
                if not current or current[0] <= 0:
                    c.rollback()
                    return await ctx.send(f'❌ You do not own {item_emoji(key)} **{label}**. Buy it with `!shop buy {shortform} 1`.')
                if key == 'full-restore':
                    targets = c.execute("SELECT instance_id,name,hp,max_hp,status_condition FROM pokemon WHERE user_id=? AND (hp<max_hp OR COALESCE(status_condition,'')!='') ORDER BY instance_id", (ctx.author.id,)).fetchall()
                else:
                    targets = c.execute('SELECT instance_id,name,hp,max_hp,status_condition FROM pokemon WHERE user_id=? AND hp<max_hp ORDER BY instance_id', (ctx.author.id,)).fetchall()
                if not targets:
                    c.rollback()
                    return await ctx.send(f'ℹ️ None of your Pokémon need **{item_emoji(key)} {label}**. No items were consumed.')
                available = current[0]
                healed = min(len(targets), available)
                for target in targets[:healed]:
                    pid, pname, old_hp, max_hp, status = target
                    new_hp = max_hp if key in {'max-potion','full-restore'} else min(max_hp, old_hp + heal_amount)
                    new_status = '' if key == 'full-restore' else (status or '')
                    c.execute('UPDATE pokemon SET hp=?,status_condition=? WHERE instance_id=? AND user_id=?', (new_hp, new_status, pid, ctx.author.id))
                c.execute('UPDATE inventory SET amount=amount-? WHERE user_id=? AND item=?', (healed, ctx.author.id, key))
                c.commit()
            missed = len(targets) - healed
            summary = f'🧪 Used {item_emoji(key)} **{label}** on **{healed} Pokémon**.'
            if missed:
                summary += f'\n⚠️ **{missed} Pokémon could not be healed** because you did not have enough {label.lower()}s. Buy more from `!shop`.'
            await ctx.send(summary)
            return
        if not row:return await ctx.send('❌ That Pokémon ID is not yours. Use `!box` to check its ID.')
        if not stock or stock[0]<=0:return await ctx.send(f'❌ You do not own {item_emoji(key)} **{label}**. Buy it with `!shop buy {shortform} 1`.')
        hp,maxhp,status=row[2],row[3],row[4] or ''
        old_hp,old_status=hp,status
        cure_map={'pecha-berry':'poison','cheri-berry':'paralysis','rawst-berry':'burn','aspear-berry':'freeze','chesto-berry':'sleep'}
        if key in cure_map:
            target=cure_map[key]
            if status not in ((target,'badly-poisoned') if target=='poison' else (target,)):
                return await ctx.send(f'ℹ️ **{row[1].title()}** is not affected by {target.replace("-"," ")}. **{item_emoji(key)} {label}** was not consumed.')
            status='';msg=f'cured {target.replace("-"," ")}'
        elif key=='lum-berry':
            if not status:return await ctx.send(f'ℹ️ **{row[1].title()}** has no status condition. **{item_emoji(key)} {label}** was not consumed.')
            msg=f'cured {status_label(status).lower()}';status=''
        elif key=='oran-berry':
            if hp>=maxhp:return await ctx.send(f'ℹ️ **{row[1].title()}** already has full HP. **{item_emoji(key)} {label}** was not consumed.')
            hp=min(maxhp,hp+10);msg=f'restored {hp-old_hp} HP'
        elif key in ('sitrus-berry','figy-berry','wiki-berry','mago-berry','aguav-berry','iapapa-berry'):
            if hp>=maxhp:return await ctx.send(f'ℹ️ **{row[1].title()}** already has full HP. **{item_emoji(key)} {label}** was not consumed.')
            hp=min(maxhp,hp+max(1,maxhp//4));msg=f'restored {hp-old_hp} HP'
        elif key=='leppa-berry':
            if hp>=maxhp:return await ctx.send(f'ℹ️ **{row[1].title()}** already has full HP. **{item_emoji(key)} {label}** was not consumed.')
            hp=min(maxhp,hp+5);msg=f'restored {hp-old_hp} HP'
        elif key=='potion':
            if hp>=maxhp:return await ctx.send(f'ℹ️ **{row[1].title()}** already has full HP. **{item_emoji(key)} {label}** was not consumed.')
            hp=min(maxhp,hp+20);msg=f'restored {hp-old_hp} HP'
        elif key=='super-potion':
            if hp>=maxhp:return await ctx.send(f'ℹ️ **{row[1].title()}** already has full HP. **{item_emoji(key)} {label}** was not consumed.')
            hp=min(maxhp,hp+50);msg=f'restored {hp-old_hp} HP'
        elif key=='hyper-potion':
            if hp>=maxhp:return await ctx.send(f'ℹ️ **{row[1].title()}** already has full HP. **{item_emoji(key)} {label}** was not consumed.')
            hp=min(maxhp,hp+120);msg=f'restored {hp-old_hp} HP'
        elif key=='max-potion':
            if hp>=maxhp:return await ctx.send(f'ℹ️ **{row[1].title()}** already has full HP. **{item_emoji(key)} {label}** was not consumed.')
            hp=maxhp;msg='restored all HP'
        elif key=='full-restore':
            if hp>=maxhp and not status:return await ctx.send(f'ℹ️ **{row[1].title()}** already has full HP and no status condition. **{item_emoji(key)} {label}** was not consumed.')
            hp=maxhp;status='';msg='restored all HP and cured all status conditions'
        else:
            return await ctx.send('❌ This item does not have a use effect yet.')
        # Save the effect and consume the item together so failed uses do not lose inventory.
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            current=c.execute('SELECT amount FROM inventory WHERE user_id=? AND item=?',(ctx.author.id,key)).fetchone()
            if not current or current[0]<=0:
                c.rollback();return await ctx.send(f'❌ You do not own **{label}** anymore. No changes were made.')
            c.execute('UPDATE pokemon SET hp=?,status_condition=? WHERE instance_id=? AND user_id=?',(hp,status,pokemon_id,ctx.author.id))
            c.execute('UPDATE inventory SET amount=amount-1 WHERE user_id=? AND item=?',(ctx.author.id,key))
            c.commit()
        await ctx.send(f'🧪 Used {item_emoji(key)} **{label}** on **{row[1].title()}** (ID `{public_box_id}`): {msg}. HP: {hp_bar(hp,maxhp)} • Status: **{status_label(status)}**.')

    @commands.command(name='inventory',aliases=['inv','bag'],description='View your inventory in pages of ten entries.')
    async def inventory(self,ctx):
        ensure_player(ctx.author.id)
        entries=[]
        with db() as c:
            stock=c.execute('SELECT item,amount FROM inventory WHERE user_id=? AND amount>0 ORDER BY item COLLATE NOCASE',(ctx.author.id,)).fetchall()
            equipped=c.execute("SELECT held_item,name,instance_id FROM pokemon WHERE user_id=? AND held_item<>'' ORDER BY held_item COLLATE NOCASE,name COLLATE NOCASE",(ctx.author.id,)).fetchall()
        for item,amount in stock:
            info=ITEM_BY_KEY.get(item)
            if info:
                pid, key, label, cost, desc, shortform=info
                detail=f'Quantity: **{amount}** • Shop ID: `{pid}` • Shortform: `{shortform}`\n{desc}'
            else:
                label=item.replace('-',' ').title();detail=f'Quantity: **{amount}**'
            entries.append((label,detail))
        for item,name,iid in equipped:
            info=ITEM_BY_KEY.get(item)
            label=info[2] if info else item.replace('-',' ').title()
            entries.append((f'{label} — Equipped',f'Equipped to **{name.title()}** (Pokémon ID `{iid}`). This copy is equipped; any additional copies in inventory can be equipped to other Pokémon.'))
        entries.sort(key=lambda x:x[0].casefold())
        view=InventoryView(ctx.author.id,entries)
        view.message=await ctx.send(embed=view.make_embed(),view=view)
    @commands.command(name='pass', description='Dev-only: add Raid Passes to a player.')
    async def pass_command(self, ctx, action: str = None, member: discord.Member = None, quantity: int = None):
        if ctx.author.id not in OWNER_IDS:
            return await ctx.send('❌ This command is restricted to the bot developer.')
        if (action or '').lower() != 'add' or member is None or quantity is None:
            return await ctx.send('Usage: `!pass add @user <quantity>`')
        if quantity <= 0 or quantity > 100000:
            return await ctx.send('❌ Quantity must be between 1 and 100,000.')
        ensure_player(member.id)
        def action_fn():
            with db() as c:
                c.execute("INSERT INTO inventory(user_id,item,amount) VALUES(?, 'raid-pass', ?) ON CONFLICT(user_id,item) DO UPDATE SET amount=amount+excluded.amount", (member.id, quantity))
                row=c.execute("SELECT amount FROM inventory WHERE user_id=? AND item='raid-pass'",(member.id,)).fetchone()
            return f'Added **{quantity:,} Raid Pass(es)** to {member.mention}. New balance: **{row[0] if row else quantity:,}**.'
        await self.dev_confirmation(ctx,'Confirm Raid Pass addition',f'Add **{quantity:,} Raid Pass(es)** to {member.mention}?',action_fn)

    @commands.command(name='raid',description='View raid passes, spawn a special raid, or battle it.')
    async def raid(self,ctx,action:Optional[str]=None):
        uid=ctx.author.id; action=(action or 'status').lower()
        if action in ('cancel','stop','quit'):
            with db() as c:
                existed=c.execute('DELETE FROM raid_encounters WHERE user_id=?',(uid,)).rowcount
                c.execute('DELETE FROM raid_party WHERE user_id=?',(uid,))
                if existed:
                    c.execute("INSERT INTO inventory(user_id,item,amount) VALUES(?, 'raid-pass', 1) ON CONFLICT(user_id,item) DO UPDATE SET amount=amount+1",(uid,))
            if not existed:return await ctx.send('ℹ️ You do not have an active raid to cancel.')
            view=ACTIVE_VIEWS.pop(uid,None)
            if view and getattr(view,'raid',False):
                if self.active_boss_battles is not None:self.active_boss_battles.discard(uid)
                try:
                    if view.message: await view.message.edit(content='🛑 Raid cancelled. Your Raid Pass has been refunded.',embed=None,view=None)
                except Exception: pass
            return await ctx.send('🛑 Raid cancelled. Your Raid Pass has been returned to your inventory.')
        if action in ('battle','fight'):
            with db() as c:
                boss=c.execute('SELECT dex_id,name,level,shiny FROM raid_encounters WHERE user_id=?',(uid,)).fetchone()
                party=c.execute('SELECT p.* FROM raid_party rp JOIN pokemon p ON p.instance_id=rp.instance_id WHERE rp.user_id=? ORDER BY rp.slot',(uid,)).fetchall()
            if not boss:return await ctx.send('❌ No active raid. Use `!raid spawn` first.')
            if len(party)!=6:return await ctx.send(f'🧩 Select exactly **6 Pokémon** using `!add <ID1> <ID2> ... <ID6>` ({len(party)}/6 selected).')
            if all(r[8]<=0 for r in party):return await ctx.send('💤 All six Pokémon have fainted. Heal them before raiding.')
            level=max(r[4] for r in party)+100
            with db() as c:c.execute('UPDATE raid_encounters SET level=? WHERE user_id=?',(level,uid))
            d=await pokemon_data(boss[0]); d['_level']=level
            lead=next((r for r in party if r[8]>0),party[0])
            view=NPCBattleView(uid,lead,d,boss=False,boss_shiny=True,active_boss_battles=self.active_boss_battles,raid=True)
            if self.active_boss_battles is not None:self.active_boss_battles.add(uid)
            try: await view.build()
            except Exception:
                if self.active_boss_battles is not None:self.active_boss_battles.discard(uid)
                raise
            em=discord.Embed(title='🌟 SHINY RAID BOSS — 6 vs 1',description=f'**Boss:** ✨ {display_name(d)} Lv. **{level}**\nHP {hp_bar(max_hp(d,level)*4,max_hp(d,level)*4)}\n\n**Your raid squad:**\n'+'\n'.join(f'• `{r[0]}` **{r[3].title()}** Lv.{r[4]} — {hp_bar(r[8],r[9])}' for r in party)+'\n\nUse the move buttons below; if your active Pokémon faints, use Switch Pokémon to choose a healthy teammate. Win to receive 50 Rare Candies and the shiny boss at 75 levels below its raid level.')
            em.color=discord.Color.gold()
            if sprite(d,shiny=True):em.set_image(url=sprite(d,shiny=True))
            view.message=await ctx.send(embed=em,view=view); ACTIVE_VIEWS[uid]=view
            return
        if action=='spawn':
            with db() as c:
                wild=c.execute('SELECT 1 FROM encounters WHERE user_id=?',(uid,)).fetchone()
                legendary=c.execute('SELECT 1 FROM boss_encounters WHERE user_id=?',(uid,)).fetchone()
                if wild:return await ctx.send('⚠️ Resolve your active hunt with `!catch` or `!cancel` before spawning a raid.')
                if legendary:return await ctx.send('⚠️ Finish or cancel your legendary encounter before spawning a raid.')
                active=c.execute('SELECT name,level FROM raid_encounters WHERE user_id=?',(uid,)).fetchone()
                passes=c.execute("SELECT amount FROM inventory WHERE user_id=? AND item='raid-pass'",(uid,)).fetchone()
                if active:return await ctx.send(f'⚠️ You already have an active raid: ✨ **{active[0].title()}** Lv.{active[1]}. Use `!add` to select six Pokémon, then `!raid battle`.')
                if not passes or passes[0]<1:return await ctx.send('❌ You need a Raid Pass. Claim `!daily` for 5 passes.')
                c.execute("UPDATE inventory SET amount=amount-1 WHERE user_id=? AND item='raid-pass'",(uid,))
                c.execute("DELETE FROM inventory WHERE user_id=? AND item='raid-pass' AND amount<=0",(uid,))
            special_names={'nihilego','buzzwole','pheromosa','xurkitree','celesteela','kartana','guzzlord','poipole','naganadel','stakataka','blacephalon','meltan','melmetal'}
            mythical_names={'mew','celebi','jirachi','deoxys','phione','manaphy','darkrai','shaymin','arceus','victini','keldeo','meloetta','genesect','diancie','hoopa','volcanion','magearna','marshadow','zeraora','meltan','melmetal','zarude','pecharunt'}
            pool=[x for x in POKEMON_LIST if x['name'] in LEGENDARY_NAMES or x['name'] in special_names or x['name'] in mythical_names]
            if not pool:
                with db() as c:c.execute("INSERT INTO inventory(user_id,item,amount) VALUES(?, 'raid-pass', 1) ON CONFLICT(user_id,item) DO UPDATE SET amount=amount+1",(uid,))
                return await ctx.send('❌ Special Pokémon data is not loaded yet; your Raid Pass was refunded.')
            chosen=random.choice(pool); data=await pokemon_data(chosen['name'])
            with db() as c:c.execute('INSERT OR REPLACE INTO raid_encounters(user_id,dex_id,name,level,shiny) VALUES(?,?,?,?,1)',(uid,data['id'],data['name'],0))
            return await ctx.send(f'🌟 **Raid spawned!** A shiny special Pokémon — **{display_name(data)}** — is waiting!\n🎟️ 1 Raid Pass used. Use `!add <ID1> <ID2> <ID3> <ID4> <ID5> <ID6>`, then `!raid battle`.')
        with db() as c:
            passes=c.execute("SELECT amount FROM inventory WHERE user_id=? AND item='raid-pass'",(uid,)).fetchone()
            active=c.execute('SELECT name,level FROM raid_encounters WHERE user_id=?',(uid,)).fetchone()
            party=c.execute('SELECT p.instance_id,p.name,p.level FROM raid_party rp JOIN pokemon p ON p.instance_id=rp.instance_id WHERE rp.user_id=? ORDER BY rp.slot',(uid,)).fetchall()
        e=discord.Embed(
            title='🌟 Raid Center — How Raids Work',
            description=(
                f'🎟️ **Your Raid Passes: {passes[0] if passes else 0}**\n\n'
                'Challenge an exceptionally powerful **shiny special Pokémon** with a squad of six Pokémon. While a raid is active, `!hunt`, `!legendarybattle`, and `!battle` are blocked until you win or cancel. '
                'Raids use the existing move-and-switch battle controls.'
            ),
            color=discord.Color.gold()
        )
        e.add_field(name='🗺️ 1. Spawn a Raid', value='`!raid spawn`\nSpends **1 Raid Pass** to spawn a shiny Legendary, Mythical, or Ultra Beast. You can only have one active raid at a time.', inline=False)
        e.add_field(name='👥 2. Choose Your Six Pokémon', value='`!add <ID1> <ID2> <ID3> <ID4> <ID5> <ID6>`\nSelect **exactly six Pokémon IDs** you own. Your boss level is **100 levels above your highest-level selected Pokémon**.', inline=False)
        e.add_field(name='⚔️ 3. Start the Battle', value='`!raid battle`\nUse **Choose Move** and switch between your squad during the battle. Finish any other active battle first, and make sure your team can fight.', inline=False)
        e.add_field(name='🏆 Victory Rewards', value='Win to receive **50 Rare Candies** and add the shiny raid boss to your box at **75 levels below its raid level** (maximum Pokémon level: **300**). A failed raid gives no victory rewards, and the pass is not refunded.', inline=False)
        e.add_field(name='🍬 Level Up', value='`!candy <pokemon_id> <amount>` — spend Rare Candies to level up one of your Pokémon, up to **Lv. 300**.\n`!daily` — claim your daily reward, including **5 Raid Passes** when available.', inline=False)
        if active:
            raid_level=str(active[1]) if active[1] else 'set when battle starts'
            e.add_field(name='🚨 Your Active Raid',value=f'✨ **{active[0].title()}** • Boss level: **{raid_level}**\nSelected squad: **{len(party)}/6 Pokémon**\n' + ('Run `!add` to complete your squad, then `!raid battle`.' if len(party)<6 else 'Your squad is ready. Run `!raid battle` to begin.'),inline=False)
        e.set_footer(text='Tip: Run !raid any time to check your passes and review these instructions.')
        await ctx.send(embed=e)

    @commands.command(name='candy',description='Use Rare Candies to level up a Pokémon, up to level 300.')
    async def candy(self,ctx,pokemon_id:int,amount:int=1):
        public_box_id=pokemon_id
        if amount<1:return await ctx.send('❌ Amount must be at least 1.')
        with db() as c: pokemon_id=resolve_box_id(c,ctx.author.id,pokemon_id)
        if pokemon_id is None:return await ctx.send('❌ That Pokémon ID is not yours. Check `!box`.')
        with db() as c:
            row=c.execute('SELECT name,level FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,ctx.author.id)).fetchone()
            inv=c.execute("SELECT amount FROM inventory WHERE user_id=? AND item='rare-candy'",(ctx.author.id,)).fetchone()
            if not row:return await ctx.send('❌ That Pokémon ID is not yours.')
            if row[1]>=300:return await ctx.send('⭐ This Pokémon is already at the maximum level (300).')
            need=min(amount,300-row[1])
            if not inv or inv[0]<need:return await ctx.send(f'🍬 You need **{need} Rare Candies** but have **{inv[0] if inv else 0}**. Win raids to earn more.')
            newlevel=row[1]+need
            species=c.execute('SELECT dex_id,name,shiny,hp,max_hp FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,ctx.author.id)).fetchone()
            # Inventory and level updates are committed together below; max HP is recalculated afterward.
            c.execute('UPDATE pokemon SET level=? WHERE instance_id=? AND user_id=?',(newlevel,pokemon_id,ctx.author.id))
            c.execute("UPDATE inventory SET amount=amount-? WHERE user_id=? AND item='rare-candy'",(need,ctx.author.id))
            c.execute("DELETE FROM inventory WHERE user_id=? AND item='rare-candy' AND amount<=0",(ctx.author.id,))
        with db() as c: current=c.execute('SELECT dex_id,name,hp,max_hp,shiny FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,ctx.author.id)).fetchone()
        try:
            species_data=await pokemon_data(current[1]); new_max=max_hp(species_data,newlevel)
            old_max=max(1,current[3]); new_hp=min(new_max,max(1,int(current[2]/old_max*new_max))) if current[2]>0 else 0
            with db() as c:c.execute('UPDATE pokemon SET max_hp=?,hp=? WHERE instance_id=? AND user_id=?',(new_max,new_hp,pokemon_id,ctx.author.id))
        except Exception:pass
        await ctx.send(f'🍬 Used **{need} Rare Candies** on **{row[0].title()}**: Lv.{row[1]} → **Lv.{newlevel}**. Maximum level is 300.')

    @commands.command(name='daily',aliases=['d','claim'],description='Claim your daily VantaCoin and Pokémon reward.')
    async def daily(self,ctx):
        coins,xp,l,last,streak=get_player(ctx.author.id);now=int(time.time());uid=ctx.author.id
        if now-last<86400:return await ctx.send(f'⏳ Come back in {(86400-now+last)//3600}h.')
        if last and now-last<=172800: streak+=1
        else: streak=1
        legendary=streak%50==0
        if legendary:
            candidates=[x for x in POKEMON_LIST if x['name'] in LEGENDARY_NAMES]
        else:
            candidates=[x for x in POKEMON_LIST if x['name'] not in LEGENDARY_NAMES]
        pick=await pokemon_data(random.choice(candidates)['name'])
        lvl=random.randint(10,30); mh=max_hp(pick,lvl)
        with db() as c:
            c.execute('UPDATE players SET coins=coins+?,daily=?,daily_streak=? WHERE user_id=?',(2000,now,streak,uid))
            c.execute("INSERT INTO inventory(user_id,item,amount) VALUES(?, 'raid-pass', 5) ON CONFLICT(user_id,item) DO UPDATE SET amount=amount+5",(uid,))
            cur=c.execute('INSERT INTO pokemon(user_id,dex_id,name,level,shiny,hp,max_hp) VALUES(?,?,?,?,?,?,?)',(uid,pick['id'],pick['name'],lvl,0,mh,mh));iid=cur.lastrowid; assign_box_id(c,uid,iid)
            if not c.execute('SELECT 1 FROM team WHERE user_id=?',(uid,)).fetchone():c.execute('INSERT INTO team VALUES(?,?,?)',(uid,1,iid))
        if legendary:
            await ctx.send(f'🔥 **{streak}-day streak!** Guaranteed legendary reward: **{display_name(pick)}** Lv.{lvl} — ID `{get_box_id(c,uid,iid)}`\n💰 +2,000 {get_vantacoin_emoji()} VantaCoins • 🎟️ +5 Raid Passes')
        else:
            await ctx.send(f'🎁 Daily reward: **2,000 {get_vantacoin_emoji()} VantaCoins** + **{display_name(pick)}** Lv.{lvl} — ID `{get_box_id(c,uid,iid)}`\n🎟️ +5 Raid Passes\n🔥 Current streak: **{streak}** days')
    @commands.command(name='balance',aliases=['bal','money'],description='View your VantaCoins, level and XP.')
    async def balance(self,ctx):
        coins,xp,level,_,_=get_player(ctx.author.id)
        e=discord.Embed(title=f"💰 {ctx.author.display_name}'s Trainer Balance",color=discord.Color.gold())
        e.add_field(name=f'{get_vantacoin_emoji()} VantaCoins',value=f'**{coins:,}**',inline=True)
        e.add_field(name='Trainer Level',value=f'**{level}**',inline=True)
        e.add_field(name='XP Progress',value=f'**{xp:,} / {level*100:,}**',inline=True)
        e.set_footer(text='Earn coins from catching Pokémon, battles and daily rewards.')
        await ctx.send(embed=e)

    @commands.command(name='give', description='Give VantaCoins to another player.')
    async def give_coins(self, ctx, member: discord.Member = None, amount: int = None):
        if member is None or amount is None:
            return await ctx.send('Usage: `!give @user <coins>`')
        if member.bot or member.id == ctx.author.id:
            return await ctx.send('❌ You can give coins to another human player, not yourself or a bot.')
        if amount < 1 or amount > 1_000_000_000:
            return await ctx.send('❌ Enter an amount between 1 and 1,000,000,000 VantaCoins.')
        ensure_player(ctx.author.id); ensure_player(member.id)
        try:
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                sender=c.execute('SELECT coins FROM players WHERE user_id=?',(ctx.author.id,)).fetchone()
                balance=int(sender[0]) if sender else 0
                if balance < amount:
                    c.rollback()
                    return await ctx.send(f'❌ **Not enough balance!** Your `!bal` balance is **{balance:,} {get_vantacoin_emoji()} VantaCoins**, but you tried to give **{amount:,}**.')
                c.execute('UPDATE players SET coins=coins-? WHERE user_id=?',(amount,ctx.author.id))
                c.execute('UPDATE players SET coins=coins+? WHERE user_id=?',(amount,member.id))
                c.commit()
        except sqlite3.Error:
            return await ctx.send('❌ The transfer failed. Please try again.')
        e=discord.Embed(title='💸 VantaCoin Transfer Successful', description=f'{ctx.author.mention} gave **{amount:,} {get_vantacoin_emoji()} VantaCoins** to {member.mention}.', color=discord.Color.green())
        e.add_field(name='Sender balance',value=f'Use `!bal` to check your remaining coins.',inline=True)
        e.add_field(name='Recipient',value=f'{member.mention} received **{amount:,}** coins.',inline=True)
        await ctx.send(embed=e, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))

    @commands.command(name='bet', description='Challenge another player to a VantaCoin wager, including high-stakes mini-games.')
    async def bet(self, ctx, opponent: discord.Member, *, details: str = ''):
        """Use !bet @user <amount> or !bet @user high-stakes <amount>."""
        if ctx.guild is None:
            return await ctx.send('❌ Use `!bet` in a server.')
        if opponent.bot or opponent.id == ctx.author.id:
            return await ctx.send('❌ You must challenge another human player.')
        parts=details.split()
        high_stakes=bool(parts and parts[0].lower() in ('high-stakes','highstakes','high'))
        if high_stakes:
            if len(parts)!=2 or not parts[1].isdigit():
                return await ctx.send('Usage: `!bet @user high-stakes <amount>`')
            amount=int(parts[1])
        else:
            if len(parts)!=1 or not parts[0].isdigit():
                return await ctx.send('Usage: `!bet @user <amount>` or `!bet @user high-stakes <amount>`')
            amount=int(parts[0])
        if amount < 1 or amount > 2_000_000_000:
            return await ctx.send('❌ Bet an amount from **1 to 2,000,000,000 VantaCoins** per player.')
        if ctx.author.id in self.coin_bets or opponent.id in self.coin_bets:
            return await ctx.send('❌ One of you already has a pending or active coin bet.')
        ensure_player(ctx.author.id); ensure_player(opponent.id)
        with db() as c:
            rows=c.execute('SELECT user_id,coins FROM players WHERE user_id IN (?,?)',(ctx.author.id,opponent.id)).fetchall()
        balances={int(uid):int(coins) for uid,coins in rows}
        if balances.get(ctx.author.id,0)<amount:
            return await ctx.send(f'❌ You only have **{balances.get(ctx.author.id,0):,} {get_vantacoin_emoji()} VantaCoins**.')
        if balances.get(opponent.id,0)<amount:
            return await ctx.send(f'❌ {opponent.mention} only has **{balances.get(opponent.id,0):,} {get_vantacoin_emoji()} VantaCoins**, not enough to match that bet.')

        self.coin_bets[ctx.author.id]=opponent.id
        self.coin_bets[opponent.id]=ctx.author.id
        settled=False
        chosen_mode=None
        mode_view=TimedView(timeout=60,timeout_text='⏰ Bet challenge expired. No coins were taken.')
        async def cleanup():
            self.coin_bets.pop(ctx.author.id,None); self.coin_bets.pop(opponent.id,None)
        async def mode_timeout():
            await cleanup(); await TimedView.on_timeout(mode_view)
        mode_view.on_timeout=mode_timeout

        async def begin_challenge(mode):
            nonlocal chosen_mode
            chosen_mode=mode
            challenge=TimedView(timeout=60,timeout_text='⏰ Bet challenge expired. No coins were taken.')
            accept=discord.ui.Button(label='Accept Bet',style=discord.ButtonStyle.success,emoji='🤝')
            decline=discord.ui.Button(label='Decline',style=discord.ButtonStyle.danger,emoji='✖️')
            challenge.add_item(accept); challenge.add_item(decline)
            async def challenge_timeout():
                await cleanup(); await TimedView.on_timeout(challenge)
            challenge.on_timeout=challenge_timeout
            async def accept_cb(interaction):
                nonlocal settled
                if interaction.user.id!=opponent.id:
                    return await interaction.response.send_message('Only the challenged player can accept this bet.',ephemeral=True)
                if settled: return await interaction.response.send_message('This bet has already been settled.',ephemeral=True)
                settled=True
                await interaction.response.defer()
                with db() as c:
                    c.execute('BEGIN IMMEDIATE')
                    rows=c.execute('SELECT user_id,coins FROM players WHERE user_id IN (?,?)',(ctx.author.id,opponent.id)).fetchall()
                    now_bal={int(uid):int(coins) for uid,coins in rows}
                    if now_bal.get(ctx.author.id,0)<amount or now_bal.get(opponent.id,0)<amount:
                        c.rollback(); await cleanup(); challenge.stop()
                        return await interaction.edit_original_response(content='❌ Bet cancelled: one player no longer has enough coins. No coins were taken.',embed=None,view=None)
                    c.execute('UPDATE players SET coins=coins-? WHERE user_id IN (?,?)',(amount,ctx.author.id,opponent.id))
                    pot=amount*2
                    if mode=='roll':
                        score_a=random.randint(1,100); score_b=random.randint(1,100)
                        outcome=f'🎲 Roll results: {ctx.author.mention} rolled **{score_a}**; {opponent.mention} rolled **{score_b}**.'
                    elif mode=='roulette':
                        score_a=random.randint(0,36); score_b=random.randint(0,36)
                        outcome=f'🎡 Roulette spins: {ctx.author.mention} landed on **{score_a}**; {opponent.mention} landed on **{score_b}**.'
                    else:
                        def blackjack_total():
                            cards=[random.choice([2,3,4,5,6,7,8,9,10,10,10,11]) for _ in range(2)]
                            total=sum(cards)
                            if total>21 and 11 in cards: total-=10
                            # Simulate one conservative hit when below 16.
                            if total<16:
                                card=random.choice([2,3,4,5,6,7,8,9,10,10,10,11]); total+=card
                                if total>21 and (11 in cards or card==11): total-=10
                            return total
                        score_a=blackjack_total(); score_b=blackjack_total()
                        outcome=f'🃏 Blackjack totals: {ctx.author.mention} **{score_a}**; {opponent.mention} **{score_b}**.'
                    if score_a==score_b:
                        c.execute('UPDATE players SET coins=coins+? WHERE user_id=?',(amount,ctx.author.id))
                        c.execute('UPDATE players SET coins=coins+? WHERE user_id=?',(amount,opponent.id))
                        winner_id=None; fee=0; payout=0
                    else:
                        winner_id=ctx.author.id if score_a>score_b else opponent.id
                        fee=(pot*5)//100 if high_stakes else 0
                        payout=pot-fee
                        c.execute('UPDATE players SET coins=coins+? WHERE user_id=?',(payout,winner_id))
                    winner_row=c.execute('SELECT coins FROM players WHERE user_id=?',(winner_id,)).fetchone() if winner_id else None
                    winner_balance=int(winner_row[0]) if winner_row else 0
                    c.commit()
                await cleanup(); challenge.stop()
                e=discord.Embed(title=f'🎰 High-Stakes {mode.title()} Bet Complete' if high_stakes else '🪙 VantaCoin Head-to-Head Bet',color=discord.Color.gold())
                if winner_id is None:
                    e.description=f'{outcome}\n\n🤝 **Tie!** Both players get their **{amount:,}** stake back. No fee was charged.'
                else:
                    fee_text=' after the 5% pot fee' if high_stakes else ''
                    e.description=(f'{outcome}\n\n🏆 <@{winner_id}> wins **{payout:,} {get_vantacoin_emoji()} VantaCoins**{fee_text}.\n'
                                   f'💰 Total pot: **{pot:,}** · Bot fee: **{fee:,}** · Winner payout: **{payout:,}**.')
                    e.add_field(name='Winner Balance',value=f'**{winner_balance:,} {get_vantacoin_emoji()} VantaCoins**')
                e.set_footer(text='Both stakes are debited only after acceptance. High-stakes games charge 5% of the pot after a winner is determined.')
                try: await interaction.edit_original_response(content=None,embed=e,view=None)
                except Exception: await ctx.send(embed=e)
            async def decline_cb(interaction):
                nonlocal settled
                if interaction.user.id!=opponent.id:
                    return await interaction.response.send_message('Only the challenged player can decline this bet.',ephemeral=True)
                if settled: return await interaction.response.send_message('This bet has already been settled.',ephemeral=True)
                settled=True; await cleanup(); challenge.stop()
                await interaction.response.edit_message(content='❌ Bet declined. No coins were taken.',embed=None,view=None)
            accept.callback=accept_cb; decline.callback=decline_cb
            await ctx.send(f'🎰 **{"High-Stakes " if high_stakes else ""}VantaCoin Bet!**\n{ctx.author.mention} challenges {opponent.mention} to **{mode.title()}** for **{amount:,} {get_vantacoin_emoji()} VantaCoins each**.\nThe pot is **{amount*2:,}**; the winner receives 95% and the bot takes 5%. Ties refund both stakes.\n{opponent.mention}, accept or decline within 60 seconds.',view=challenge,allowed_mentions=discord.AllowedMentions(users=True))

        if high_stakes:
            for label,mode,emoji in [('Roll','roll','🎲'),('Roulette','roulette','🎡'),('Blackjack','blackjack','🃏')]:
                button=discord.ui.Button(label=label,style=discord.ButtonStyle.primary,emoji=emoji)
                async def mode_cb(interaction, selected=mode):
                    if interaction.user.id!=ctx.author.id:
                        return await interaction.response.send_message('Only the player who started the bet can choose the game mode.',ephemeral=True)
                    if settled: return await interaction.response.send_message('This bet has already been settled.',ephemeral=True)
                    await interaction.response.edit_message(content=f'✅ Selected **{selected.title()}**. Sending the challenge to {opponent.mention}…',view=None)
                    mode_view.stop()
                    await begin_challenge(selected)
                button.callback=mode_cb; mode_view.add_item(button)
            await ctx.send(f'🎰 {ctx.author.mention}, which high-stakes game do you want to play against {opponent.mention}?',view=mode_view)
        else:
            await begin_challenge('roll')

    async def dev_confirmation(self, ctx, title, description, action):
        # Developer confirmations do not expire; avoid stale timeout messages after a completed action.
        view=TimedView(timeout=None, timeout_text='')
        yes=discord.ui.Button(label='Confirm',style=discord.ButtonStyle.success,emoji='✅')
        no=discord.ui.Button(label='Cancel',style=discord.ButtonStyle.danger,emoji='❌')
        async def yes_cb(interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message('Only the dev who started this action can confirm it.',ephemeral=True)
            try:
                result=action()
                if asyncio.iscoroutine(result):
                    result = await result
                await interaction.response.edit_message(content=f'✅ {result}',embed=None,view=None)
            except Exception as exc:
                await interaction.response.edit_message(content=f'❌ Action failed: `{exc}`',embed=None,view=None)
        async def no_cb(interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message('Only the dev who started this action can cancel it.',ephemeral=True)
            await interaction.response.edit_message(content='❎ Action cancelled.',embed=None,view=None)
        yes.callback=yes_cb; no.callback=no_cb; view.add_item(yes); view.add_item(no)
        view.message=await ctx.send(embed=discord.Embed(title=title,description=description,color=discord.Color.orange()),view=view)

    @commands.command(name='banbot')
    async def ban_user(self, ctx, member: discord.Member, *, reason: str = 'Violation of game rules'):
        """Ban a user from using PokéVanta commands (not a Discord server ban)."""
        if not self.is_dev(ctx):
            return await ctx.send('❌ This command is restricted to the bot developers.')
        if member.bot:
            return await ctx.send('❌ You cannot bot-ban another bot account with this command.')
        if member.id in OWNER_IDS:
            return await ctx.send('❌ You cannot bot-ban a configured developer.')
        reason = reason.strip()[:500] or 'Violation of game rules'
        # Ask the developer to explicitly confirm before applying the persistent bot ban.
        def apply_ban():
            with db() as c:
                c.execute(
                    'INSERT INTO bot_bans(user_id, reason, banned_by, banned_at) VALUES(?,?,?,?) '
                    'ON CONFLICT(user_id) DO UPDATE SET reason=excluded.reason, banned_by=excluded.banned_by, banned_at=excluded.banned_at',
                    (member.id, reason, ctx.author.id, int(time.time()))
                )
            return f'{member.mention} is now banned from using PokéVanta commands. Reason: **{discord.utils.escape_markdown(reason)}**'
        e = discord.Embed(
            title='⚠️ Confirm PokéVanta Ban',
            description=(f'Are you sure you want to ban {member.mention} from using PokéVanta commands?\n\n'
                         f'**Reason:** {discord.utils.escape_markdown(reason)}\n\n'
                         'This does **not** ban them from the Discord server.'),
            color=discord.Color.orange()
        )
        e.set_thumbnail(url=member.display_avatar.url)
        await self.dev_confirmation(ctx, e.title, e.description, apply_ban)

    @commands.command(name='unbanbot')
    async def unban_user(self, ctx, user_id: int):
        """Remove a PokéVanta bot ban."""
        if not self.is_dev(ctx):
            return await ctx.send('❌ This command is restricted to the bot developers.')
        with db() as c:
            cur = c.execute('DELETE FROM bot_bans WHERE user_id=?', (user_id,))
        if cur.rowcount:
            await ctx.send(f'✅ Removed the PokéVanta bot ban for user ID `{user_id}`.')
        else:
            await ctx.send(f'ℹ️ User ID `{user_id}` is not bot-banned.')

    @commands.command(name='ban')
    async def developer_server_ban(self, ctx, member: discord.Member, *, reason: str = 'Violation of server rules'):
        """Ban a member from this Discord server, with explicit confirmation."""
        if not await self.require_permission(ctx, 'ban_members', 'Ban Members'): return
        if member.bot or member.id in OWNER_IDS:
            return await ctx.send('❌ You cannot server-ban a bot or configured developer.')
        if not await self._moderation_precheck(ctx, member, 'ban_members', 'Ban Members', 'ban'):
            return
        reason = reason.strip()[:500] or 'Violation of server rules'
        safe_reason = discord.utils.escape_markdown(reason)
        async def apply_server_ban():
            await ctx.guild.ban(member, reason=f'{reason} | Requested by developer {ctx.author} ({ctx.author.id})', delete_message_seconds=0)
            return f'{member} was **banned from this Discord server**. Reason: **{safe_reason}**'
        embed = discord.Embed(title='⚠️ Confirm Discord Server Ban', description=f'Ban {member.mention} from this server?\n\n**Reason:** {safe_reason}\n\nThis is a Discord server ban, separate from `!banbot`.', color=discord.Color.red())
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.dev_confirmation(ctx, embed.title, embed.description, apply_server_ban)

    @commands.command(name='unban')
    async def developer_server_unban(self, ctx, user_id: int):
        """Unban a member from this Discord server, with explicit confirmation."""
        if not await self.require_permission(ctx, 'ban_members', 'Ban Members'): return
        if ctx.guild is None:
            return await ctx.send('❌ Use this command in the server where the ban should be removed.')
        try:
            ban_entry = await ctx.guild.fetch_ban(discord.Object(id=user_id))
            user_label = f'{ban_entry.user} (`{user_id}`)'
        except discord.NotFound:
            return await ctx.send(f'ℹ️ User ID `{user_id}` is not banned from this server.')
        except discord.Forbidden:
            return await ctx.send('❌ I need the Ban Members permission to check server bans.')
        async def apply_server_unban():
            await ctx.guild.unban(discord.Object(id=user_id), reason=f'Removed by PokéVanta developer {ctx.author} ({ctx.author.id})')
            return f'**{user_label}** was unbanned from this Discord server.'
        await self.dev_confirmation(ctx, 'Confirm Discord Server Unban', f'Are you sure you want to unban **{user_label}** from this server? This does not remove a `!banbot` restriction.', apply_server_unban)

    # Carl-bot-inspired utilities: public commands do not require moderation permissions.
    @commands.command(name='roll')
    async def utility_roll(self, ctx, sides: int = 100):
        """Roll a random integer from 1 to the requested number of sides."""
        if sides < 2 or sides > 1_000_000:
            return await ctx.send('❌ Choose a number of sides between 2 and 1,000,000.')
        await ctx.send(f'🎲 {ctx.author.mention} rolled **{random.randint(1, sides)}** (1–{sides}).')

    @commands.command(name='choose', aliases=['pick'])
    async def utility_choose(self, ctx, *, options: str = ''):
        """Choose randomly from comma-separated options."""
        choices = [x.strip() for x in re.split(r',|\s+\bor\b\s+', options, flags=re.I) if x.strip()]
        if len(choices) < 2:
            return await ctx.send('Usage: `!choose option 1, option 2, option 3` (or `!pick ...`).')
        if len(choices) > 50:
            return await ctx.send('❌ Please provide no more than 50 choices.')
        await ctx.send(f'🎯 **I choose:** {discord.utils.escape_mentions(random.choice(choices))}')

    @commands.command(name='speak', description='Send an announcement message or attached media to a chosen channel.')
    async def speak(self, ctx, channel: discord.TextChannel, *, message: str = ''):
        """Post text and/or attached images, GIFs, or videos in another channel."""
        if not await self.require_permission(ctx, 'manage_messages', 'Manage Messages'):
            return
        if channel.guild.id != ctx.guild.id:
            return await ctx.send('❌ Please choose a text channel in this server.')

        attachments = list(ctx.message.attachments)
        if not message.strip() and not attachments:
            return await ctx.send(
                'Usage: `!speak #channel <message>` — you can also attach a photo, GIF, or video to the command.'
            )
        if len(attachments) > 10:
            return await ctx.send('❌ Discord allows at most 10 attachments in one message.')

        # Check the bot can actually post in the destination before attempting the send.
        me = ctx.guild.me
        perms = channel.permissions_for(me) if me else None
        if not perms or not perms.send_messages:
            return await ctx.send(f'❌ I do not have **Send Messages** permission in {channel.mention}.')
        if attachments and not perms.attach_files:
            return await ctx.send(f'❌ I need **Attach Files** permission in {channel.mention} to send that media.')

        files = []
        try:
            for attachment in attachments:
                files.append(await attachment.to_file())
            clean_message = message.strip()
            image_url = None
            urls = re.findall(r'https?://\S+', clean_message)
            for raw_url in urls:
                candidate = raw_url.rstrip('.,)>')
                if candidate.lower().split('?', 1)[0].endswith(('.gif','.png','.jpg','.jpeg','.webp')):
                    image_url = image_url or candidate
                    clean_message = clean_message.replace(raw_url, '').strip()
                elif not image_url:
                    try:
                        timeout = aiohttp.ClientTimeout(total=6)
                        async with aiohttp.ClientSession(timeout=timeout, headers={'User-Agent':'Mozilla/5.0'}) as session:
                            async with session.get(candidate, allow_redirects=True) as response:
                                if response.status == 200:
                                    html = await response.text(errors='ignore')
                                    for pattern in (r'<meta[^>]+property=["\']og:video(?:\:url)?["\'][^>]+content=["\']([^"\']+)', r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:video(?:\:url)?["\']', r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)'):
                                        match = re.search(pattern, html, re.I)
                                        if match and match.group(1).startswith('http'):
                                            image_url = match.group(1).replace('&amp;','&'); break
                    except Exception:
                        pass
                    clean_message = clean_message.replace(raw_url, '').strip()
            announcement = discord.Embed(
                title='📢 Announcement',
                description=clean_message[:4000] if clean_message else None,
                color=discord.Color.blurple(),
                timestamp=discord.utils.utcnow(),
            )
            announcement.set_footer(text=f'Announced by {ctx.author.display_name}', icon_url=ctx.author.display_avatar.url)
            image_attachment = next((a for a in attachments if (a.content_type or '').startswith('image/')), None)
            if image_attachment:
                announcement.set_image(url=f'attachment://{image_attachment.filename}')
            elif image_url:
                announcement.set_image(url=image_url)
            await channel.send(embed=announcement, files=files or None)
        except discord.Forbidden:
            return await ctx.send(f'❌ Discord denied my access to {channel.mention}. Check my channel permissions.')
        except discord.HTTPException as exc:
            return await ctx.send(f'❌ I could not post that announcement. The media may be too large or invalid. ({exc})')
        finally:
            for file in files:
                try:
                    file.close()
                except Exception:
                    pass

        try:
            await ctx.message.add_reaction('✅')
        except discord.HTTPException:
            pass

    @commands.command(name='poll')
    async def utility_poll(self, ctx, *, question: str):
        """Create a simple yes/no reaction poll."""
        if len(question) > 1800:
            return await ctx.send('❌ Keep the poll question under 1,800 characters.')
        embed = discord.Embed(title='📊 Poll', description=question, color=discord.Color.blurple())
        embed.set_footer(text=f'Poll created by {ctx.author.display_name}')
        msg = await ctx.send(embed=embed)
        for emoji in ('👍', '👎'):
            try:
                await msg.add_reaction(emoji)
            except discord.HTTPException:
                break

    # Moderation commands: pre-check bot permissions and role hierarchy, then report
    # Discord's actual error instead of masking every Forbidden response.
    async def _moderation_precheck(self, ctx, member, permission, label, action):
        if ctx.guild is None:
            await ctx.send(f"❌ Use {action} in a Discord server.")
            return False
        me = ctx.guild.me
        if me is None:
            await ctx.send("❌ I couldn't resolve my bot member in this server. Re-invite the bot or check its server membership.")
            return False
        if not getattr(me.guild_permissions, permission, False):
            await ctx.send(f"❌ I need the **{label}** server permission. Enable it for my bot role in Server Settings → Roles.")
            return False
        if member.id == ctx.guild.owner_id:
            await ctx.send("❌ Discord does not allow this action against the server owner.")
            return False
        if member.id == me.id:
            await ctx.send("❌ I can't apply this moderation action to myself.")
            return False
        if member.top_role >= me.top_role:
            await ctx.send(
                f"❌ I can't {action} {member.mention} because their highest role "
                f"(**{discord.utils.escape_markdown(member.top_role.name)}**) is equal to or above my highest role "
                f"(**{discord.utils.escape_markdown(me.top_role.name)}**). Move my bot role above their highest role."
            )
            return False
        return True

    @commands.command(name='mute', aliases=['to', 'timeout'])
    async def developer_timeout(self, ctx, member: discord.Member, minutes: int = 10, *, reason: str = 'No reason provided'):
        if not await self.require_permission(ctx, 'moderate_members', 'Moderate Members'):
            return
        if member.bot or member.id in OWNER_IDS:
            return await ctx.send('❌ You cannot timeout a bot or configured developer.')
        if not 1 <= minutes <= 40320:
            return await ctx.send('❌ Timeout duration must be between 1 and 40,320 minutes (28 days).')
        if not await self._moderation_precheck(ctx, member, 'moderate_members', 'Moderate Members', 'timeout'):
            return
        try:
            from datetime import timedelta
            await member.timeout(discord.utils.utcnow() + timedelta(minutes=minutes),
                                 reason=f'{reason[:400]} | Requested by {ctx.author} ({ctx.author.id})')
            await ctx.send(f'🔇 Timed out {member.mention} for **{minutes} minute(s)**. Reason: {discord.utils.escape_markdown(reason)[:500]}')
        except discord.Forbidden as exc:
            await ctx.send(f'❌ Discord denied the timeout (403 Forbidden). Check **Moderate Members**, bot role position, and whether the target has Administrator. Details: `{str(exc)[:250] or "Discord returned Forbidden"}`')
        except discord.HTTPException as exc:
            await ctx.send(f'❌ Timeout failed (HTTP {getattr(exc, "status", "?")}, code {getattr(exc, "code", "?")}): `{str(exc)[:300]}`')

    @commands.command(name='unmute', aliases=['untimeout', 'unto'])
    async def developer_untimeout(self, ctx, member: discord.Member, *, reason: str = 'Timeout removed by developer'):
        if not await self.require_permission(ctx, 'moderate_members', 'Moderate Members'):
            return
        if not await self._moderation_precheck(ctx, member, 'moderate_members', 'Moderate Members', 'remove the timeout from'):
            return
        try:
            await member.timeout(None, reason=f'{reason[:400]} | Requested by {ctx.author} ({ctx.author.id})')
            await ctx.send(f'🔊 Removed timeout for {member.mention}.')
        except discord.Forbidden as exc:
            await ctx.send(f'❌ Discord denied removing the timeout (403 Forbidden). Check **Moderate Members** and bot role position. Details: `{str(exc)[:250] or "Discord returned Forbidden"}`')
        except discord.HTTPException as exc:
            await ctx.send(f'❌ Could not remove timeout (HTTP {getattr(exc, "status", "?")}, code {getattr(exc, "code", "?")}): `{str(exc)[:300]}`')

    @commands.command(name='kick')
    async def developer_kick(self, ctx, member: discord.Member, *, reason: str = 'No reason provided'):
        if not await self.require_permission(ctx, 'kick_members', 'Kick Members'):
            return
        if member.bot or member.id in OWNER_IDS:
            return await ctx.send('❌ You cannot kick a bot or configured developer.')
        if not await self._moderation_precheck(ctx, member, 'kick_members', 'Kick Members', 'kick'):
            return
        try:
            await member.kick(reason=f'{reason[:400]} | Requested by {ctx.author} ({ctx.author.id})')
            await ctx.send(f'👢 Kicked **{discord.utils.escape_markdown(str(member))}**. Reason: {discord.utils.escape_markdown(reason)[:500]}')
        except discord.Forbidden as exc:
            await ctx.send(f'❌ Discord denied the kick (403 Forbidden). Check **Kick Members**, bot role position, and target permissions. Details: `{str(exc)[:250] or "Discord returned Forbidden"}`')
        except discord.HTTPException as exc:
            await ctx.send(f'❌ Kick failed (HTTP {getattr(exc, "status", "?")}, code {getattr(exc, "code", "?")}): `{str(exc)[:300]}`')

    @commands.command(name='clear', aliases=['purge', 'prune'])
    async def developer_clear(self, ctx, amount: int = 10):
        if not await self.require_permission(ctx, 'manage_messages', 'Manage Messages'): return
        if not 1 <= amount <= 100:
            return await ctx.send('❌ Choose an amount from 1 to 100.')
        try:
            deleted = await ctx.channel.purge(limit=amount + 1)
            notice = await ctx.send(f'🧹 Deleted **{max(0, len(deleted)-1)}** message(s).')
            await notice.delete(delay=4)
        except discord.Forbidden:
            await ctx.send('❌ I need Manage Messages permission to clear messages.')
        except discord.HTTPException as exc:
            await ctx.send(f'❌ Clear failed: `{exc}`')

    @commands.command(name='slowmode')
    async def developer_slowmode(self, ctx, seconds: int = 0):
        if not await self.require_permission(ctx, 'manage_channels', 'Manage Channels'): return
        if not 0 <= seconds <= 21600:
            return await ctx.send('❌ Slowmode must be from 0 to 21,600 seconds.')
        try:
            await ctx.channel.edit(slowmode_delay=seconds, reason=f'Set by PokéVanta developer {ctx.author} ({ctx.author.id})')
            await ctx.send(f'🐢 Slowmode set to **{seconds} second(s)**.')
        except discord.Forbidden:
            await ctx.send('❌ I need Manage Channels permission to set slowmode.')
        except discord.HTTPException as exc:
            await ctx.send(f'❌ Slowmode failed: `{exc}`')

    @commands.command(name='lock')
    async def developer_lock(self, ctx):
        if not await self.require_permission(ctx, 'manage_channels', 'Manage Channels'): return
        if not isinstance(ctx.channel, discord.TextChannel):
            return await ctx.send('❌ This command works in a server text channel.')
        try:
            overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
            overwrite.send_messages = False
            await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f'Locked by developer {ctx.author} ({ctx.author.id})')
            await ctx.send('🔒 Locked the channel.', allowed_mentions=discord.AllowedMentions.none())
        except discord.Forbidden:
            await ctx.send('❌ I need Manage Channels permission to lock this channel.')
        except discord.HTTPException as exc:
            await ctx.send(f'❌ Lock failed: `{exc}`')

    @commands.command(name='unlock')
    async def developer_unlock(self, ctx):
        if not await self.require_permission(ctx, 'manage_channels', 'Manage Channels'): return
        if not isinstance(ctx.channel, discord.TextChannel):
            return await ctx.send('❌ This command works in a server text channel.')
        try:
            overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
            overwrite.send_messages = None
            await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f'Unlocked by developer {ctx.author} ({ctx.author.id})')
            await ctx.send('🔓 Unlocked the channel.')
        except discord.Forbidden:
            await ctx.send('❌ I need Manage Channels permission to unlock this channel.')
        except discord.HTTPException as exc:
            await ctx.send(f'❌ Unlock failed: `{exc}`')

    @commands.command(name='serverinfo', aliases=['server'])
    async def utility_serverinfo(self, ctx):
        if not ctx.guild:
            return await ctx.send('This command is available in a server.')
        g = ctx.guild
        e = discord.Embed(title=f'ℹ️ {g.name}', color=discord.Color.blurple(), description=f'**Server ID:** `{g.id}`\n**Owner:** {g.owner.mention if g.owner else "Unknown"}\n**Members:** {g.member_count}\n**Text/voice channels:** {len(g.channels)}\n**Roles:** {len(g.roles)}\n**Created:** <t:{int(g.created_at.timestamp())}:D>')
        if g.icon:
            e.set_thumbnail(url=g.icon.url)
        await ctx.send(embed=e)

    @commands.command(name='userinfo', aliases=['user'])
    async def utility_userinfo(self, ctx, member: Optional[discord.Member] = None):
        member = member or ctx.author
        e = discord.Embed(title=f'👤 {member}', color=discord.Color.blurple())
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name='User ID', value=f'`{member.id}`', inline=True)
        e.add_field(name='Account created', value=f'<t:{int(member.created_at.timestamp())}:D>', inline=True)
        if member.joined_at:
            e.add_field(name='Joined server', value=f'<t:{int(member.joined_at.timestamp())}:D>', inline=True)
        await ctx.send(embed=e)

    def is_dev(self, ctx):
        return ctx.author.id in OWNER_IDS

    async def require_permission(self, ctx, permission, label):
        """Require the caller's own server permission; bot developers get no bypass."""
        if ctx.guild and (ctx.author.guild_permissions.administrator or getattr(ctx.author.guild_permissions, permission, False)):
            return True
        await ctx.send(f'❌ You need **{label}** permission in this server to use this command. Bot-developer status does not bypass server permissions.')
        return False

    @commands.command(name='coinsadd',aliases=['addcoins'])
    async def coinsadd(self,ctx,member:discord.Member,amount:int):
        if not self.is_dev(ctx): return
        if amount <= 0 or amount > 1_000_000_000: return await ctx.send('❌ Amount must be between 1 and 1,000,000,000 VantaCoins.')
        def action():
            add_progress(member.id,coins=amount)
            return f'Added **{amount:,} {get_vantacoin_emoji()} VantaCoins** to {member.mention}. New balance: **{get_player(member.id)[0]:,} {get_vantacoin_emoji()} VantaCoins**.'
        await self.dev_confirmation(ctx,'Confirm coin addition',f'Add **{amount:,} {get_vantacoin_emoji()} VantaCoins** to {member.mention}?',action)

    @commands.command(name='removecoins',aliases=['takecoins'])
    async def removecoins(self,ctx,member:discord.Member,amount:int):
        if not self.is_dev(ctx): return
        if amount <= 0 or amount > 1_000_000_000: return await ctx.send('❌ Amount must be between 1 and 1,000,000,000 VantaCoins.')
        def action():
            old=get_player(member.id)[0]; new=max(0,old-amount)
            with db() as c: c.execute('UPDATE players SET coins=? WHERE user_id=?',(new,member.id))
            return f'Removed **{old-new:,} {get_vantacoin_emoji()} VantaCoins** from {member.mention}. New balance: **{new:,} {get_vantacoin_emoji()} VantaCoins**.'
        await self.dev_confirmation(ctx,'Confirm coin removal',f'Remove up to **{amount:,} {get_vantacoin_emoji()} VantaCoins** from {member.mention}?',action)

    @commands.command(name='removepokemon',aliases=['removepoke'])
    async def removepokemon(self,ctx,member:discord.Member,pokemon_id:int):
        if not self.is_dev(ctx): return
        public_box_id=pokemon_id
        with db() as c: pokemon_id=resolve_box_id(c,member.id,pokemon_id)
        if pokemon_id is None:return await ctx.send('❌ That Pokémon ID is not in that trainer’s box.')
        with db() as c: row=c.execute('SELECT instance_id,name,shiny,level FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,member.id)).fetchone()
        if not row: return await ctx.send('❌ That Pokémon ID does not belong to that user.')
        def action():
            with db() as c:
                c.execute('DELETE FROM team WHERE instance_id=?',(pokemon_id,))
                c.execute('DELETE FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,member.id))
            return f'Removed {"✨ Shiny " if row[2] else ""}**{row[1].title()}** Lv. {row[3]} (ID `{public_box_id}`) from {member.mention}.'
        await self.dev_confirmation(ctx,'Confirm Pokémon removal',f'Remove **{row[1].title()}** (ID `{public_box_id}`) from {member.mention}?',action)

    @commands.command(name='setupitememojis')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_emojis_and_stickers=True)
    async def setupitememojis(self, ctx):
        """Install all 54 shop-item sprite emojis, resuming safely after partial runs."""
        items = list(SHOP_ITEMS.values())
        status = await ctx.send(f'🖼️ Preparing item sprites: {len(items)} shop items found. Checking existing emojis and available slots…')

        saved = {}
        try:
            with open(ITEM_EMOJI_FILE, 'r', encoding='utf-8') as f:
                old = json.load(f)
                if isinstance(old, dict):
                    saved.update(old)
        except (OSError, ValueError, TypeError):
            pass

        # Reuse item emojis from ANY server this bot belongs to, instead of
        # trying to upload a duplicate into the server where the command ran.
        # Discord custom emoji markup (str(emoji)) stores both the name and ID.
        globally_found = {}
        for source_guild in self.bot.guilds:
            for source_emoji in source_guild.emojis:
                for item_key, *_rest in items:
                    expected_name = 'item_' + re.sub(r'[^a-z0-9_]', '_', item_key.lower())
                    if source_emoji.name == expected_name and item_key not in globally_found:
                        globally_found[item_key] = str(source_emoji)
        for item_key, emoji_markup in globally_found.items():
            saved[item_key] = emoji_markup
            ITEM_EMOJI[item_key] = emoji_markup
            SHOP_ITEM_EMOJI[item_key] = emoji_markup

        # Some game-specific item names do not have their own PokeAPI sprite.
        # Use a related official item sprite as a fallback rather than leaving
        # the item without an emoji. Every shop key still gets its own emoji name.
        fallback_by_item = {
            'fast-tm': 'tm-normal',
            'charged-tm': 'tm-normal',
            'elite-charged-tm': 'tm-normal',
            'pixie-plate': 'flame-plate',
            'heavy-duty-boots': 'boots',
            'safety-goggles': 'wide-lens',
            'wise-glasses': 'wise-glasses',
            'choice-specs': 'choice-specs',
            'assault-vest': 'assault-vest',
        }
        fallback_by_group = {
            'berry': 'oran-berry',
            'potion': 'potion',
            'tm': 'tm-normal',
            'held': 'leftovers',
        }

        async def download_png(key):
            candidates = [key]
            if key in fallback_by_item:
                candidates.append(fallback_by_item[key])
            if 'berry' in key:
                candidates.append(fallback_by_group['berry'])
            elif key in {'potion', 'super-potion', 'hyper-potion', 'max-potion', 'full-restore'}:
                candidates.append(fallback_by_group['potion'])
            elif 'tm' in key:
                candidates.append(fallback_by_group['tm'])
            else:
                candidates.append(fallback_by_group['held'])
            # Final known-good generic item art keeps a missing upstream sprite
            # from leaving a shop item without an image.
            candidates.append('leftovers')
            # Keep order but remove duplicates.
            candidates = list(dict.fromkeys(candidates))
            last_error = 'sprite not found'
            for candidate in candidates:
                url = f'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/items/{candidate}.png'
                for attempt in range(3):
                    try:
                        timeout = aiohttp.ClientTimeout(total=20)
                        async with aiohttp.ClientSession(timeout=timeout) as session:
                            async with session.get(url) as response:
                                if response.status == 404:
                                    last_error = f'{candidate}: HTTP 404'
                                    break
                                if response.status != 200:
                                    last_error = f'{candidate}: HTTP {response.status}'
                                    await asyncio.sleep(0.7 * (attempt + 1))
                                    continue
                                data = await response.read()
                                if not data.startswith(b'\x89PNG\r\n\x1a\n'):
                                    last_error = f'{candidate}: response was not PNG'
                                    break
                                if len(data) > 256 * 1024:
                                    last_error = f'{candidate}: sprite exceeds Discord 256 KB limit'
                                    break
                                return data, candidate
                    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                        last_error = f'{candidate}: {type(exc).__name__}'
                        await asyncio.sleep(0.7 * (attempt + 1))
            raise RuntimeError(last_error)

        created = reused = failed = 0
        failures = []
        total = len(items)
        for index, (key, label, cost, desc, shortform) in enumerate(items, start=1):
            emoji_name = 'item_' + re.sub(r'[^a-z0-9_]', '_', key.lower())
            # Prefer an emoji already present in any server shared with the bot.
            # This allows the same item sprite to be used across the bot's servers.
            existing_markup = saved.get(key)
            existing_here = discord.utils.get(ctx.guild.emojis, name=emoji_name)
            if existing_here:
                saved[key] = str(existing_here)
                ITEM_EMOJI[key] = str(existing_here)
                SHOP_ITEM_EMOJI[key] = str(existing_here)
                reused += 1
            elif existing_markup:
                ITEM_EMOJI[key] = existing_markup
                SHOP_ITEM_EMOJI[key] = existing_markup
                reused += 1
            else:
                try:
                    image_bytes, source_key = await download_png(key)
                    # Retry transient Discord API failures (rate limits / server errors).
                    # Permanent errors such as a full emoji slot limit are reported clearly.
                    emoji = None
                    for upload_attempt in range(5):
                        try:
                            emoji = await ctx.guild.create_custom_emoji(
                                name=emoji_name,
                                image=image_bytes,
                                reason=f'PokéVanta item sprite: {label}'
                            )
                            break
                        except discord.HTTPException as upload_exc:
                            status_code = getattr(upload_exc, "status", None)
                            error_code = getattr(upload_exc, "code", None)
                            retry_after = getattr(upload_exc, "retry_after", None)
                            transient = (
                                status_code == 429
                                or (status_code is not None and status_code >= 500)
                                or error_code in (0, 50035)
                            )
                            if upload_attempt >= 4 or not transient:
                                if error_code == 30008:
                                    raise RuntimeError(
                                        "Discord emoji slots are full; remove unused emojis or boost the server for more slots"
                                    ) from upload_exc
                                raise
                            wait_seconds = float(retry_after or (2 ** upload_attempt))
                            await asyncio.sleep(min(max(wait_seconds, 1.0), 30.0))
                    if emoji is None:
                        raise RuntimeError("Discord upload did not return an emoji after retries")
                    saved[key] = str(emoji)
                    created += 1
                    # Persist after each successful upload so a disconnect/restart
                    # does not lose mappings and the command can safely be rerun.
                    with open(ITEM_EMOJI_FILE, 'w', encoding='utf-8') as f:
                        json.dump(saved, f, ensure_ascii=False, indent=2)
                    ITEM_EMOJI[key] = str(emoji)
                    SHOP_ITEM_EMOJI[key] = str(emoji)
                except Exception as exc:
                    failed += 1
                    failures.append(f'{key}: {type(exc).__name__}: {str(exc)[:110]}')
            if index % 5 == 0 or index == total:
                try:
                    await status.edit(content=f'🖼️ Item sprite setup: **{index}/{total}** checked • created {created} • already present {reused} • failed {failed}')
                except discord.HTTPException:
                    pass
            # Respect Discord's per-route rate limits and avoid hammering the sprite host.
            await asyncio.sleep(0.8)

        try:
            with open(ITEM_EMOJI_FILE, 'w', encoding='utf-8') as f:
                json.dump(saved, f, ensure_ascii=False, indent=2)
            ITEM_EMOJI.update(saved)
            SHOP_ITEM_EMOJI.update(saved)
        except OSError as exc:
            failures.append(f'Could not save item_emojis.json: {exc}')

        summary = (
            '**PokéVanta Item Sprite Setup**\n'
            f'**Shop items checked:** {total}/54\n'
            f'**Created now:** {created}\n'
            f'**Already present/reused:** {reused}\n'
            f'**Mapped items:** {sum(1 for key, *_ in items if key in saved)}/54\n'
            f'**Failed this run:** {failed}\n'
            f'**Emoji slots:** {len(ctx.guild.emojis)}/{getattr(ctx.guild, "emoji_limit", "unknown")} used'
        )
        if failures:
            summary += (
                '\n\n**Items to retry**\n'
                + '\n'.join('• ' + x for x in failures[:15])
                + '\n\nTemporary Discord upload errors are retried. Emoji-slot limits and missing permissions cannot be bypassed; fix those and rerun `!setupitememojis` to resume.'
            )
            if len(failures) > 15:
                summary += f'\n…and {len(failures) - 15} more. Run `!setupitememojis` again after fixing the listed issue.'
        elif sum(1 for key, *_ in items if key in saved) == 54:
            summary += '\n\n✅ All 54 item keys now have saved emoji mappings. Run `!setupitememojis` again to reuse them without duplicate uploads.'
        await status.edit(content=summary[:2000])

    @commands.command(name='setupvantacoin')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_emojis_and_stickers=True)
    async def setupvantacoin(self, ctx):
        """Install or reuse the VantaCoin currency emoji without touching item sprites."""
        status = await ctx.send('🪙 Installing the VantaCoin sprite…')
        emoji_name = 'vantacoin'
        existing = discord.utils.get(ctx.guild.emojis, name=emoji_name)
        if existing:
            emoji = str(existing)
            result = 'VantaCoin sprite was already installed; saved mapping refreshed.'
        else:
            try:
                image_bytes = base64.b64decode(VANTACOIN_SPRITE_B64, validate=True)
                if not image_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise ValueError('embedded VantaCoin data is not a PNG')
                if len(image_bytes) > 256 * 1024:
                    raise ValueError(f'VantaCoin PNG is {len(image_bytes)} bytes; reduce it below 256 KB')
                created = await asyncio.wait_for(
                    ctx.guild.create_custom_emoji(
                        name=emoji_name,
                        image=image_bytes,
                        reason='PokéVanta VantaCoin currency sprite'
                    ),
                    timeout=60.0
                )
                emoji = str(created)
                result = 'VantaCoin sprite installed successfully.'
            except asyncio.TimeoutError:
                return await status.edit(content='⏱️ VantaCoin upload timed out before Discord confirmed creation. The sprite may not be installed. Check the bot console/network connection to Discord, then run `!setupvantacoin` again; the command checks for an existing `vantacoin` emoji first to avoid creating duplicates.')
            except discord.Forbidden:
                return await status.edit(content='❌ I need **Manage Expressions** permission and an available custom emoji slot to install VantaCoin.')
            except Exception as exc:
                return await status.edit(content=f'❌ VantaCoin sprite setup failed: {type(exc).__name__}: {str(exc)[:180]}')
        try:
            with open(VANTACOIN_EMOJI_FILE, 'w', encoding='utf-8') as f:
                json.dump({'emoji': emoji}, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            return await status.edit(content=f'⚠️ Sprite uploaded, but I could not save its mapping: {exc}')
        await status.edit(content=f'✅ {result}\\nPreview: {emoji} **VantaCoins**\\nExisting Pokémon item sprites were not changed.')

    @commands.command(name='leaderboard',aliases=['lb','top'],description='Show richest trainers.')
    async def leaderboard(self,ctx,category:str='coins'):
        category=(category or 'coins').lower().strip()
        if category in ('coin','money','richest'): category='coins'
        if category in ('lvl','levels','xp'): category='level'
        if category not in ('coins','level'):
            return await ctx.send('❌ Choose a leaderboard: `!lb vantacoin` or `!lb level`.')
        order='coins DESC, level DESC, user_id ASC' if category=='coins' else 'level DESC, coins DESC, user_id ASC'
        with db() as c:r=c.execute(f'SELECT user_id,coins,level FROM players ORDER BY {order} LIMIT 10').fetchall()
        metric='coins' if category=='coins' else 'level'
        embed=discord.Embed(title=(f'{get_vantacoin_emoji()} VantaCoin Leaderboard' if category=='coins' else '⭐ Level Leaderboard'),description=(f'Top trainers ranked by VantaCoins.' if category=='coins' else 'Top trainers ranked by level.'),color=discord.Color.gold() if category=='coins' else discord.Color.blue())
        if not r:
            embed.description='No trainers are ranked yet. Use `!hunt` and `!daily` to get started.'
        else:
            medals={1:'🥇',2:'🥈',3:'🥉'}
            lines=[]
            for i,(uid,coins,level) in enumerate(r,1):
                member=ctx.guild.get_member(uid) if ctx.guild else None
                shown=f'{member.mention} ({discord.utils.escape_markdown(member.display_name)})' if member else f'<@{uid}>'
                score=f'{get_vantacoin_emoji()} **{coins:,} VantaCoins**' if category=='coins' else f'⭐ **Level {level}**'
                secondary=f'⭐ Lv. {level}' if category=='coins' else f'{get_vantacoin_emoji()} {coins:,} VantaCoins'
                lines.append(f'{medals.get(i, f"**{i}.**")} {shown}  ·  {score}  ·  {secondary}')
            embed.description='\n'.join(lines)
        embed.set_footer(text=f'Top {len(r)} trainers • Ranked by {category}')
        await ctx.send(embed=embed)

    @commands.command(name='trade')
    async def trade(self, ctx, target: discord.Member = None):
        if target is None or target.bot or target.id == ctx.author.id:
            return await ctx.send('Usage: `!trade @user` — choose another human player.')
        if ctx.author.id in TRADE_BY_USER or target.id in TRADE_BY_USER:
            return await ctx.send('❌ One of you is already in an active trade.')
        ensure_player(ctx.author.id); ensure_player(target.id)
        tid = f'{ctx.channel.id}:{ctx.author.id}:{target.id}:{time.time_ns()}'
        trade = {'id':tid,'starter':ctx.author.id,'target':target.id,'channel':ctx.channel,'guild':ctx.guild,
                 'offer':{'pokemon':[],'coins':0},'target_offer':{'pokemon':[],'coins':0},
                 'accepted':False,'confirmed':set(),'message':None}
        # Keep one canonical offer key per participant.
        trade['offers'] = {ctx.author.id:trade['offer'], target.id:trade['target_offer']}
        ACTIVE_TRADES[tid]=trade; TRADE_BY_USER[ctx.author.id]=tid; TRADE_BY_USER[target.id]=tid
        trade['message'] = await ctx.send(f'{target.mention}, {ctx.author.mention} wants to trade with you.', embed=await trade_embed(trade), view=TradeView(tid))

    @commands.command(name='tradeadd', aliases=['ta'])
    async def tradeadd(self, ctx, *args):
        trade = ACTIVE_TRADES.get(TRADE_BY_USER.get(ctx.author.id))
        if not trade or not trade['accepted']:
            return await ctx.send('❌ You need an accepted active trade first. Use `!trade @user`.')
        if not args: return await ctx.send('Usage: `!ta <pokemon_id> [id ...]`, `!ta vantacoin <amount>`, or `!ta c <amount>`.')
        offer=trade['offers'][ctx.author.id]
        if args[0].lower() in ('coin','coins','c'):
            if len(args)!=2 or not args[1].isdigit() or int(args[1])<1: return await ctx.send('Usage: `!ta vantacoin <positive amount>`')
            amount=int(args[1]); balance=get_player(ctx.author.id)[0]
            if offer['coins']+amount>balance: return await ctx.send(f'❌ You only have {balance:,} {get_vantacoin_emoji()} VantaCoins and already offered {offer["coins"]:,}.')
            offer['coins']+=amount
        else:
            try: ids=[int(x) for x in args]
            except ValueError: return await ctx.send('Use Pokémon instance IDs, or `!ta vantacoin <amount>`.')
            if len(ids)!=len(set(ids)): return await ctx.send('❌ Do not repeat Pokémon IDs.')
            translated=[]
            with db() as c:
                for box_id in ids:
                    pid=resolve_box_id(c,ctx.author.id,box_id)
                    if pid is None: return await ctx.send(f'❌ Pokémon ID `{box_id}` is not in your box.')
                    if pid in offer['pokemon']: return await ctx.send(f'❌ Pokémon ID `{box_id}` is already offered.')
                    translated.append(pid)
            offer['pokemon'].extend(translated)
        trade['confirmed'].clear(); await refresh_trade(trade)
        await ctx.send('✅ Offer updated. Both players must confirm again after any change.')

    @commands.command(name='traderemove', aliases=['tr'])
    async def traderemove(self, ctx, *args):
        # Check for !tr @user BEFORE looking up an active trade; otherwise
        # users who are not trading yet are incorrectly told no trade is active.
        if args and ctx.message.mentions and args[0].startswith('<@'):
            target = ctx.message.mentions[0]
            if ctx.author.id in TRADE_BY_USER:
                return await ctx.send('❌ You are already in an active trade.')
            return await ctx.invoke(self.trade, target=target)
        trade=ACTIVE_TRADES.get(TRADE_BY_USER.get(ctx.author.id))
        if not trade: return await ctx.send('❌ You do not have an active trade.')
        if not args: return await ctx.send('Usage: `!tr @user` to start a trade, `!tr <pokemon_id> [id ...]`, `!tr c <amount>`, `!tr confirm`, `!tr accept`, `!tr cancel`, or `!tr decline`.')
        action=args[0].lower()
        if action == 'confirm':
            return await ctx.invoke(self.tradeconfirm)
        if action == 'accept':
            if trade.get('accepted'):
                return await ctx.send('✅ This trade is already accepted. Use `!tr confirm` to confirm the offer.')
            if ctx.author.id != trade['target']:
                return await ctx.send('Only the invited player can accept this trade.')
            trade['accepted'] = True
            try:
                await trade['message'].edit(
                    content=f'**Trade accepted** — {ctx.author.mention} accepted the trade.',
                    embed=await trade_embed(trade),
                    view=None,
                )
            except (discord.HTTPException, AttributeError):
                await refresh_trade(trade)
            return await ctx.send('🤝 Trade accepted! Add Pokémon/VantaCoins with `!ta` and confirm with `!tr confirm`.')
        if action == 'cancel':
            if ctx.author.id != trade['starter']:
                return await ctx.send('Only the person who initiated this trade can cancel it. Use `!tr decline` to decline an invitation.')
            await end_trade(trade, '🚫 Trade cancelled by its initiator.')
            return
        if action == 'decline':
            if trade.get('accepted'):
                return await ctx.send('This trade has already been accepted. The initiator can use `!tr cancel` to cancel it.')
            if ctx.author.id != trade['target']:
                return await ctx.send('Only the invited player can decline this trade. The initiator can use `!tr cancel`.')
            await end_trade(trade, '👋 Trade invitation declined.')
            return
        if not trade['accepted']:
            return await ctx.send('❌ Accept the trade first with `!tr accept` or the Accept trade button.')
        offer=trade['offers'][ctx.author.id]
        if args[0].lower() in ('coin','coins','c'):
            if len(args)!=2 or not args[1].isdigit() or int(args[1])<1: return await ctx.send('Usage: `!tr c <positive amount>`')
            amount=int(args[1])
            if amount>offer['coins']: return await ctx.send(f'❌ You only offered {offer["coins"]:,} coins.')
            offer['coins']-=amount
        else:
            try: box_ids=[int(x) for x in args]
            except ValueError: return await ctx.send('Use offered Pokémon IDs or `!tr c <amount>`.')
            translated={}
            with db() as c:
                for box_id in box_ids:
                    pid=resolve_box_id(c,ctx.author.id,box_id)
                    if pid is not None: translated[box_id]=pid
            missing=[box_id for box_id in box_ids if translated.get(box_id) not in offer['pokemon']]
            if missing: return await ctx.send('❌ Not in your offer: '+', '.join(map(str,missing)))
            ids=set(translated[box_id] for box_id in box_ids)
            offer['pokemon']=[pid for pid in offer['pokemon'] if pid not in ids]
        trade['confirmed'].clear(); await refresh_trade(trade)
        await ctx.send('✅ Offer updated. Both players must confirm again after any change.')

    @commands.command(name='tradeconfirm', aliases=['tradeaccept', 'trconfirm'])
    async def tradeconfirm(self, ctx):
        await self._do_tradeconfirm(ctx)

    async def _do_tradeconfirm(self, ctx):
        trade=ACTIVE_TRADES.get(TRADE_BY_USER.get(ctx.author.id))
        if not trade or not trade['accepted']: return await ctx.send('❌ You need an accepted active trade first.')
        trade['confirmed'].add(ctx.author.id)
        if len(trade['confirmed'])<2:
            try:
                await trade['message'].edit(
                    content=f'**Trade confirmed** — {ctx.author.mention} confirmed their offer. Waiting for the other player.',
                    embed=await trade_embed(trade),
                    view=None,
                )
            except (discord.HTTPException, AttributeError):
                await refresh_trade(trade)
            return await ctx.send('✅ Your confirmation is recorded. Waiting for the other player.')
        # Validate and transfer in a single SQLite transaction; no partial trades.
        try:
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                for uid, offer in trade['offers'].items():
                    bal=c.execute('SELECT coins FROM players WHERE user_id=?',(uid,)).fetchone()
                    if not bal or bal[0] < offer['coins']: raise ValueError(f'<@{uid}> no longer has enough coins.')
                    for pid in offer['pokemon']:
                        if not c.execute('SELECT 1 FROM pokemon WHERE instance_id=? AND user_id=?',(pid,uid)).fetchone():
                            raise ValueError(f'Pokémon ID {pid} is no longer owned by <@{uid}>.')
                a,b=trade['starter'],trade['target']; oa,ob=trade['offers'][a],trade['offers'][b]
                c.execute('UPDATE players SET coins=coins-?+? WHERE user_id=?',(oa['coins'],ob['coins'],a))
                c.execute('UPDATE players SET coins=coins-?+? WHERE user_id=?',(ob['coins'],oa['coins'],b))
                for pid in oa['pokemon']: transfer_pokemon_owner(c,pid,a,b)
                for pid in ob['pokemon']: transfer_pokemon_owner(c,pid,b,a)
        except (ValueError, sqlite3.Error) as exc:
            trade['confirmed'].clear(); await ctx.send(f'❌ Trade not completed: {exc}')
            return
        # Clear the live trade UI and leave a final success status in the same message.
        success_text = f'**Trade successful!** 🎉 <@{trade["starter"]}> and <@{trade["target"]}> completed the trade.'
        await end_trade(trade, success_text)


# Player-to-player trading. Offers remain in the owners' boxes until both confirm.
ACTIVE_TRADES = {}
TRADE_BY_USER = {}
TRADE_LOCK = asyncio.Lock()

class TradeView(discord.ui.View):
    def __init__(self, trade_id):
        super().__init__(timeout=3600)
        self.trade_id = trade_id
    @discord.ui.button(label='Accept trade', style=discord.ButtonStyle.success, emoji='🤝')
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        trade = ACTIVE_TRADES.get(self.trade_id)
        if not trade or interaction.user.id != trade['target']:
            return await interaction.response.send_message('This trade is not for you or has expired.', ephemeral=True)
        trade['accepted'] = True
        await interaction.response.send_message('Trade accepted! Add Pokémon/VantaCoins with `!tradeadd` / `!ta` and confirm with `!tradeconfirm` or `!tr confirm`.', ephemeral=True)
        try:
            await trade['message'].edit(
                content=f'**Trade accepted** — {interaction.user.mention} accepted the trade.',
                embed=await trade_embed(trade),
                view=None,
            )
        except (discord.HTTPException, AttributeError):
            await refresh_trade(trade)
    @discord.ui.button(label='Decline trade', style=discord.ButtonStyle.danger, emoji='✖️')
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        trade = ACTIVE_TRADES.get(self.trade_id)
        if not trade or interaction.user.id != trade['target']:
            return await interaction.response.send_message('This trade is not for you or has expired.', ephemeral=True)
        await end_trade(trade, 'Trade declined.')
        await interaction.response.send_message('Trade declined.', ephemeral=True)

async def trade_embed(trade):
    e = discord.Embed(title='🤝 PokeVanta — Pokémon Trade', color=discord.Color.blurple())
    with db() as c:
        for side, uid in [('offer', trade['starter']), ('target_offer', trade['target'])]:
            lines=[]
            for pid in trade['offers'][uid]['pokemon']:
                row=c.execute('SELECT name,shiny,nickname,box_id FROM pokemon WHERE instance_id=? AND user_id=?',(pid,uid)).fetchone()
                if row:
                    name=row[2] or row[0]; local_id=row[3]
                    lines.append(f"✨ **{name}** (`{local_id}`)" if row[1] else f"**{name}** (`{local_id}`)")
            lines.append(f"🪙 Coins: **{trade['offers'][uid]['coins']:,}**")
            member = trade['guild'].get_member(uid) if trade.get('guild') else None
            user_label = member.mention if member else f'<@{uid}>'
            confirmed_mark = '✅' if uid in trade['confirmed'] else '⬜'
            e.add_field(name=f"{confirmed_mark} {member.display_name if member else 'Trainer'}'s offer", value=f'{user_label}\n' + ('\n'.join(lines) if lines else '*(Nothing offered yet)*'), inline=True)
    if trade['confirmed']:
        confirmation_lines = []
        for uid in (trade['starter'], trade['target']):
            member = trade['guild'].get_member(uid) if trade.get('guild') else None
            label = member.mention if member else f'<@{uid}>'
            confirmation_lines.append(f"{'✅' if uid in trade['confirmed'] else '⬜'} {label}")
        confirmations = '\nConfirmations:\n' + '\n'.join(confirmation_lines)
    else:
        confirmations = '\nConfirmations: both players still need to confirm.'
    e.description = ('Status: **Accepted**' if trade['accepted'] else 'Status: **Waiting for recipient to accept**') + confirmations + '\nBoth users must run `!tr confirm` (or `!tradeconfirm`) after reviewing the offers. Any offer change clears both confirmations. Initiator: `!tr cancel`; invitee: `!tr decline` before accepting.'
    e.set_footer(text='!tradeadd / !ta <IDs...> | !ta coins <amount> | !traderemove / !tr <IDs...> | !tr c <amount> | !cancel')
    return e

async def refresh_trade(trade):
    try:
        if trade.get('message'):
            await trade['message'].edit(embed=await trade_embed(trade), view=TradeView(trade['id']) if not trade.get('accepted') else None)
    except (discord.HTTPException, AttributeError):
        pass

async def end_trade(trade, message):
    for uid in (trade['starter'], trade['target']):
        TRADE_BY_USER.pop(uid, None)
    ACTIVE_TRADES.pop(trade['id'], None)
    # Remove stale trade controls, then announce successful trades in a fresh message.
    if message.startswith('**Trade successful!**'):
        try:
            await trade['message'].edit(content='✅ Trade completed.', embed=None, view=None)
        except (discord.HTTPException, AttributeError):
            pass
        message = f'🎉 **Trade successful!** <@{trade["starter"]}> and <@{trade["target"]}> have completed their trade!'
    try:
        await trade['channel'].send(message, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
    except discord.HTTPException:
        pass


class CarlStyleExtensions(commands.Cog):
    """Additional Carl-bot-inspired server tools kept separate from the Pokémon game Cog."""
    def __init__(self, bot):
        self.bot = bot
        with db() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS cv_tags(guild_id INTEGER NOT NULL, name TEXT NOT NULL, response TEXT NOT NULL, author_id INTEGER NOT NULL, PRIMARY KEY(guild_id,name));
            CREATE TABLE IF NOT EXISTS cv_custom_commands(guild_id INTEGER NOT NULL, name TEXT NOT NULL, response TEXT NOT NULL, author_id INTEGER NOT NULL, PRIMARY KEY(guild_id,name));
            CREATE TABLE IF NOT EXISTS cv_warnings(id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, moderator_id INTEGER NOT NULL, reason TEXT NOT NULL, created_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS cv_settings(guild_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(guild_id,key));
            CREATE TABLE IF NOT EXISTS cv_reaction_roles(guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, message_id INTEGER NOT NULL, emoji TEXT NOT NULL, role_id INTEGER NOT NULL, PRIMARY KEY(guild_id,message_id,emoji));
            CREATE TABLE IF NOT EXISTS cv_reminders(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, remind_at INTEGER NOT NULL, text TEXT NOT NULL, guild_id INTEGER NOT NULL DEFAULT 0, message_id INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS cv_starboard(message_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, star_count INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS cv_giveaways(id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, message_id INTEGER NOT NULL UNIQUE, prize TEXT NOT NULL, host_id INTEGER NOT NULL, ends_at INTEGER NOT NULL, winners_count INTEGER NOT NULL DEFAULT 1, ended INTEGER NOT NULL DEFAULT 0);
            """)
            # Migrate existing reminder tables without deleting saved reminders.
            reminder_cols = {row[1] for row in c.execute('PRAGMA table_info(cv_reminders)').fetchall()}
            if 'guild_id' not in reminder_cols:
                c.execute('ALTER TABLE cv_reminders ADD COLUMN guild_id INTEGER NOT NULL DEFAULT 0')
            if 'message_id' not in reminder_cols:
                c.execute('ALTER TABLE cv_reminders ADD COLUMN message_id INTEGER NOT NULL DEFAULT 0')

    async def cog_load(self):
        self.reminder_task = asyncio.create_task(self._reminder_loop())

    def cog_unload(self):
        task = getattr(self, 'reminder_task', None)
        if task:
            task.cancel()

    async def _reminder_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = int(time.time())
            with db() as c:
                due = c.execute('SELECT id,user_id,channel_id,text,guild_id,message_id FROM cv_reminders WHERE remind_at<=? ORDER BY remind_at LIMIT 50', (now,)).fetchall()
                if due:
                    c.executemany('DELETE FROM cv_reminders WHERE id=?', [(row[0],) for row in due])
            for reminder_id, user_id, channel_id, reminder_text, guild_id, message_id in due:
                # DM the reminder and a clickable link to the original !remind command.
                if message_id:
                    guild_part = str(guild_id) if guild_id else '@me'
                    message_link = f'https://discord.com/channels/{guild_part}/{channel_id}/{message_id}'
                    link_line = f'🔗 [Open your original reminder message]({message_link})'
                else:
                    link_line = '🔗 Original message link is unavailable for this reminder.'
                try:
                    user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                    await user.send(f"⏰ **Time's up! Here's your reminder:**\n{reminder_text[:1200]}\n\n{link_line}")
                except (discord.HTTPException, discord.NotFound, discord.Forbidden):
                    pass
            await asyncio.sleep(5)

    def is_dev(self, ctx):
        """Return whether the command author is a configured PokéVanta developer."""
        return bool(ctx.author and ctx.author.id in OWNER_IDS)

    async def require_dev(self, ctx):
        """Require the caller to have server permissions; developer status never bypasses them."""
        if ctx.guild and (ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild):
            return True
        await ctx.send('❌ You need **Manage Server** or **Administrator** permission in this server to use this command. Bot-developer status does not bypass server permissions.')
        return False

    async def require_permission(self, ctx, permission, label):
        """Require the caller's own Discord server permission; no developer bypass."""
        if ctx.guild and (ctx.author.guild_permissions.administrator or getattr(ctx.author.guild_permissions, permission, False)):
            return True
        await ctx.send(f'❌ You need **{label}** permission in this server to use this command. Bot-developer status does not bypass server permissions.')
        return False

    def setting(self, guild_id, key, value=None):
        with db() as c:
            if value is None:
                row=c.execute('SELECT value FROM cv_settings WHERE guild_id=? AND key=?',(guild_id,key)).fetchone()
                return row[0] if row else None
            c.execute('INSERT INTO cv_settings(guild_id,key,value) VALUES(?,?,?) ON CONFLICT(guild_id,key) DO UPDATE SET value=excluded.value',(guild_id,key,str(value)))
            return str(value)

    @commands.hybrid_command(name='tag')
    async def tag(self, ctx, name: str = None, *, text: str = None):
        """Use a saved tag: !tag name. Developers can create/update with !tagset."""
        if not ctx.guild: return await ctx.send('Tags are available in servers.')
        if not name: return await ctx.send('Usage: `!tag <name>` or `!tags`')
        with db() as c: row=c.execute('SELECT response FROM cv_tags WHERE guild_id=? AND name=?',(ctx.guild.id,name.lower())).fetchone()
        if row: return await ctx.send(row[0][:2000], allowed_mentions=discord.AllowedMentions.none())
        await ctx.send('Tag not found. Use `!tags` to list saved tags.')

    @commands.hybrid_command(name='tagset')
    async def tagset(self, ctx, name: str, *, response: str):
        if not await self.require_dev(ctx): return
        if not ctx.guild: return
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,32}',name): return await ctx.send('Use a tag name of 1–32 letters, numbers, underscores, or hyphens.')
        if len(response)>1900: return await ctx.send('Tag text must be 1,900 characters or fewer.')
        with db() as c: c.execute('INSERT INTO cv_tags VALUES(?,?,?,?) ON CONFLICT(guild_id,name) DO UPDATE SET response=excluded.response,author_id=excluded.author_id',(ctx.guild.id,name.lower(),response,ctx.author.id))
        await ctx.send(f'✅ Saved tag `{name.lower()}`. Use `!tag {name.lower()}` to display it.')

    @commands.hybrid_command(name='tagdelete')
    async def tagdelete(self, ctx, name: str):
        if not await self.require_dev(ctx): return
        if not ctx.guild: return
        with db() as c: cur=c.execute('DELETE FROM cv_tags WHERE guild_id=? AND name=?',(ctx.guild.id,name.lower()))
        await ctx.send('✅ Tag deleted.' if cur.rowcount else 'Tag not found.')

    @commands.hybrid_command(name='tags')
    async def tags(self, ctx):
        if not ctx.guild: return
        with db() as c: rows=c.execute('SELECT name FROM cv_tags WHERE guild_id=? ORDER BY name LIMIT 100',(ctx.guild.id,)).fetchall()
        await ctx.send('**Saved tags:** '+(', '.join(f'`{x[0]}`' for x in rows) if rows else 'No tags yet.'))

    @commands.hybrid_command(name='ccset')
    async def ccset(self, ctx, name: str, *, response: str):
        if not await self.require_dev(ctx): return
        if not ctx.guild: return
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,32}',name): return await ctx.send('Use a name of 1–32 letters, numbers, underscores, or hyphens.')
        if len(response)>1900: return await ctx.send('Response must be 1,900 characters or fewer.')
        with db() as c: c.execute('INSERT INTO cv_custom_commands VALUES(?,?,?,?) ON CONFLICT(guild_id,name) DO UPDATE SET response=excluded.response,author_id=excluded.author_id',(ctx.guild.id,name.lower(),response,ctx.author.id))
        await ctx.send(f'✅ Custom command `{name.lower()}` saved. Invoke it with `!{name.lower()}`.')

    @commands.hybrid_command(name='ccdelete')
    async def ccdelete(self, ctx, name: str):
        if not await self.require_dev(ctx): return
        if not ctx.guild: return
        with db() as c: cur=c.execute('DELETE FROM cv_custom_commands WHERE guild_id=? AND name=?',(ctx.guild.id,name.lower()))
        await ctx.send('✅ Custom command deleted.' if cur.rowcount else 'Custom command not found.')

    @commands.hybrid_command(name='warn')
    async def warn(self, ctx, member: discord.Member, *, reason='No reason provided'):
        if not await self.require_permission(ctx, 'moderate_members', 'Moderate Members'): return
        if not ctx.guild: return
        if member.bot or member.id in OWNER_IDS: return await ctx.send('❌ Cannot warn a bot or configured developer.')
        with db() as c:
            c.execute('INSERT INTO cv_warnings(guild_id,user_id,moderator_id,reason,created_at) VALUES(?,?,?,?,?)',(ctx.guild.id,member.id,ctx.author.id,reason[:1000],int(time.time())))
            count=c.execute('SELECT COUNT(*) FROM cv_warnings WHERE guild_id=? AND user_id=?',(ctx.guild.id,member.id)).fetchone()[0]
        await ctx.send(f'⚠️ Warned {member.mention}. Warning count: **{count}**. Reason: {discord.utils.escape_markdown(reason)[:500]}')

    @commands.hybrid_command(name='warnings', aliases=['infractions'])
    async def warnings(self, ctx, member: discord.Member):
        if not await self.require_permission(ctx, 'moderate_members', 'Moderate Members'): return
        if not ctx.guild: return
        with db() as c: rows=c.execute('SELECT id,reason,created_at,moderator_id FROM cv_warnings WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 10',(ctx.guild.id,member.id)).fetchall()
        if not rows: return await ctx.send(f'No saved warnings for {member.mention}.')
        e=discord.Embed(title=f'Warnings for {member}', color=discord.Color.orange())
        for wid,reason,created,mod in rows: e.add_field(name=f'#{wid} • <t:{created}:R>',value=f'{reason[:700]}\nModerator: <@{mod}>',inline=False)
        await ctx.send(embed=e)

    @commands.hybrid_command(name='clearwarnings')
    async def clearwarnings(self, ctx, member: discord.Member):
        if not await self.require_permission(ctx, 'moderate_members', 'Moderate Members'): return
        if not ctx.guild: return
        with db() as c: cur=c.execute('DELETE FROM cv_warnings WHERE guild_id=? AND user_id=?',(ctx.guild.id,member.id))
        await ctx.send(f'🧹 Removed **{cur.rowcount}** warning(s) for {member.mention}.')

    @commands.hybrid_command(name='removewarn', aliases=['removewarning', 'delwarn', 'rwarn'])
    async def removewarn(self, ctx, warning_number: int):
        """Remove one warning by its displayed warning ID: !removewarn <warning number>."""
        if not await self.require_permission(ctx, 'moderate_members', 'Moderate Members'): return
        if not ctx.guild: return
        with db() as c:
            row = c.execute('SELECT user_id,reason FROM cv_warnings WHERE guild_id=? AND id=?', (ctx.guild.id, warning_number)).fetchone()
            if not row:
                return await ctx.send(f'❌ Warning `#{warning_number}` was not found in this server.')
            c.execute('DELETE FROM cv_warnings WHERE guild_id=? AND id=?', (ctx.guild.id, warning_number))
        await ctx.send(f'🧹 Removed warning `#{warning_number}` for <@{row[0]}>. Reason was: {discord.utils.escape_markdown(row[1])[:400]}')

    @commands.hybrid_command(name='setwelcome')
    async def setwelcome(self, ctx, channel: discord.TextChannel, *, message='Welcome {user} to {server}!'):
        if not await self.require_dev(ctx): return
        if not ctx.guild: return
        if len(message)>1500: return await ctx.send('Welcome template is too long.')
        # If a URL was pasted into the template, keep it out of the welcome text and
        # use it as artwork only when it is a direct image/GIF URL. Uploaded media is preferred.
        media = next((a for a in getattr(ctx.message, 'attachments', []) if (a.content_type or '').startswith('image/')), None)
        urls = re.findall(r'https?://\S+', message)
        art_url = media.url if media else None
        if urls:
            candidate = urls[0].rstrip('.,)>')
            if candidate.lower().split('?', 1)[0].endswith(('.gif','.png','.jpg','.jpeg','.webp')):
                art_url = art_url or candidate
            elif not art_url:
                # Resolve common GIF-hosting pages (e.g. Tenor/Giphy) to their actual media URL.
                try:
                    timeout = aiohttp.ClientTimeout(total=8)
                    async with aiohttp.ClientSession(timeout=timeout, headers={'User-Agent':'Mozilla/5.0'}) as session:
                        async with session.get(candidate, allow_redirects=True) as response:
                            if response.status == 200:
                                html = await response.text(errors='ignore')
                                for pattern in (r'<meta[^>]+property=["\']og:video(?:\:url)?["\'][^>]+content=["\']([^"\']+)', r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:video(?:\:url)?["\']', r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)'):
                                    match = re.search(pattern, html, re.I)
                                    if match:
                                        found = match.group(1).replace('&amp;', '&')
                                        if found.startswith('http'):
                                            art_url = found
                                            break
                except Exception:
                    pass
            message = message.replace(urls[0], '').strip()
            if not message:
                message = 'Welcome {user} to {server}! Make yourself at home!'
        self.setting(ctx.guild.id,'welcome_channel',channel.id); self.setting(ctx.guild.id,'welcome_message',message)
        if art_url:
            self.setting(ctx.guild.id,'welcome_gif',art_url)
        await ctx.send(f'✅ Welcome messages configured for {channel.mention}.' + (' Welcome GIF/image saved!' if art_url else ' Attach the actual GIF/image file, or provide a direct .gif/.png/.jpg/.webp URL, to set the welcome artwork.') + ' Placeholders: `{user}`, `{server}`, `{member_count}`.')

    @commands.hybrid_command(name='setgoodbye')
    async def setgoodbye(self, ctx, channel: discord.TextChannel, *, message='Goodbye {user}!'):
        if not await self.require_dev(ctx): return
        if not ctx.guild: return
        if len(message)>1500: return await ctx.send('Goodbye template is too long.')
        self.setting(ctx.guild.id,'goodbye_channel',channel.id); self.setting(ctx.guild.id,'goodbye_message',message)
        await ctx.send(f'✅ Goodbye messages configured for {channel.mention}. Placeholders: `{{user}}`, `{{server}}`, `{{member_count}}`.')

    @commands.hybrid_command(name='setlog')
    async def setlog(self, ctx, channel: discord.TextChannel):
        if not await self.require_dev(ctx): return
        if not ctx.guild: return
        self.setting(ctx.guild.id,'log_channel',channel.id)
        await ctx.send(f'✅ Basic moderation/member log channel set to {channel.mention}.')

    def resolve_role(self, guild, value):
        """Resolve a role from a mention, numeric ID, or exact name."""
        match = re.fullmatch(r'<@&(\d+)>', value.strip())
        role_id = int(match.group(1)) if match else (int(value.strip()) if value.strip().isdigit() else None)
        if role_id is not None:
            return guild.get_role(role_id)
        return discord.utils.find(lambda r: r.name.casefold() == value.strip().casefold(), guild.roles)

    @commands.hybrid_command(name='role', description='Toggle a role on a member: add it or remove it.')
    @commands.guild_only()
    async def role_command(self, ctx, member: discord.Member, *, role_name_or_id: str):
        """Usage: !role @user <role name, mention, or ID>. Adds the role if absent; removes it if present."""
        if not await self.require_permission(ctx, 'manage_roles', 'Manage Roles'):
            return
        role = self.resolve_role(ctx.guild, role_name_or_id)
        if role is None:
            return await ctx.send('❌ Role not found. Use its exact name, mention, or ID.')
        if role.is_default() or role.managed:
            return await ctx.send('❌ That role cannot be assigned or removed manually.')
        bot_member = ctx.guild.me
        if bot_member is None or role >= bot_member.top_role:
            return await ctx.send('❌ I cannot assign or remove a role equal to or higher than my highest role.')
        if (not ctx.author.guild_permissions.administrator
                and role >= ctx.author.top_role):
            return await ctx.send('❌ You cannot manage a role equal to or higher than your highest role.')
        if member.id == ctx.author.id and role >= ctx.author.top_role and not ctx.author.guild_permissions.administrator:
            return await ctx.send('❌ You cannot use this command to change a role equal to or higher than your highest role.')

        has_role = role in member.roles
        try:
            if has_role:
                await member.remove_roles(role, reason=f'Role toggled by {ctx.author} ({ctx.author.id})')
                action = 'Removed'
                color = discord.Color.orange()
                title = '➖ Role Removed'
            else:
                await member.add_roles(role, reason=f'Role toggled by {ctx.author} ({ctx.author.id})')
                action = 'Added'
                color = discord.Color.green()
                title = '✅ Role Added'
        except discord.Forbidden:
            return await ctx.send('❌ I do not have permission to assign or remove that role.')
        except discord.HTTPException:
            return await ctx.send('❌ Discord could not update that role. Please try again.')

        direction = 'to' if action == 'Added' else 'from'
        embed = discord.Embed(
            title=title,
            description=f'{action} **{role.name}** {direction} **{discord.utils.escape_markdown(str(member))}**.',
            color=color,
        )
        embed.add_field(name='Member ID', value=f'`{member.id}`', inline=True)
        embed.add_field(name='Role ID', value=f'`{role.id}`', inline=True)
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.hybrid_command(name='dump', description='List usernames and IDs of members with a role.')
    @commands.guild_only()
    async def dump_role(self, ctx, *, role_name_or_id: str):
        """Usage: !dump @role or !dump <role ID>. Does not mention members."""
        if not await self.require_permission(ctx, 'manage_roles', 'Manage Roles'):
            return
        role = self.resolve_role(ctx.guild, role_name_or_id)
        if role is None:
            return await ctx.send('❌ Role not found. Use its exact name, mention, or ID.')
        # Fetch the complete member list when possible, rather than relying only on cache.
        try:
            members = [m async for m in ctx.guild.fetch_members(limit=None) if role in m.roles]
        except (discord.Forbidden, discord.HTTPException):
            members = list(role.members)
            if not members and not ctx.guild.chunked:
                return await ctx.send(
                    '❌ I could not fetch the full member list. Enable **Server Members Intent** '
                    'for this bot in the Discord Developer Portal, then restart it.'
                )
        members.sort(key=lambda m: (m.name.casefold(), m.id))
        lines = [f'{discord.utils.escape_markdown(m.name)} [{m.id}]' for m in members]
        if not lines:
            description = 'No members currently have this role.'
        else:
            description = '\n'.join(lines)
        # Split safely across messages/embeds so large roles are not truncated.
        chunks, current = [], ''
        for line in (lines if lines else ['No members currently have this role.']):
            if len(current) + len(line) + 1 > 3800:
                chunks.append(current)
                current = ''
            current += ('\n' if current else '') + line
        if current:
            chunks.append(current)
        for index, chunk in enumerate(chunks):
            embed = discord.Embed(title=f'Role Dump: {role.name}', description=chunk,
                                  color=discord.Color.blurple())
            embed.set_footer(text=f'{len(members)} member(s) • Part {index + 1}/{len(chunks)}')
            await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.hybrid_command(name='ping', description='Show bot latency and response time.')
    async def ping(self, ctx):
        import time as _time
        started = _time.perf_counter()
        message = await ctx.send('🏓 Checking ping…')
        response_ms = (_time.perf_counter() - started) * 1000
        latency_ms = self.bot.latency * 1000
        embed = discord.Embed(title='🏓 Pong!', color=discord.Color.blurple())
        embed.add_field(name='WebSocket', value=f'`{latency_ms:.0f} ms`', inline=True)
        embed.add_field(name='Response', value=f'`{response_ms:.0f} ms`', inline=True)
        await message.edit(content=None, embed=embed)

    @commands.hybrid_command(name='setautorole')
    async def setautorole(self, ctx, role: discord.Role):
        if not await self.require_dev(ctx): return
        if not ctx.guild: return
        if role.is_default() or role.managed: return await ctx.send('Choose a normal, assignable role.')
        self.setting(ctx.guild.id,'autorole_id',role.id)
        embed = discord.Embed(title='✅ Autorole Configured',
                              description=f'New members will receive **{role.name}** when the bot has permission and role hierarchy allows it.',
                              color=discord.Color.green())
        embed.add_field(name='Role', value=f'{role.name}', inline=True)
        embed.add_field(name='Role ID', value=f'`{role.id}`', inline=True)
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.hybrid_command(name='setstarboard')
    async def setstarboard(self, ctx, channel: discord.TextChannel):
        if not await self.require_dev(ctx): return
        if not ctx.guild: return
        self.setting(ctx.guild.id,'starboard_channel',channel.id)
        await ctx.send(f'⭐ Starboard destination set to {channel.mention}. React with ⭐ to nominate messages.')

    @commands.hybrid_command(name='rradd')
    async def rradd(self, ctx, message_id: int, emoji: str, role: discord.Role):
        if not await self.require_permission(ctx, 'manage_roles', 'Manage Roles'): return
        if not ctx.guild: return
        if role.is_default() or role.managed: return await ctx.send('Choose a normal, assignable role.')
        try:
            msg=await ctx.channel.fetch_message(message_id)
            await msg.add_reaction(emoji)
        except (discord.HTTPException, discord.NotFound, discord.InvalidArgument):
            return await ctx.send('❌ Could not find that message here or add the emoji. Run this command in the message channel.')
        with db() as c: c.execute('INSERT OR REPLACE INTO cv_reaction_roles VALUES(?,?,?,?,?)',(ctx.guild.id,ctx.channel.id,message_id,emoji,role.id))
        await ctx.send(f'✅ Reaction role configured: react with {emoji} on [this message]({msg.jump_url}) to receive {role.mention}.')

    @commands.hybrid_command(name='rrremove')
    async def rrremove(self, ctx, message_id: int, *, emoji: str):
        if not await self.require_permission(ctx, 'manage_roles', 'Manage Roles'): return
        if not ctx.guild: return
        with db() as c: cur=c.execute('DELETE FROM cv_reaction_roles WHERE guild_id=? AND message_id=? AND emoji=?',(ctx.guild.id,message_id,emoji))
        await ctx.send('✅ Reaction role mapping removed.' if cur.rowcount else 'Mapping not found.')

    @commands.hybrid_command(name='remind')
    async def remind(self, ctx, duration: str, *, reminder: str):
        """Set a reminder like !remind 10m drink water (s/m/h/d)."""
        m=re.fullmatch(r'(\d{1,5})(s|m|h|d)',duration.lower())
        if not m: return await ctx.send('Usage: `!remind 10m <reminder>`; units: s, m, h, d. Maximum: 30 days.')
        amount=int(m.group(1)); mult={'s':1,'m':60,'h':3600,'d':86400}[m.group(2)]; seconds=amount*mult
        if not 5<=seconds<=30*86400: return await ctx.send('Reminder must be 5 seconds to 30 days from now.')
        remind_at = int(time.time() + seconds)
        guild_id = ctx.guild.id if ctx.guild else 0
        source_message_id = getattr(getattr(ctx, 'message', None), 'id', 0) or 0
        with db() as c:
            c.execute('INSERT INTO cv_reminders(user_id,channel_id,remind_at,text,guild_id,message_id) VALUES(?,?,?,?,?,?)', (ctx.author.id, ctx.channel.id, remind_at, reminder[:1000], guild_id, source_message_id))
        await ctx.send(f'⏰ Reminder saved for **{reminder[:1000]}**  <t:{remind_at}:R>.')

    @commands.hybrid_command(name='automodword')
    async def automodword(self, ctx, action: str, *, word: str):
        if not await self.require_dev(ctx): return
        if not ctx.guild: return
        action=action.lower()
        if action not in ('add','remove'): return await ctx.send('Usage: `!automodword add <word>` or `!automodword remove <word>`.')
        words=set((self.setting(ctx.guild.id,'blocked_words','') or '').split('|'))
        word=word.strip().lower()[:100]
        if not word: return await ctx.send('Provide a word or phrase.')
        if action=='add': words.add(word)
        else: words.discard(word)
        self.setting(ctx.guild.id,'blocked_words','|'.join(sorted(x for x in words if x)))
        await ctx.send(f'✅ Filter phrase {"added" if action=="add" else "removed"}.')

    @commands.hybrid_command(name='automodwords')
    async def automodwords(self, ctx):
        if not await self.require_dev(ctx): return
        if not ctx.guild: return
        words=[w for w in (self.setting(ctx.guild.id,'blocked_words','') or '').split('|') if w]
        await ctx.send('**Filtered phrases:** '+(', '.join(f'`{discord.utils.escape_markdown(w)}`' for w in words) if words else 'None configured.'))

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Revert self-service or other unauthorized nickname changes while frozen."""
        if before.nick == after.nick or after.bot:
            return
        with db() as c:
            freeze = c.execute('SELECT locked_nick FROM nick_freezes WHERE guild_id=? AND user_id=?', (after.guild.id, after.id)).fetchone()
        if not freeze:
            return
        locked_nick = freeze[0]
        if after.nick == locked_nick:
            return
        try:
            await after.edit(nick=locked_nick, reason='Enforcing server-specific nickname freeze')
        except (discord.Forbidden, discord.HTTPException):
            # Missing Manage Nicknames or role hierarchy can prevent enforcement; don't crash the bot.
            return

    @commands.hybrid_command(name='setnick')
    async def setnick(self, ctx, member: discord.Member, *, nickname: str = None):
        if not await self.require_permission(ctx, 'manage_nicknames', 'Manage Nicknames'): return
        if not ctx.guild:
            return await ctx.send('❌ This command only works in a server.')
        with db() as c:
            freeze = c.execute('SELECT freezer_id,locked_nick FROM nick_freezes WHERE guild_id=? AND user_id=?', (ctx.guild.id, member.id)).fetchone()
            if freeze and freeze[0] != ctx.author.id:
                return await ctx.send(f'❌ {member.mention} has a nickname freeze. Only the member who used `!nickfreeze` can change their nickname with `!setnick`.')
            # Update the enforced nickname before editing so the gateway event recognizes this as authorized.
            if freeze:
                c.execute('UPDATE nick_freezes SET locked_nick=? WHERE guild_id=? AND user_id=?', (nickname, ctx.guild.id, member.id))
        try:
            await member.edit(nick=nickname, reason=f'Nickname change by {ctx.author} ({ctx.author.id})')
            await ctx.send(f'✅ Updated nickname for {member.mention}.')
        except discord.Forbidden:
            if freeze:
                with db() as c: c.execute('UPDATE nick_freezes SET locked_nick=? WHERE guild_id=? AND user_id=?', (freeze[1], ctx.guild.id, member.id))
            await ctx.send('❌ Discord denied the nickname change; check permissions and role hierarchy.')
        except discord.HTTPException as exc:
            if freeze:
                with db() as c: c.execute('UPDATE nick_freezes SET locked_nick=? WHERE guild_id=? AND user_id=?', (freeze[1], ctx.guild.id, member.id))
            await ctx.send(f'❌ Nickname change failed: `{exc}`')

    @commands.hybrid_command(name='nickfreeze', description='Freeze a member nickname so only you can change it.')
    @commands.guild_only()
    async def nickfreeze(self, ctx, member: discord.Member):
        if not await self.require_permission(ctx, 'manage_nicknames', 'Manage Nicknames'): return
        if member.id == ctx.author.id:
            return await ctx.send('❌ You cannot freeze your own nickname.')
        with db() as c:
            existing = c.execute('SELECT freezer_id FROM nick_freezes WHERE guild_id=? AND user_id=?', (ctx.guild.id, member.id)).fetchone()
            if existing:
                owner = ctx.guild.get_member(existing[0])
                owner_label = owner.mention if owner else f'`{existing[0]}`'
                return await ctx.send(f'❌ {member.mention} is already nickname-frozen by {owner_label}.')
            c.execute('INSERT INTO nick_freezes(guild_id,user_id,freezer_id,original_nick,locked_nick) VALUES(?,?,?,?,?)',
                      (ctx.guild.id, member.id, ctx.author.id, member.nick, member.nick))
        await ctx.send(f'🔒 Nickname frozen for {member.mention}. Only you can change it with `!setnick`; use `!nickreset {member.mention}` to restore their original nickname and remove the freeze.')

    @commands.hybrid_command(name='nickreset', description='Restore a member original nickname and remove nickname freeze.')
    @commands.guild_only()
    async def nickreset(self, ctx, member: discord.Member):
        if not await self.require_permission(ctx, 'manage_nicknames', 'Manage Nicknames'): return
        with db() as c:
            freeze = c.execute('SELECT freezer_id,original_nick FROM nick_freezes WHERE guild_id=? AND user_id=?', (ctx.guild.id, member.id)).fetchone()
        if not freeze:
            return await ctx.send(f'❌ {member.mention} does not have an active nickname freeze.')
        if freeze[0] != ctx.author.id:
            return await ctx.send('❌ Only the person who froze this member can reset their nickname and remove the freeze.')
        # Remove the freeze before restoring the nickname so the event listener won't re-freeze it.
        with db() as c:
            c.execute('DELETE FROM nick_freezes WHERE guild_id=? AND user_id=?', (ctx.guild.id, member.id))
        try:
            await member.edit(nick=freeze[1], reason=f'Nickname freeze reset by {ctx.author} ({ctx.author.id})')
        except discord.Forbidden:
            with db() as c:
                c.execute('INSERT OR REPLACE INTO nick_freezes(guild_id,user_id,freezer_id,original_nick,locked_nick) VALUES(?,?,?,?,?)', (ctx.guild.id, member.id, freeze[0], freeze[1], member.nick))
            return await ctx.send('❌ Discord denied the nickname reset; check permissions and role hierarchy. The freeze is still active.')
        except discord.HTTPException as exc:
            with db() as c:
                c.execute('INSERT OR REPLACE INTO nick_freezes(guild_id,user_id,freezer_id,original_nick,locked_nick) VALUES(?,?,?,?,?)', (ctx.guild.id, member.id, freeze[0], freeze[1], member.nick))
            return await ctx.send(f'❌ Nickname reset failed: `{exc}`. The freeze is still active.')
        await ctx.send(f'✅ {member.mention}’s original nickname has been restored and the freeze removed.')

    @commands.hybrid_command(name='roleadd')
    async def roleadd(self, ctx, member: discord.Member, role: discord.Role):
        if not await self.require_permission(ctx, 'manage_roles', 'Manage Roles'): return
        try:
            await member.add_roles(role, reason=f'PokéVanta developer action by {ctx.author} ({ctx.author.id})')
            await ctx.send(f'✅ Added {role.mention} to {member.mention}.')
        except discord.Forbidden: await ctx.send('❌ Discord denied the role change; check Manage Roles and role hierarchy.')

    @commands.hybrid_command(name='roleremove')
    async def roleremove(self, ctx, member: discord.Member, role: discord.Role):
        if not await self.require_permission(ctx, 'manage_roles', 'Manage Roles'): return
        try:
            await member.remove_roles(role, reason=f'PokéVanta developer action by {ctx.author} ({ctx.author.id})')
            await ctx.send(f'✅ Removed {role.mention} from {member.mention}.')
        except discord.Forbidden: await ctx.send('❌ Discord denied the role change; check Manage Roles and role hierarchy.')

    @commands.hybrid_command(name='rolecreate', description='Create a server role. Optional color can be a hex value like #5865F2.')
    async def rolecreate(self, ctx, name: str, color: str = None):
        """Create a new server role: !rolecreate <name> [hex_color]."""
        if not await self.require_permission(ctx, 'manage_roles', 'Manage Roles'): return
        if not ctx.guild: return await ctx.send('❌ This command only works in a server.')
        name = name.strip()
        if not name or len(name) > 100:
            return await ctx.send('❌ Role names must be between 1 and 100 characters.')
        role_color = discord.Color.default()
        if color:
            try:
                value = color.strip().removeprefix('#').removeprefix('0x')
                if len(value) not in (3, 6) or any(ch not in '0123456789abcdefABCDEF' for ch in value):
                    raise ValueError('invalid hex color')
                if len(value) == 3:
                    value = ''.join(ch * 2 for ch in value)
                role_color = discord.Color(int(value, 16))
            except (TypeError, ValueError):
                return await ctx.send('❌ Invalid color. Use a hex color such as `#5865F2`, or omit the color.')
        try:
            role = await ctx.guild.create_role(name=name, color=role_color, reason=f'Role created by {ctx.author} ({ctx.author.id})')
            await ctx.send(f'✅ Created role {role.mention} (`{role.name}`).', allowed_mentions=discord.AllowedMentions.none())
        except discord.Forbidden:
            await ctx.send('❌ I cannot create roles. Give the bot Manage Roles permission and move its highest role above the roles it manages.')
        except discord.HTTPException as exc:
            await ctx.send(f'❌ Role creation failed: {type(exc).__name__}: {str(exc)[:180]}')

    @commands.hybrid_command(name='roledelete', description='Delete a server role by mention, ID, or exact name.')
    async def roledelete(self, ctx, *, role: str):
        """Delete a server role: !roledelete <role mention|ID|exact name>."""
        if not await self.require_permission(ctx, 'manage_roles', 'Manage Roles'): return
        if not ctx.guild: return await ctx.send('❌ This command only works in a server.')
        role_text = role.strip()
        target = None
        match = re.fullmatch(r'<@&?(\d+)>', role_text)
        if match:
            target = ctx.guild.get_role(int(match.group(1)))
        elif role_text.isdigit():
            target = ctx.guild.get_role(int(role_text))
        else:
            matches = [r for r in ctx.guild.roles if r.name.casefold() == role_text.casefold()]
            if len(matches) == 1:
                target = matches[0]
            elif len(matches) > 1:
                return await ctx.send('❌ More than one role has that name. Please use its mention or ID.')
        if target is None:
            return await ctx.send('❌ I could not find that role. Use its mention, ID, or exact name.')
        if target.is_default() or target.managed:
            return await ctx.send('❌ The @everyone role and integration-managed roles cannot be deleted.')
        bot_member = ctx.guild.me
        if bot_member and target >= bot_member.top_role:
            return await ctx.send('❌ That role is at or above my highest role. Move my bot role above it first.')
        try:
            role_name = target.name
            await target.delete(reason=f'Role deleted by {ctx.author} ({ctx.author.id})')
            await ctx.send(f'🗑️ Deleted role **{discord.utils.escape_markdown(role_name)}**.')
        except discord.Forbidden:
            await ctx.send('❌ I cannot delete that role. Check Manage Roles permission and the bot role hierarchy.')
        except discord.HTTPException as exc:
            await ctx.send(f'❌ Role deletion failed: {type(exc).__name__}: {str(exc)[:180]}')

    @commands.hybrid_command(name='announce')
    async def announce(self, ctx, channel: Optional[discord.TextChannel] = None):
        """Set up a match announcement by choosing two different roles and a time (IST)."""
        if not await self.require_dev(ctx): return
        if not ctx.guild:
            return await ctx.send('❌ This command only works in a server.')
        active = getattr(self.bot, 'active_match_announces', None)
        if active is None:
            self.bot.active_match_announces = {}
            active = self.bot.active_match_announces
        if ctx.guild.id in active:
            return await ctx.send('❌ A match announcement setup or scheduled match is already running here. Use `!cancel` first.')
        active[ctx.guild.id] = {'task': asyncio.current_task(), 'channel': None, 'locked': False, 'cancelled': False}
        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            return await ctx.send('❌ Please use a text channel.')

        cog = self
        class MatchRoleSelect(discord.ui.RoleSelect):
            def __init__(self, step):
                super().__init__(placeholder='Choose a role…', min_values=1, max_values=1)
                self.step = step
            async def callback(self, interaction: discord.Interaction):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message('Only the person who started this setup can choose roles.', ephemeral=True)
                role = self.values[0]
                if role.is_default() or role.managed:
                    return await interaction.response.send_message('Please choose a regular server role.', ephemeral=True)
                if self.step == 1:
                    view.first_role = role
                    view.clear_items()
                    view.add_item(discord.ui.Button(label=f'First role: {role.name}', style=discord.ButtonStyle.secondary, disabled=True))
                    view.add_item(ChooseSecondRoleButton())
                    await interaction.response.edit_message(content=f'First role selected: **{discord.utils.escape_markdown(role.name)}**\nNow press **Choose second role**. The first role cannot be selected again.', view=view)
                else:
                    if role.id == view.first_role.id:
                        return await interaction.response.send_message('That role is already selected. Choose a different role.', ephemeral=True)
                    view.second_role = role
                    selection_done.set()
                    view.stop()
                    await interaction.response.edit_message(content=f'✅ Roles selected: **{discord.utils.escape_markdown(view.first_role.name)}** vs **{discord.utils.escape_markdown(view.second_role.name)}**\nI will now ask for the match time in chat.', view=None)

        class FirstRoleView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=180)
                self.add_item(MatchRoleSelect(1))

        class SecondRoleView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=180)
                self.add_item(MatchRoleSelect(2))

        class ChooseSecondRoleButton(discord.ui.Button):
            def __init__(self):
                super().__init__(label='Choose second role', style=discord.ButtonStyle.primary)
            async def callback(self, interaction: discord.Interaction):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message('Only the person who started this setup can choose roles.', ephemeral=True)
                second_view = SecondRoleView()
                await interaction.response.edit_message(content=f'First role: {view.first_role.mention}\nChoose a different role for the second team.', view=second_view)

        class StartRoleView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=180)
            @discord.ui.button(label='Choose first role', style=discord.ButtonStyle.primary, emoji='⚔️')
            async def choose_first(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message('Only the person who started this setup can choose roles.', ephemeral=True)
                await interaction.response.edit_message(content='Choose the first team role:', view=FirstRoleView())

        view = type('MatchRoleState', (discord.ui.View,), {}) (timeout=180)
        view.first_role = None
        view.second_role = None
        selection_done = asyncio.Event()
        # The view's state is retained across the button/select interactions above.
        msg = await ctx.send('⚔️ **Match announcement setup**\nPress the button to choose the first team role.', view=StartRoleView())
        # State is attached to the top-level view used by the callbacks.
        # Use a small message-scoped state object so nested views share the same selections.
        # (The callbacks close over this variable.)
        try:
            await asyncio.wait_for(selection_done.wait(), timeout=180)
            def check(message):
                return message.author.id == ctx.author.id and message.channel.id == ctx.channel.id
            await ctx.send('🕒 Send the match time in chat using **HH:MM** (24-hour format, IST), for example `20:30`.')
            time_message = await self.bot.wait_for('message', check=check, timeout=180)
            raw_time = time_message.content.strip()
            match = re.fullmatch(r'([01]?\d|2[0-3]):([0-5]\d)', raw_time)
            if not match:
                return await ctx.send('❌ Invalid time. Run `!announce` again and enter the time as `HH:MM`, in IST.')
            hour, minute = int(match.group(1)), int(match.group(2))
            ist = ZoneInfo('Asia/Kolkata')
            now = datetime.now(ist)
            starts = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if starts <= now:
                starts += timedelta(days=1)
            starts_at = int(starts.timestamp())
            if not view.first_role or not view.second_role:
                return await ctx.send('❌ Role selection was not completed. Run `!announce` again.')
            embed = discord.Embed(title='⚔️ Match timings:', color=discord.Color.blurple())
            embed.description = (f'**Teams:** {view.first_role.mention} vs {view.second_role.mention}\n'
                                 f'**Match time:** <t:{starts_at}:F>\n<t:{starts_at}:R>')
            # Lock first, then post the scheduled announcement. Role pings happen only in this announcement.
            # Lock the announcement channel immediately after posting the match notice.
            # Only change @everyone's send_messages overwrite; leave other channel permissions intact.
            everyone_role = ctx.guild.default_role
            await target_channel.set_permissions(
                everyone_role,
                send_messages=False,
                reason=f'Match scheduled by {ctx.author} ({ctx.author.id}); lock until match time'
            )
            active[ctx.guild.id]['channel'] = target_channel
            active[ctx.guild.id]['locked'] = True
            await target_channel.send(content=f'{view.first_role.mention} {view.second_role.mention}', embed=embed, allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False))
            await asyncio.sleep(max(0, starts_at - int(time.time())))
            # Open the channel when the scheduled match time arrives.
            await target_channel.set_permissions(
                everyone_role,
                send_messages=None,
                reason='Scheduled match time reached; restoring match channel permissions'
            )
            active[ctx.guild.id]['locked'] = False
            await target_channel.send(
                f'🔓 The match channel is now open!\n⚔️ **Match time — gather here!** The match starts now.\n<t:{starts_at}:F>\n{view.first_role.mention} {view.second_role.mention}',
                allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False)
            )
        except asyncio.TimeoutError:
            await ctx.send('⌛ Match setup timed out. Run `!announce` to try again.')
        except asyncio.CancelledError:
            state = active.get(ctx.guild.id, {})
            locked_channel = state.get('channel')
            if state.get('locked') and locked_channel:
                try:
                    await locked_channel.set_permissions(ctx.guild.default_role, send_messages=None, reason='Match cancelled by command')
                    await locked_channel.send('🛑 The scheduled match was cancelled. Channel permissions have been restored.', allowed_mentions=discord.AllowedMentions.none())
                except discord.HTTPException:
                    pass
            raise
        except discord.Forbidden:
            await ctx.send('❌ I cannot manage channel permissions or send messages there. Check my Manage Channels, View Channel and Send Messages permissions.')
        finally:
            state = getattr(self.bot, 'active_match_announces', {}).get(ctx.guild.id)
            if state and state.get('task') is asyncio.current_task():
                getattr(self.bot, 'active_match_announces', {}).pop(ctx.guild.id, None)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.bot: return
        with db() as c: settings=dict(c.execute('SELECT key,value FROM cv_settings WHERE guild_id=?',(member.guild.id,)).fetchall())
        role_id=settings.get('autorole_id')
        if role_id:
            role=member.guild.get_role(int(role_id))
            if role and not role.managed:
                try: await member.add_roles(role,reason='Configured PokéVanta autorole')
                except (discord.Forbidden,discord.HTTPException): pass
        channel_id=settings.get('welcome_channel'); channel=member.guild.get_channel(int(channel_id)) if channel_id else None
        if channel:
            template=settings.get('welcome_message','Welcome {user} to {server}!')
            text=template.replace('{user}',member.mention).replace('{server}',member.guild.name).replace('{member_count}',str(member.guild.member_count))
            # Never print a raw GIF hosting URL in the welcome embed; artwork belongs in the image slot.
            text=re.sub(r'https?://\S+', '', text).strip()
            welcome = discord.Embed(title=f'🎉 Welcome to {member.guild.name}!', description=f'{text[:3500]}\n\nYou are our **{member.guild.member_count:,}th** member. Make yourself at home!', color=discord.Color.from_rgb(88, 101, 242), timestamp=discord.utils.utcnow())
            welcome.set_thumbnail(url=member.display_avatar.url)
            welcome.set_footer(text='We’re glad you’re here!')
            art=settings.get('welcome_gif')
            if art: welcome.set_image(url=art)
            try: await channel.send(content=member.mention, embed=welcome, allowed_mentions=discord.AllowedMentions(users=True,roles=False,everyone=False))
            except discord.HTTPException: pass
        log_id=settings.get('log_channel'); log=member.guild.get_channel(int(log_id)) if log_id else None
        if log:
            try: await log.send(embed=discord.Embed(description=f'📥 {member.mention} joined the server.',color=discord.Color.green()))
            except discord.HTTPException: pass

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        with db() as c: settings=dict(c.execute('SELECT key,value FROM cv_settings WHERE guild_id=?',(member.guild.id,)).fetchall())
        channel_id=settings.get('goodbye_channel'); channel=member.guild.get_channel(int(channel_id)) if channel_id else None
        if channel:
            text=settings.get('goodbye_message','Goodbye {user}!').replace('{user}',str(member)).replace('{server}',member.guild.name).replace('{member_count}',str(member.guild.member_count))
            try: await channel.send(text[:1900],allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException: pass
        log_id=settings.get('log_channel'); log=member.guild.get_channel(int(log_id)) if log_id else None
        if log:
            try: await log.send(embed=discord.Embed(description=f'📤 **{discord.utils.escape_markdown(str(member))}** left the server. ID: `{member.id}`',color=discord.Color.orange()))
            except discord.HTTPException: pass

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild: return
        # Simple configurable phrase filter; this does not replace Discord AutoMod.
        words=(self.setting(message.guild.id,'blocked_words','') or '').split('|')
        content=message.content.casefold()
        if words and any(w and w.casefold() in content for w in words):
            try: await message.delete()
            except (discord.Forbidden,discord.NotFound,discord.HTTPException): pass
            return
        # Saved custom commands are invoked by their exact prefix name.
        if content.startswith(PREFIX) and len(content)>1:
            name=content[1:].split()[0].lower()
            with db() as c: row=c.execute('SELECT response FROM cv_custom_commands WHERE guild_id=? AND name=?',(message.guild.id,name)).fetchone()
            if row:
                try: await message.channel.send(row[0][:1900],allowed_mentions=discord.AllowedMentions.none())
                except discord.HTTPException: pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.guild_id is None or (self.bot.user and payload.user_id==self.bot.user.id): return
        emoji=str(payload.emoji)
        with db() as c:
            rr=c.execute('SELECT role_id FROM cv_reaction_roles WHERE guild_id=? AND message_id=? AND emoji=?',(payload.guild_id,payload.message_id,emoji)).fetchone()
            starboard=c.execute('SELECT value FROM cv_settings WHERE guild_id=? AND key=?',(payload.guild_id,'starboard_channel')).fetchone()
        guild=self.bot.get_guild(payload.guild_id)
        if not guild: return
        if rr:
            member=guild.get_member(payload.user_id); role=guild.get_role(rr[0])
            if member and role and not member.bot:
                try: await member.add_roles(role,reason='Configured reaction role')
                except (discord.Forbidden,discord.HTTPException): pass
        if emoji=='⭐' and starboard:
            try:
                channel=guild.get_channel(int(starboard[0])); source=guild.get_channel(payload.channel_id)
                if not channel or not source: return
                msg=await source.fetch_message(payload.message_id)
                count=next((r.count for r in msg.reactions if str(r.emoji)=='⭐'),0)
                if count>=3 and source.id!=channel.id:
                    with db() as c: exists=c.execute('SELECT 1 FROM cv_starboard WHERE message_id=?',(msg.id,)).fetchone()
                    if not exists:
                        embed=discord.Embed(description=msg.content[:3500] or '*No text content*',color=discord.Color.gold())
                        embed.set_author(name=str(msg.author),icon_url=msg.author.display_avatar.url)
                        embed.add_field(name='Source',value=f'[Jump to message]({msg.jump_url}) • ⭐ {count}')
                        if msg.attachments: embed.set_image(url=msg.attachments[0].url)
                        await channel.send(embed=embed,allowed_mentions=discord.AllowedMentions.none())
                        with db() as c: c.execute('INSERT OR REPLACE INTO cv_starboard VALUES(?,?,?,?)',(msg.id,guild.id,channel.id,count))
            except (discord.HTTPException,discord.Forbidden,discord.NotFound): pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.guild_id is None: return
        with db() as c: rr=c.execute('SELECT role_id FROM cv_reaction_roles WHERE guild_id=? AND message_id=? AND emoji=?',(payload.guild_id,payload.message_id,str(payload.emoji))).fetchone()
        if not rr: return
        guild=self.bot.get_guild(payload.guild_id); member=guild.get_member(payload.user_id) if guild else None; role=guild.get_role(rr[0]) if guild else None
        if member and role:
            try: await member.remove_roles(role,reason='Configured reaction role removed')
            except (discord.Forbidden,discord.HTTPException): pass

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not before.guild or before.author.bot or before.content==after.content: return
        log_id=self.setting(before.guild.id,'log_channel')
        channel=before.guild.get_channel(int(log_id)) if log_id else None
        if channel:
            e=discord.Embed(title='✏️ Message edited',description=f'Author: {before.author.mention}\n[Jump to edited message]({after.jump_url})',color=discord.Color.orange())
            e.add_field(name='Before',value=before.content[:900] or '*empty*',inline=False); e.add_field(name='After',value=after.content[:900] or '*empty*',inline=False)
            try: await channel.send(embed=e,allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException: pass

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.guild or message.author.bot: return
        log_id=self.setting(message.guild.id,'log_channel'); channel=message.guild.get_channel(int(log_id)) if log_id else None
        if channel:
            e=discord.Embed(title='🗑️ Message deleted',description=f'Author: {message.author.mention}\nChannel: {message.channel.mention}',color=discord.Color.red())
            if message.content: e.add_field(name='Content',value=message.content[:1000],inline=False)
            try: await channel.send(embed=e,allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException: pass


    # Persistent reaction-based giveaways. Durations accept s/m/h/d (e.g. 30m, 2h, 1d).
    def _parse_giveaway_duration(self, value):
        match = re.fullmatch(r'\s*(\d+)\s*([smhd])\s*', value.lower())
        if not match:
            return None
        amount = int(match.group(1))
        seconds = amount * {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[match.group(2)]
        return seconds if 10 <= seconds <= 30 * 86400 else None

    async def _giveaway_participants(self, channel, message_id):
        try:
            message = await channel.fetch_message(int(message_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError):
            return None, None
        reaction = discord.utils.get(message.reactions, emoji='🎉')
        if reaction is None:
            return message, []
        users = []
        try:
            async for user in reaction.users(limit=None):
                if not user.bot:
                    users.append(user)
        except (discord.Forbidden, discord.HTTPException):
            return message, None
        return message, users

    async def _finish_giveaway(self, ctx, row, reroll=False):
        giveaway_id, guild_id, channel_id, message_id, prize, host_id, ends_at, winners_count, ended = row
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return await ctx.send('❌ I cannot access the giveaway channel. Check my View Channel and Read Message History permissions.')
        message, participants = await self._giveaway_participants(channel, message_id)
        if message is None:
            return await ctx.send('❌ I cannot find that giveaway message. It may have been deleted, or I lack channel permissions.')
        if participants is None:
            return await ctx.send('❌ I could not read giveaway reactions. Check my Read Message History permission.')
        if not participants:
            winners = []
        else:
            winners = random.sample(participants, min(max(1, winners_count), len(participants)))
        if not reroll and not ended:
            with db() as c:
                c.execute('UPDATE cv_giveaways SET ended=1 WHERE id=?', (giveaway_id,))
        if winners:
            winner_text = ', '.join(user.mention for user in winners)
            result = f'🎉 Congratulations {winner_text}! You won **{prize}**!'
        else:
            result = f'🎉 Giveaway for **{prize}** ended with no valid entries.'
        try:
            await channel.send(result, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
        except discord.HTTPException:
            return await ctx.send('⚠️ I selected the winner(s), but could not post in the giveaway channel.')
        return await ctx.send(('🔄 Giveaway rerolled.' if reroll else '✅ Giveaway ended.') + f' Message ID: `{message_id}`')

    @commands.command(name='giveaway', aliases=['gstart', 'giveawaystart', 'gstartgiveaway'])
    @commands.guild_only()
    async def giveaway_start(self, ctx, duration: str = None, winners: int = 1, *, prize: str = None):
        """Start a reaction giveaway. Usage: !giveaway <duration> <winner_count> <prize>; duration examples: 30m, 2h, 1d."""
        if not duration or not prize:
            return await ctx.send('Usage: `!giveaway <duration> <winner_count> <prize>` — example: `!giveaway 2h 1 Nitro`')
        seconds = self._parse_giveaway_duration(duration)
        if seconds is None:
            return await ctx.send('❌ Invalid duration. Use `10s`, `30m`, `2h`, or `1d` (10 seconds to 30 days).')
        if not 1 <= winners <= 20:
            return await ctx.send('❌ Winner count must be between 1 and 20.')
        if not ctx.guild or not (ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild):
            return await ctx.send('❌ Giveaway commands require **Manage Server** or **Administrator** permission in this server.')
        ends_at = int(time.time()) + seconds
        embed = discord.Embed(title='🎉 GIVEAWAY', description=f'**Prize:** {discord.utils.escape_markdown(prize)[:200]}\n**Host:** {ctx.author.mention}\n**Winners:** {winners}\n**Ends:** <t:{ends_at}:R>\n\nReact with 🎉 to enter!', color=discord.Color.gold())
        embed.set_footer(text='PokéVanta Giveaways')
        try:
            message = await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
            await message.add_reaction('🎉')
        except discord.HTTPException:
            return await ctx.send('❌ I could not create the giveaway. Check Send Messages, Embed Links, and Add Reactions permissions.')
        with db() as c:
            c.execute('INSERT INTO cv_giveaways(guild_id,channel_id,message_id,prize,host_id,ends_at,winners_count,ended) VALUES(?,?,?,?,?,?,?,0)',
                      (ctx.guild.id, ctx.channel.id, message.id, prize[:200], ctx.author.id, ends_at, winners))
        await ctx.send(f'✅ Giveaway created! End it with `!giveawayend {message.id}` or reroll it with `!giveawayreroll {message.id}`.')

    @commands.command(name='giveawayend', aliases=['gend', 'gendgiveaway', 'endgiveaway'])
    @commands.guild_only()
    async def giveaway_end(self, ctx, message_id: int):
        """End a giveaway by its giveaway message ID. Alias: !gend."""
        if not ctx.guild or not (ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild):
            return await ctx.send('❌ Giveaway commands require **Manage Server** or **Administrator** permission in this server.')
        with db() as c:
            row = c.execute('SELECT id,guild_id,channel_id,message_id,prize,host_id,ends_at,winners_count,ended FROM cv_giveaways WHERE message_id=? AND guild_id=?', (message_id, ctx.guild.id)).fetchone()
        if not row:
            return await ctx.send('❌ I could not find a giveaway with that message ID in this server.')
        if row[8]:
            return await ctx.send('❌ That giveaway has already ended. Use `!giveawayreroll <message_id>` to pick again.')
        await self._finish_giveaway(ctx, row)

    @commands.command(name='giveawayreroll', aliases=['greroll', 'grerollgiveaway', 'rerollgiveaway'])
    @commands.guild_only()
    async def giveaway_reroll(self, ctx, message_id: int):
        """Pick new winner(s) for an ended giveaway. Alias: !greroll."""
        if not ctx.guild or not (ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild):
            return await ctx.send('❌ Giveaway commands require **Manage Server** or **Administrator** permission in this server.')
        with db() as c:
            row = c.execute('SELECT id,guild_id,channel_id,message_id,prize,host_id,ends_at,winners_count,ended FROM cv_giveaways WHERE message_id=? AND guild_id=?', (message_id, ctx.guild.id)).fetchone()
        if not row:
            return await ctx.send('❌ I could not find a giveaway with that message ID in this server.')
        if not row[8]:
            return await ctx.send('❌ That giveaway is still active. End it first with `!giveawayend <message_id>`.')
        await self._finish_giveaway(ctx, row, reroll=True)




class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True  # Required for reliable member lists and join/leave events.
        super().__init__(command_prefix=PREFIX, intents=intents, help_command=None)
    async def setup_hook(self):
        await self.add_cog(Game(self));await self.add_cog(CarlStyleExtensions(self));await load_pokemon_list();await self.tree.sync()
    async def on_ready(self):
        print(f'Logged in as {self.user}')
        print(f'Loaded {len(POKEMON_LIST)} Pokémon species.')
        expected = ('role', 'dump', 'setautorole', 'ping')
        registered = {command.name for command in self.walk_commands()}
        missing = [name for name in expected if name not in registered]
        if missing:
            print(f'[COMMAND REGISTRATION ERROR] Missing commands: {", ".join(missing)}')
        else:
            print('[COMMAND CHECK] Registered: !role, !dump, !setautorole, !ping')
    async def on_message(self, message):
        if message.author.bot:
            return
        # Banned users can still chat normally; PokéVanta-prefixed commands are blocked.
        if message.content.startswith(PREFIX) and message.author.id not in OWNER_IDS:
            with db() as c:
                ban = c.execute('SELECT reason FROM bot_bans WHERE user_id=?', (message.author.id,)).fetchone()
            if ban:
                e = discord.Embed(title='🚫 You are banned from PokéVanta', description='You cannot use PokéVanta commands because your account has been banned from the bot.', color=discord.Color.red())
                e.add_field(name='Reason', value=discord.utils.escape_markdown(ban[0])[:1024], inline=False)
                e.set_footer(text='Contact a PokéVanta developer if you believe this ban was issued by mistake.')
                try:
                    await message.reply(embed=e, mention_author=False)
                except discord.HTTPException:
                    pass
                return
        await self.process_commands(message)
    async def on_command_error(self, ctx, error):
        # Handle expected command/input problems separately. Unexpected exceptions
        # are logged with their full traceback so they can be fixed accurately.
        if isinstance(error, commands.CommandNotFound):
            content = (getattr(ctx.message, 'content', '') or '').strip().lower()
            requested = ('!role', '!dump', '!setautorole', '!ping')
            if any(content == name or content.startswith(name + ' ') for name in requested):
                try:
                    await ctx.send(
                        '❌ That command is not registered in the running bot. '
                        'Check that this updated Python file is the one being launched, then restart the bot.',
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except discord.HTTPException:
                    pass
            return
        if isinstance(error, commands.CommandOnCooldown):
            try:
                await ctx.send(f'⏳ Try again in {error.retry_after:.1f} seconds.', allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass
            return
        if isinstance(error, commands.CheckFailure):
            # Some cogs/checks already send their own explanation.
            return

        original = getattr(error, 'original', error)
        name = ctx.command.qualified_name if ctx.command else 'unknown'
        if isinstance(original, commands.MissingRequiredArgument):
            # Use the command's registered signature rather than guessing a usage string.
            signature = getattr(ctx.command, 'signature', '') if ctx.command else ''
            usage = f'!{name} {signature}'.strip()
            try:
                await ctx.send(f'Usage: `{usage}`', allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass
            return
        if isinstance(original, (commands.BadArgument, commands.BadUnionArgument, commands.MemberNotFound,
                                 commands.UserNotFound, commands.RoleNotFound, commands.ChannelNotFound,
                                 commands.EmojiNotFound, commands.MessageNotFound)):
            signature = getattr(ctx.command, 'signature', '') if ctx.command else ''
            usage = f'!{name} {signature}'.strip()
            try:
                await ctx.send(f'⚠️ I could not understand one of those arguments. Usage: `{usage}`',
                               allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass
            return

        import traceback
        print(f'\n[PokéVanta command error] command=!{name} | author_id={getattr(ctx.author, "id", "unknown")} | guild_id={getattr(ctx.guild, "id", "DM")}')
        traceback.print_exception(type(original), original, original.__traceback__)
        try:
            await ctx.send('❌ This command failed unexpectedly. The full error has been printed in Termux. Please send the traceback to the bot maintainer.',
                           allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as send_error:
            print(f'Could not send command-error notice (missing permissions or API failure): {send_error!r}')

async def main():
    global SESSION
    setup()
    if not TOKEN:raise RuntimeError('Set DISCORD_TOKEN first.')
    bot=Bot()
    try:await bot.start(TOKEN)
    finally:
        if SESSION:await SESSION.close()
if __name__=='__main__':asyncio.run(main())
