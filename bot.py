import os, random, sqlite3, asyncio, time, re
from typing import Optional
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv('DISCORD_TOKEN')
PREFIX = '!'
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pokemon_game.db')
OWNER_ID = int(os.getenv('DISCORD_OWNER_ID', '0') or 0)
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
  16: ('choice-band', 'Choice Band', 2200, 'Held item; increases physical damage', 'cho16'),
  17: ('choice-specs', 'Choice Specs', 2200, 'Held item; increases special damage', 'cho17'),
  18: ('choice-scarf', 'Choice Scarf', 2200, 'Held item; boosts battle damage slightly in this simplified battle system', 'cho18'),
  19: ('life-orb', 'Life Orb', 2500, 'Held item; boosts damage', 'lif19'),
  20: ('expert-belt', 'Expert Belt', 2000, 'Held item; boosts super-effective damage', 'exp20'),
  21: ('focus-sash', 'Focus Sash', 2000, 'Held item; may help survive a hit', 'foc21'),
  22: ('assault-vest', 'Assault Vest', 1800, 'Held item; reduces incoming damage slightly', 'ass22'),
  23: ('rocky-helmet', 'Rocky Helmet', 1800, 'Held item; retaliates with minor damage after being hit', 'roc23'),
  24: ('muscle-band', 'Muscle Band', 1500, 'Held item; boosts physical damage', 'mus24'),
  25: ('wise-glasses', 'Wise Glasses', 1500, 'Held item; boosts special damage', 'wis25'),
  26: ('shell-bell', 'Shell Bell', 1600, 'Held item; heals a little after dealing damage', 'she26'),
  27: ('safety-goggles', 'Safety Goggles', 1200, 'Held item; status protection flavour effect', 'saf27'),
  28: ('heavy-duty-boots', 'Heavy-Duty Boots', 1300, 'Held item; defensive utility', 'hea28'),
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
}
ITEM_BY_KEY = {v[0]: (k, *v) for k,v in SHOP_ITEMS.items()}
SHOP_ALIASES = {}
for _pid, (_key, _label, _cost, _desc, _short) in SHOP_ITEMS.items():
    for _alias in (_key, _label, _short, str(_pid)):
        SHOP_ALIASES[re.sub(r'[^a-z0-9]', '', _alias.lower())] = _pid

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
        c.execute('CREATE TABLE IF NOT EXISTS players(user_id INTEGER PRIMARY KEY, coins INTEGER DEFAULT 500, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, daily INTEGER DEFAULT 0, daily_streak INTEGER DEFAULT 0)')
        cols=[r[1] for r in c.execute('PRAGMA table_info(players)').fetchall()]
        if 'daily_streak' not in cols: c.execute('ALTER TABLE players ADD COLUMN daily_streak INTEGER DEFAULT 0')
        c.execute('CREATE TABLE IF NOT EXISTS pokemon(instance_id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,dex_id INTEGER,name TEXT,level INTEGER DEFAULT 5,xp INTEGER DEFAULT 0,shiny INTEGER DEFAULT 0,nickname TEXT DEFAULT "",hp INTEGER DEFAULT 1,max_hp INTEGER DEFAULT 1,held_item TEXT DEFAULT "",status_condition TEXT DEFAULT "")')
        pcols=[r[1] for r in c.execute('PRAGMA table_info(pokemon)').fetchall()]
        if 'held_item' not in pcols: c.execute('ALTER TABLE pokemon ADD COLUMN held_item TEXT DEFAULT ""')
        if 'status_condition' not in pcols: c.execute('ALTER TABLE pokemon ADD COLUMN status_condition TEXT DEFAULT ""')
        c.execute('CREATE TABLE IF NOT EXISTS hunt_counts(user_id INTEGER PRIMARY KEY, count INTEGER DEFAULT 0)')
        c.execute('CREATE TABLE IF NOT EXISTS boss_encounters(user_id INTEGER PRIMARY KEY,dex_id INTEGER,name TEXT,level INTEGER,shiny INTEGER DEFAULT 0)')
        c.execute('CREATE TABLE IF NOT EXISTS boss_party(user_id INTEGER,slot INTEGER,instance_id INTEGER,PRIMARY KEY(user_id,slot),UNIQUE(user_id,instance_id))')
        c.execute('CREATE TABLE IF NOT EXISTS team(user_id INTEGER,slot INTEGER,instance_id INTEGER,PRIMARY KEY(user_id,slot))')
        c.execute('CREATE TABLE IF NOT EXISTS inventory(user_id INTEGER,item TEXT,amount INTEGER,PRIMARY KEY(user_id,item))')
        c.execute('CREATE TABLE IF NOT EXISTS encounters(user_id INTEGER PRIMARY KEY,dex_id INTEGER,name TEXT,shiny INTEGER DEFAULT 0,level INTEGER DEFAULT 5,hints_used INTEGER DEFAULT 0)')
        # One server-wide special encounter: the first correct guess claims it.
        c.execute('CREATE TABLE IF NOT EXISTS global_encounter(id INTEGER PRIMARY KEY CHECK(id=1),dex_id INTEGER,name TEXT,shiny INTEGER DEFAULT 1,level INTEGER DEFAULT 5,spawned_by INTEGER)')
        cols=[r[1] for r in c.execute('PRAGMA table_info(encounters)').fetchall()]
        if 'hints_used' not in cols: c.execute('ALTER TABLE encounters ADD COLUMN hints_used INTEGER DEFAULT 0')

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

def calc_damage(attacker, defender, move, level):
    a=stats(attacker); b=stats(defender); physical=move.get('damage_class',{}).get('name')=='physical'
    atk=a.get('attack' if physical else 'special-attack',50); defense=b.get('defense' if physical else 'special-defense',50)
    mt=move['type']['name']; at=[x['type']['name'] for x in attacker['types']]; dt=[x['type']['name'] for x in defender['types']]
    stab=1.5 if mt in at else 1; eff=effectiveness(mt,dt); crit=1.5 if random.random()<.0625 else 1
    damage=max(1,int((((2*level/5+2)*(move.get('power') or 40)*atk/max(1,defense))/50+2)*stab*eff*crit*random.uniform(.85,1)))
    return damage,eff,crit>1

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
            button=discord.ui.Button(label=m['name'].replace('-', ' ').title()[:80],style=discord.ButtonStyle.primary)
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


class NPCBattleView(TimedView):
    def __init__(self,uid,row,enemy,boss=False,boss_shiny=False,active_boss_battles=None):
        super().__init__(timeout=None, timeout_text=''); self.uid=uid; self.row=row; self.enemy=enemy; self.player_hp=row[8]; self.enemy_hp=max_hp(enemy,enemy['_level']); self.player_status=(row[11] or '') if len(row)>11 else ''; self.enemy_status=''; self.moves=[]; self.busy=False; self.boss=boss; self.boss_shiny=boss_shiny; self.party=[]; self.active_boss_battles=active_boss_battles
    async def on_timeout(self):
        if self.boss and self.active_boss_battles is not None:
            self.active_boss_battles.discard(self.uid)
        await super().on_timeout()
    async def build(self):
        self.moves=await get_moves(await pokemon_data(self.row[2]),4)
        choose=discord.ui.Button(label='Choose Move',style=discord.ButtonStyle.primary,row=0)
        async def open_picker(inter):
            if inter.user.id!=self.uid:return await inter.response.send_message('This is not your battle.',ephemeral=True)
            if self.busy:return await inter.response.send_message('Wait for the turn to finish.',ephemeral=True)
            await inter.response.send_message('Choose a move for your active Pokémon (only you can see these options):',view=NPCMovePicker(self),ephemeral=True)
        choose.callback=open_picker; self.add_item(choose)
        if self.boss:
            with db() as c: rows=c.execute('SELECT p.* FROM boss_party bp JOIN pokemon p ON p.instance_id=bp.instance_id WHERE bp.user_id=? ORDER BY bp.slot',(self.uid,)).fetchall()
            self.party=list(rows)
            for i,row in enumerate(self.party):
                b=discord.ui.Button(label=f'Switch: {row[3].title()}'[:80],style=discord.ButtonStyle.secondary,row=2,disabled=row[0]==self.row[0]); b.callback=self.switch_cb(i); self.add_item(b)
    def switch_cb(self,i):
        async def f(inter):
            if inter.user.id!=self.uid:return await inter.response.send_message('This is not your battle.',ephemeral=True)
            if self.busy:return await inter.response.send_message('Wait for the turn to finish.',ephemeral=True)
            target=self.party[i]
            if target[0]==self.row[0]:return await inter.response.send_message('That Pokémon is already active.',ephemeral=True)
            if target[8]<=0:return await inter.response.send_message('That Pokémon has fainted. Choose another teammate.',ephemeral=True)
            with db() as c:c.execute('UPDATE pokemon SET hp=?,status_condition=? WHERE instance_id=?',(self.player_hp,self.player_status,self.row[0]))
            self.row=target; self.player_hp=target[8]; self.moves=await get_moves(await pokemon_data(target[2]),4)
            # Refresh the move buttons and switch buttons for the new active Pokémon.
            for item in list(self.children): self.remove_item(item)
            await self.build()
            em=discord.Embed(title='🔥 Legendary 3v1 — Pokémon switched!',description=f'**Active:** {target[3].title()} Lv.{target[4]}\nHP {hp_bar(self.player_hp,target[9])}\nStatus: **{status_label(self.player_status)}**\n**Boss:** {display_name(self.enemy)} Lv.{self.enemy['_level']}\nHP {hp_bar(self.enemy_hp,max_hp(self.enemy,self.enemy["_level"]))}\nStatus: **{status_label(self.enemy_status)}**\n🎙️ **Commentator:** A tactical switch! {target[3].title()} enters the arena.\nChoose a move or switch between your three Pokémon.')
            if sprite(self.enemy,shiny=self.boss_shiny):em.set_image(url=sprite(self.enemy,shiny=self.boss_shiny))
            await inter.response.edit_message(embed=em,view=self)
        return f
    def cb(self,i):
        async def f(inter):
            if inter.user.id!=self.uid:return await inter.response.send_message('This is not your battle.',ephemeral=True)
            if self.busy:return await inter.response.send_message('Wait for the turn.',ephemeral=True)
            self.busy=True
            try: await self.turn(inter,self.moves[i])
            except Exception as e:
                if not inter.response.is_done(): await inter.response.send_message(f'Battle error: `{e}`',ephemeral=True)
            finally:self.busy=False
        return f
    async def update_battle(self, inter, **kwargs):
        if self.message is not None:
            content=kwargs.get('content')
            view=kwargs.get('view', self)
            if content is not None and view is self:
                e=discord.Embed(title=('🔥 Legendary Boss Battle' if self.boss else '⚔️ Pokémon Battle Arena'), description=content, color=discord.Color.dark_red() if self.boss else discord.Color.red())
                own=await pokemon_data(self.row[2])
                if sprite(own):e.set_thumbnail(url=sprite(own))
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
            if held in ('life-orb','choice-band','choice-specs','choice-scarf','muscle-band','wise-glasses'): dmg=int(dmg*1.2)
            if held=='expert-belt' and eff>1:dmg=int(dmg*1.2)
            type_item={'black-belt':'fighting','charcoal':'fire','mystic-water':'water','magnet':'electric','miracle-seed':'grass','never-melt-ice':'ice','spell-tag':'ghost','dragon-fang':'dragon','silk-scarf':'normal','sharp-beak':'flying','poison-barb':'poison','soft-sand':'ground','hard-stone':'rock','silver-powder':'bug','black-glasses':'dark','twisted-spoon':'psychic','metal-coat':'steel','pixie-plate':'fairy'}
            if type_item.get(held)==move.get('type',{}).get('name'): dmg=int(dmg*1.2)
            # Simple species abilities with direct battle impact; Pokédex displays the full ability list.
            ability_names={a['ability']['name'] for a in p.get('abilities',[])}
            if 'adaptability' in ability_names and move.get('type',{}).get('name') in [t['type']['name'] for t in p['types']]: dmg=int(dmg*1.15)
            if 'huge-power' in ability_names or 'pure-power' in ability_names: dmg=int(dmg*1.15)
            enemyheld=self.enemy.get('_held_item','')
            if enemyheld=='assault-vest':dmg=int(dmg*.9)
            if enemyheld=='focus-sash' and self.enemy_hp>0 and dmg>=self.enemy_hp: dmg=max(0,self.enemy_hp-1)
            self.enemy_hp=max(0,self.enemy_hp-dmg)
            status_msg=''
            inflicted=status_from_move(move)
            if inflicted and not self.enemy_status:
                self.enemy_status=inflicted; status_msg=f'\n🧪 {display_name(self.enemy)} is now **{status_label(inflicted)}**!'
            if held=='shell-bell' and dmg>0:self.player_hp=min(self.row[9],self.player_hp+max(1,dmg//8))
            msg=f'⚔️ **{move["name"].replace("-"," ").title()}** dealt **{dmg}** damage!'+status_msg
            if crit:msg+=' 💥 Critical hit!'
            if eff>1:msg+=' Super effective!'
            elif 0<eff<1:msg+=' Not very effective...'
            elif eff==0:msg+=' No effect!'
            msg += '\n' + battle_commentary(self.row[3], move, dmg, eff, crit, inflicted if inflicted and not status_msg == '' else '')
        if self.enemy_hp<=0:
            r=random.randint(80,220);x=random.randint(40,90);add_progress(self.uid,r,x)
            if self.boss:
                mh=max_hp(self.enemy,self.enemy['_level'])
                with db() as c:
                    cur=c.execute('INSERT INTO pokemon(user_id,dex_id,name,level,shiny,hp,max_hp) VALUES(?,?,?,?,?,?,?)',(self.uid,self.enemy['id'],self.enemy['name'],self.enemy['_level'],int(self.boss_shiny),mh,mh)); iid=cur.lastrowid
                    if not c.execute('SELECT 1 FROM team WHERE user_id=?',(self.uid,)).fetchone(): c.execute('INSERT OR REPLACE INTO team(user_id,slot,instance_id) VALUES(?,?,?)',(self.uid,1,iid))
                    c.execute('DELETE FROM boss_encounters WHERE user_id=?',(self.uid,))
                    c.execute('DELETE FROM boss_party WHERE user_id=?',(self.uid,))
                if self.active_boss_battles is not None:self.active_boss_battles.discard(self.uid)
                jackpot=10000 if self.boss_shiny else 0
                if jackpot: add_progress(self.uid,coins=jackpot)
                jackpot_text=f'\n\n🎰 JACKPOT! <@{self.uid}> won a shiny legendary boss! **10,000 coins** have been credited to your balance! 💰' if jackpot else ''
                return await self.update_battle(inter, content=f'🏆 <@{self.uid}> won the legendary fight!\n{msg}\n\n🎉 You obtained {"✨ SHINY " if self.boss_shiny else ""}**{display_name(self.enemy)}** Lv. {self.enemy["_level"]} — ID `{iid}`!\n💰 +{r} coins • ⭐ +{x} XP{jackpot_text}',view=None)
            return await self.update_battle(inter, content=f'🏆 **Victory!**\n{msg}\n\nYour Pokémon: {hp_bar(self.player_hp,self.row[9])}\nOpponent: {hp_bar(self.enemy_hp,max_hp(self.enemy,self.enemy["_level"]))}\n\n💰 +{r} coins • ⭐ +{x} XP',view=None)
        self.enemy_hp, tickmsg=status_tick(self.enemy_status,self.enemy_hp,max_hp(self.enemy,self.enemy['_level']))
        if tickmsg: msg+='\n'+tickmsg
        if self.enemy_hp<=0:
            r=random.randint(80,220);x=random.randint(40,90);add_progress(self.uid,r,x)
            if self.boss and self.active_boss_battles is not None:self.active_boss_battles.discard(self.uid)
            return await self.update_battle(inter, content=f'🏆 **Victory!**\n{msg}\n\nYour Pokémon: {hp_bar(self.player_hp,self.row[9])}\nOpponent: {hp_bar(self.enemy_hp,max_hp(self.enemy,self.enemy["_level"]))}\n\n💰 +{r} coins • ⭐ +{x} XP',view=None)
        em=random.choice(await get_moves(self.enemy)); dmg,eff,crit=calc_damage(self.enemy,p,em,self.enemy['_level'])
        if held=='assault-vest': dmg=int(dmg*.9)
        if held=='focus-sash' and self.player_hp>0 and dmg>=self.player_hp: dmg=max(0,self.player_hp-1)
        if held=='rocky-helmet': self.enemy_hp=max(0,self.enemy_hp-max(1,int(dmg*.08)))
        self.player_hp=max(0,self.player_hp-dmg)
        inflicted=status_from_move(em)
        if inflicted and not self.player_status:
            self.player_status=inflicted; msg+=f'\n🧪 **{self.row[3].title()}** is now **{status_label(inflicted)}**!'
        self.player_hp,tickmsg=status_tick(self.player_status,self.player_hp,self.row[9])
        if tickmsg: msg+='\n'+tickmsg
        if held=='leftovers' and self.player_hp>0:self.player_hp=min(self.row[9],self.player_hp+max(1,self.row[9]//16))
        msg+=f'\n🔥 **{display_name(self.enemy)}** used **{display_name(em)}** for **{dmg}** damage.'
        msg+='\n'+battle_commentary(self.enemy, em, dmg, eff, crit, inflicted if inflicted and not self.player_status == '' else '')
        if self.player_hp<=0:
            with db() as c:c.execute('UPDATE pokemon SET hp=0 WHERE instance_id=?',(self.row[0],))
            if self.boss and any(r[0]!=self.row[0] and r[8]>0 for r in self.party):
                return await self.update_battle(inter, content=f'💥 **{self.row[3].title()} fainted!**\n{msg}\nSwitch to another teammate using the buttons below.',view=self)
            if self.boss:
                # A lost boss challenge is consumed: return to regular hunts, no retry.
                with db() as c:
                    c.execute('DELETE FROM boss_encounters WHERE user_id=?',(self.uid,))
                    c.execute('DELETE FROM boss_party WHERE user_id=?',(self.uid,))
                if self.active_boss_battles is not None:self.active_boss_battles.discard(self.uid)
                return await self.update_battle(inter, content=f'💥 **Boss challenge lost!**\n{msg}\n\nThe legendary escaped. You are back to normal `!hunt` encounters. Complete 10 more hunts to trigger another boss challenge.',view=None)
            return await self.update_battle(inter, content=f'💥 **Defeat!**\n{msg}\n\nYour Pokémon: {hp_bar(self.player_hp,self.row[9])}\nOpponent: {hp_bar(self.enemy_hp,max_hp(self.enemy,self.enemy["_level"]))}\n\nUse `!useitem Potion <pokemon_id>` to heal HP, or a status-curing berry if needed.',view=None)
        with db() as c:c.execute('UPDATE pokemon SET hp=?,status_condition=? WHERE instance_id=?',(self.player_hp,self.player_status,self.row[0]))
        await self.update_battle(inter, content=f'⚔️ **NPC Battle**\n{msg}\n\nYour Pokémon: {hp_bar(self.player_hp,self.row[9])}\nStatus: **{status_label(self.player_status)}**\n👾 Enemy: {hp_bar(self.enemy_hp,max_hp(self.enemy,self.enemy["_level"]))}\nStatus: **{status_label(self.enemy_status)}**',view=self)

class PvPMovePicker(TimedView):
    """Ephemeral move menu: only the trainer who opened it can see/use these moves."""
    def __init__(self, battle, uid):
        super().__init__(timeout=None, timeout_text='')
        self.battle=battle; self.uid=uid
        for i,m in enumerate(battle.moves[uid]):
            button=discord.ui.Button(label=m['name'].replace('-', ' ').title()[:80], style=discord.ButtonStyle.primary)
            async def pick(interaction, index=i):
                if interaction.user.id != self.uid:
                    return await interaction.response.send_message('These moves are private to the trainer who opened this menu.', ephemeral=True)
                if self.battle.over:
                    return await interaction.response.edit_message(content='This battle is already over.', view=None)
                await interaction.response.edit_message(content=f'✅ You selected **{self.battle.moves[self.uid][index]["name"].replace("-", " ").title()}**.', view=None)
                await self.battle.submit_move(self.uid, index)
            button.callback=pick; self.add_item(button)

class PvPBattle:
    def __init__(self,a,b,ra,rb): self.a=a;self.b=b;self.ra=ra;self.rb=rb;self.hp={a:ra[8],b:rb[8]};self.status={a:(ra[11] or ''),b:(rb[11] or '')};self.moves={};self.picks={};self.message=None;self.lock=asyncio.Lock();self.over=False;self.last_text='🎙️ **Commentator:** The trainers step into the arena—this battle is underway!'
    async def setup(self):
        for uid,row in [(self.a,self.ra),(self.b,self.rb)]:self.moves[uid]=await get_moves(await pokemon_data(row[2]),4)
    async def render(self):
        lines=[f'⚔️ **Pokémon Trainer Battle** <@{self.a}> vs <@{self.b}>','',f'🔴 **{self.ra[3].title()}** Lv.{self.ra[4]} — {hp_bar(self.hp[self.a],self.ra[9])}\nStatus: **{status_label(self.status[self.a])}**',f'🔵 **{self.rb[3].title()}** Lv.{self.rb[4]} — {hp_bar(self.hp[self.b],self.rb[9])}\nStatus: **{status_label(self.status[self.b])}**','',f'🎮 Moves selected: **{len(self.picks)}/2**',self.last_text,'Click **Choose Move**. Each trainer gets a private move menu.']
        return '\n'.join(lines)
    async def make_embed(self):
        e=discord.Embed(title='⚔️ Pokémon Battle Arena', description=await self.render(), color=discord.Color.red())
        da=await pokemon_data(self.ra[2]); dbb=await pokemon_data(self.rb[2])
        if sprite(da): e.set_thumbnail(url=sprite(da))
        if sprite(dbb): e.set_image(url=sprite(dbb))
        e.set_footer(text='Left sprite: challenger • Main sprite: opponent')
        return e
    def view(self):
        v=TimedView(timeout=None, timeout_text='')
        button=discord.ui.Button(label='Choose Move',style=discord.ButtonStyle.primary)
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
                await self.message.edit(embed=await self.make_embed(),view=self.view())
                return
            await self.resolve()
    async def resolve(self):
        speeds={}
        for uid in (self.a,self.b):
            row=self.ra if uid==self.a else self.rb
            speeds[uid]=stats(await pokemon_data(row[2])).get('speed',0)
        order=sorted([self.a,self.b],key=lambda u:speeds[u],reverse=True)
        # Keep action messages visible in the public battle log, but never reveal a move before both trainers have selected.
        log=[]
        for uid in order:
            if self.hp[uid]<=0:continue
            opp=self.b if uid==self.a else self.a; row=self.ra if uid==self.a else self.rb; orow=self.rb if uid==self.a else self.ra
            attacker=await pokemon_data(row[2]); defender=await pokemon_data(orow[2]); move=self.moves[uid][self.picks[uid]]
            move_name=move.get('name','').lower()
            healing_moves={'recover','roost','moonlight','synthesis','soft-boiled','slack-off','shore-up'}
            if move_name in healing_moves:
                before=self.hp[uid]; maximum=row[9]; self.hp[uid]=min(maximum,self.hp[uid]+max(1,int(maximum*0.5))); restored=self.hp[uid]-before
                log.append(f'💚 **{row[3].title()}** used **{move_name.replace("-"," " ).title()}** and recovered **{restored} HP**!\nHP: {hp_bar(self.hp[uid],maximum)}\n🎙️ **Commentator:** A timely recovery! {row[3].title()} regains its strength.')
                continue
            if random.randint(1,100)>(move.get('accuracy') or 100): log.append(f'💨 **{row[3].title()}** used **{move["name"].title()}**, but missed!\n{battle_commentary(row[3], move, 0)}');continue
            before_hp=self.hp[opp]
            dmg,eff,crit=calc_damage(attacker,defender,move,row[4]);self.hp[opp]=max(0,self.hp[opp]-dmg)
            inflicted=status_from_move(move)
            status_msg=''
            if inflicted and not self.status[opp]:
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
            self.over=True;ACTIVE_VIEWS.pop(self.a,None);ACTIVE_VIEWS.pop(self.b,None);loser=self.b if winner==self.a else self.a;add_progress(winner,coins=250,xp=100);self.last_text+='\n\n'+f'🏆 <@{winner}> won the fight! +250 coins +100 XP'
            with db() as c:
                c.execute('UPDATE pokemon SET hp=?,status_condition=? WHERE instance_id=?',(self.hp[self.a],self.status[self.a],self.ra[0]));c.execute('UPDATE pokemon SET hp=?,status_condition=? WHERE instance_id=?',(self.hp[self.b],self.status[self.b],self.rb[0]))
            await self.message.edit(embed=await self.make_embed(),view=None)
        else:
            await self.message.edit(embed=await self.make_embed(),view=self.view())

stats_cache={}

class ShopView(TimedView):
    """Paged shop catalogue. Only the player who opened it can navigate."""
    ITEMS_PER_PAGE = 6

    def __init__(self, owner_id):
        super().__init__(timeout=180, timeout_text='⏰ This menu timed out. Run the command again to reopen it.')
        self.owner_id = owner_id
        self.page = 0
        self.pages = max(1, (len(SHOP_ITEMS) + self.ITEMS_PER_PAGE - 1) // self.ITEMS_PER_PAGE)
        self.update_buttons()

    def update_buttons(self):
        self.previous.disabled = self.page <= 0
        self.next.disabled = self.page >= self.pages - 1

    def make_embed(self):
        entries = list(SHOP_ITEMS.items())
        start = self.page * self.ITEMS_PER_PAGE
        current = entries[start:start + self.ITEMS_PER_PAGE]
        embed = discord.Embed(
            title='🛒 Poké Mart — Battle Items',
            description='Buy with `!shop buy <item> <quantity>`. Each item has a unique shortform.\n\nUse **Previous** and **Next** to browse the market.'
        )
        for pid, (key, label, cost, desc, shortform) in current:
            embed.add_field(name=f'ID {pid} • {label} — {cost:,} coins', value=f'{desc}\nShortform: `{shortform}`\nBuy: `!shop buy {shortform}`', inline=False)
        embed.set_footer(text=f'Page {self.page + 1}/{self.pages} • !shop buy <item> <quantity>')
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


class BoxView(TimedView):
    """Paged Pokémon collection; deliberately hides current HP."""
    ITEMS_PER_PAGE = 10
    def __init__(self, owner_id, entries, category='all'):
        super().__init__(timeout=180, timeout_text='⏰ This menu timed out. Run the command again to reopen it.')
        self.owner_id=owner_id; self.entries=entries; self.page=0; self.category=category
        self.pages=max(1, (len(entries)+self.ITEMS_PER_PAGE-1)//self.ITEMS_PER_PAGE)
        self.update_buttons()
    def update_buttons(self):
        self.previous.disabled=self.page<=0
        self.next.disabled=self.page>=self.pages-1
    def make_embed(self):
        labels={'all':'All Pokémon','hp':'Highest max HP first','status':'Pokémon with status conditions','legendary':'Legendary Pokémon','shiny':'Shiny Pokémon','mythical':'Mythical Pokémon','ultrabeast':'Ultra Beasts','damaged':'Pokémon below max HP'}
        embed=discord.Embed(title=f'📦 Pokémon Box — {labels.get(self.category, "All Pokémon")}', description='Use `!select <ID>` to choose your active Pokémon and `!info <ID>` to inspect it.', color=discord.Color.blurple())
        current=self.entries[self.page*self.ITEMS_PER_PAGE:(self.page+1)*self.ITEMS_PER_PAGE]
        if not current:
            embed.description=f'No Pokémon found for this category. Try `!box` to see your full collection.'
        else:
            lines=[]
            for row in current:
                iid,name,level,shiny,held=row[:5]
                line=f'`ID {iid}`  {"✨ " if shiny else ""}**{name.replace("-"," ").title()}** · Lv. {level}'
                if len(row)>7:
                    hp,maxhp,status=row[5],row[6],row[7]
                    if self.category in ('hp','damaged'): line+=f' · HP {hp}/{maxhp}'
                    if status: line+=f' · 🧪 {status.replace("-"," ").title()}'
                if held: line+=f'\n　🎒 Held: {held.replace("-"," ").title()}'
                lines.append(line)
            embed.description='\n\n'.join(lines)
        embed.set_footer(text=f'Page {self.page+1}/{self.pages} • {len(self.entries)} Pokémon • !box <category>')
        return embed
    async def interaction_check(self, interaction):
        if interaction.user.id!=self.owner_id:
            await interaction.response.send_message('Only the player who opened this box can change pages.',ephemeral=True); return False
        return True
    @discord.ui.button(label='Previous',emoji='⬅️',style=discord.ButtonStyle.secondary)
    async def previous(self,interaction,button):
        self.page=max(0,self.page-1); self.update_buttons(); await interaction.response.edit_message(embed=self.make_embed(),view=self)
    @discord.ui.button(label='Next',emoji='➡️',style=discord.ButtonStyle.primary)
    async def next(self,interaction,button):
        self.page=min(self.pages-1,self.page+1); self.update_buttons(); await interaction.response.edit_message(embed=self.make_embed(),view=self)


class Game(commands.Cog):
    def __init__(self,bot):self.bot=bot;self.challenges={};self.active_boss_battles=set()
    @commands.hybrid_command(name='start',aliases=['begin','st'],description='Start your adventure.')
    async def start(self,ctx):ensure_player(ctx.author.id);await ctx.send('🎒 **Adventure started!** Use `!hunt` or `/hunt`.')
    @commands.hybrid_command(name='hunt',aliases=['h','search'],description='Find a wild Pokémon; every tenth hunt triggers a boss battle.')
    async def hunt(self,ctx):
        try:
            uid=ctx.author.id
            # A trainer cannot start another hunt while a battle/challenge is active.
            active_view=ACTIVE_VIEWS.get(uid)
            if uid in self.challenges or isinstance(active_view, (NPCBattleView, PvPBattle)):
                return await ctx.send('⚠️ You are already in an active battle or challenge. Finish it or use `!cancel` before hunting.')
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
            await ctx.send(embed=e)
        except Exception as e:await ctx.send(f'❌ Hunt error: `{e}`')

    @commands.command(name='add',aliases=['addboss','bossadd'])
    async def add_boss_pokemon(self,ctx,*pokemon_ids:int):
        """Add one or more owned Pokémon to the three-slot legendary boss team."""
        uid=ctx.author.id
        if not pokemon_ids:
            return await ctx.send('Usage: `!add <pokemon_id> [pokemon_id ...]` — example: `!add 1 2 3`.')
        with db() as c:
            boss=c.execute('SELECT 1 FROM boss_encounters WHERE user_id=?',(uid,)).fetchone()
            if not boss:return await ctx.send('❌ You do not have an active boss encounter. Every 10 hunts unlocks one; devs can use `!legendarybattle` to create one.')
            added=[]; errors=[]
            for pokemon_id in pokemon_ids:
                existing_rows=c.execute('SELECT slot,instance_id FROM boss_party WHERE user_id=? ORDER BY slot',(uid,)).fetchall()
                if any(r[1]==pokemon_id for r in existing_rows):
                    errors.append(f'ID `{pokemon_id}` is already on the team'); continue
                if len(existing_rows)>=3:
                    errors.append(f'ID `{pokemon_id}` not added: team is full (3/3)'); continue
                row=c.execute('SELECT instance_id,name,level FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,uid)).fetchone()
                if not row:
                    errors.append(f'ID `{pokemon_id}` is not yours (check `!box`)'); continue
                used={r[0] for r in existing_rows}
                slot=next(i for i in (1,2,3) if i not in used)
                c.execute('INSERT INTO boss_party(user_id,slot,instance_id) VALUES(?,?,?)',(uid,slot,pokemon_id))
                added.append(f'**{row[1].title()}** Lv.{row[2]} (ID `{pokemon_id}`)')
            count=c.execute('SELECT COUNT(*) FROM boss_party WHERE user_id=?',(uid,)).fetchone()[0]
        lines=[]
        if added: lines.append('✅ Added: '+', '.join(added)+f'. Boss team: **{count}/3**.')
        if errors: lines.append('⚠️ '+ '; '.join(errors)+'.')
        if count==3: lines.append('Team complete! Use `!legendarybattle` to begin.')
        await ctx.send('\n'.join(lines) if lines else 'No Pokémon were added.')

    @commands.command(name='remove',aliases=['removeboss','bossremove'])
    async def remove_boss_pokemon(self,ctx,*pokemon_ids:int):
        """Remove one or more Pokémon IDs from the legendary boss team."""
        uid=ctx.author.id
        if not pokemon_ids:
            return await ctx.send('Usage: `!remove <pokemon_id> [pokemon_id ...]` — example: `!remove 1 2`.')
        with db() as c:
            boss=c.execute('SELECT 1 FROM boss_encounters WHERE user_id=?',(uid,)).fetchone()
            if not boss:return await ctx.send('❌ You do not have an active boss encounter. There is no boss team to edit.')
            removed=[]; missing=[]
            for pokemon_id in pokemon_ids:
                row=c.execute('SELECT bp.slot,p.name FROM boss_party bp JOIN pokemon p ON p.instance_id=bp.instance_id WHERE bp.user_id=? AND bp.instance_id=?',(uid,pokemon_id)).fetchone()
                if not row:
                    missing.append(str(pokemon_id)); continue
                c.execute('DELETE FROM boss_party WHERE user_id=? AND instance_id=?',(uid,pokemon_id))
                removed.append(f'**{row[1].title()}** (ID `{pokemon_id}`)')
            # Re-pack slots after removals so later additions fill the first available slots.
            remaining=c.execute('SELECT instance_id FROM boss_party WHERE user_id=? ORDER BY slot',(uid,)).fetchall()
            c.execute('DELETE FROM boss_party WHERE user_id=?',(uid,))
            for slot,row in enumerate(remaining,1):
                c.execute('INSERT INTO boss_party(user_id,slot,instance_id) VALUES(?,?,?)',(uid,slot,row[0]))
            count=len(remaining)
        lines=[]
        if removed: lines.append('✅ Removed: '+', '.join(removed)+f'. Boss team: **{count}/3**.')
        if missing: lines.append('⚠️ Not on your boss team: '+', '.join(f'`{x}`' for x in missing)+'.')
        if count<3: lines.append('Add replacements with `!add <pokemon_id> [pokemon_id ...]`.')
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
        # Dev-created/started bosses are guaranteed shiny, so winning grants the existing 10,000-coin jackpot.
        if dev_override and not boss:
            candidates=[x for x in POKEMON_LIST if x['name'] in LEGENDARY_NAMES]
            if not candidates:
                return await ctx.send('❌ Legendary list is not loaded yet. Try `!legendarybattle` again shortly.')
            d=await pokemon_data(random.choice(candidates)['name'])
            with db() as c:
                c.execute('INSERT OR REPLACE INTO boss_encounters(user_id,dex_id,name,level,shiny) VALUES(?,?,?,?,1)',(uid,d['id'],d['name'],0))
                c.execute('DELETE FROM boss_party WHERE user_id=?',(uid,))
            boss=(d['id'],d['name'],0,1)
            await ctx.send('🛠️ **Dev override enabled:** you can start this boss without completing 10 hunts. This boss is guaranteed shiny; defeating it awards the **10,000-coin jackpot**. Build your team with `!add <pokemon_id>` if needed.')
        elif dev_override and boss and not boss[3]:
            with db() as c:
                c.execute('UPDATE boss_encounters SET shiny=1 WHERE user_id=?',(uid,))
            boss=(boss[0],boss[1],boss[2],1)
            await ctx.send('🛠️ **Dev override enabled:** this boss is now guaranteed shiny. Defeating it awards the **10,000-coin jackpot**.')
        with db() as c:
            # Re-read in case the dev override created/updated the encounter above.
            boss=c.execute('SELECT dex_id,name,level,shiny FROM boss_encounters WHERE user_id=?',(uid,)).fetchone()
            party=c.execute('SELECT p.* FROM boss_party bp JOIN pokemon p ON p.instance_id=bp.instance_id WHERE bp.user_id=? ORDER BY bp.slot',(uid,)).fetchall()
        if not boss:return await ctx.send('❌ No active boss encounter. Every 10th hunt triggers one (devs can use `!legendarybattle` directly).')
        if len(party)!=3:return await ctx.send(f'🧩 Your boss team has **{len(party)}/3 Pokémon**. Add them with `!add <pokemon_id>`; use `!box` to see IDs.')
        if all(r[8]<=0 for r in party):return await ctx.send('💤 All three Pokémon have fainted. Use a potion with `!useitem Potion <pokemon_id>` or a status berry before starting the boss battle.')
        lead=next((r for r in party if r[8]>0),party[0])
        # Scale boss level to the strongest of all three selected Pokémon, not the active lead.
        boss_level=max(r[4] for r in party)+random.randint(10,15)
        with db() as c:c.execute('UPDATE boss_encounters SET level=? WHERE user_id=?',(boss_level,uid))
        d=await pokemon_data(boss[0]);d['_level']=boss_level
        self.active_boss_battles.add(uid)
        v=NPCBattleView(uid,lead,d,boss=True,boss_shiny=bool(boss[3]),active_boss_battles=self.active_boss_battles)
        try:
            await v.build()
        except Exception:
            self.active_boss_battles.discard(uid)
            raise
        e=discord.Embed(title='🔥 LEGENDARY BOSS — 3 VS 1',description=f'**Boss:** {display_name(d)} Lv. **{boss_level}**\nHP {hp_bar(max_hp(d,boss_level),max_hp(d,boss_level))}\nStatus: **Healthy**\n**Your squad:**\n'+'\n'.join(f'• **{r[3].title()}** Lv.{r[4]}\n  HP {hp_bar(r[8],r[9])}\n  Status: **{status_label(r[11] or "")}**' for r in party)+'\n\nChoose a move to attack. Use the **Switch** buttons to swap between your three Pokémon. Boss level is 10–15 levels above your highest-level teammate. Shiny status and odds were determined when this boss appeared.')
        e.color=discord.Color.dark_red()
        if sprite(d,shiny=bool(boss[3])):e.set_image(url=sprite(d,shiny=bool(boss[3])))
        v.message=await ctx.send(embed=e,view=v); ACTIVE_VIEWS[uid]=v

    @commands.hybrid_command(name='hint',aliases=['i','clue'],description='Get one of two hints for your current wild Pokémon.')
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

    @commands.hybrid_command(name='catch',aliases=['c','guess'],description='Guess and automatically catch a wild Pokémon.')
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
            cur=c.execute('INSERT INTO pokemon(user_id,dex_id,name,level,shiny,hp,max_hp) VALUES(?,?,?,?,?,?,?)',(uid,d['id'],d['name'],enc[3],enc[2],mh,mh)); iid=cur.lastrowid
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
        response=f'🎉 {ctx.author.mention} caught {"✨ SHINY " if enc[2] else ""}{display_name(d)}!{note} ID: `{iid}`\n💰 +50 coins! Check `!box`.'
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
        """Cancel this user's pending hunt, challenge, or active button battle."""
        uid=ctx.author.id; changes=[]
        with db() as c:
            if c.execute('DELETE FROM encounters WHERE user_id=?',(uid,)).rowcount: changes.append('wild hunt')
            if c.execute('DELETE FROM boss_encounters WHERE user_id=?',(uid,)).rowcount: changes.append('boss encounter')
            c.execute('DELETE FROM boss_party WHERE user_id=?',(uid,))
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

    @commands.hybrid_command(name='help',aliases=['commands','?'],description='Show commands, examples, and how to use items.')
    async def help_command(self,ctx,*,category:str=None):
        embed=discord.Embed(title='📘 Pokémon Bot — Help Guide', description='Use `!help <category>` for one topic, such as `!help box`. Run `!help` to see all categories.', color=discord.Color.blurple())
        groups = {
            '🌱 Adventure & Collection': [
                '`!start` / `!begin` — create/load your player profile', '`!hunt` / `!h` / `!search` — find a wild Pokémon; catch it before hunting again',
                '`!hint` / `!clue` — reveal missing letters in the Pokémon name (2 hints per hunt)', '`!catch` / `!c` / `!guess` <pokemon name> — catch by typing the exact Pokémon name',
                '`!box [category]` — browse/sort: `hp`, `status`, `legendary`, `shiny`, `mythical`, `ultrabeast`, `damaged`', '`!info` / `!stats` [pokemon_id] — live HP bar, battle stats, held item and status; defaults to your selected Pokémon', '`!pokedex` / `!dex` <name> or `!pokedex shiny <name>` — view species information',
            ],
            '🤝 Teams & Battles': [
                '`!select` / `!sel` <pokemon_id> — select your Pokémon', '`!team` / `!tm` — view your team', '`!setteam` / `!teamset` <pokemon_id> <slot 1-6> — set a team slot',
                '`!add <id> [id ...]` — add up to 3 Pokémon to your boss team (example: `!add 1 2 3`)', '`!remove <id> [id ...]` — remove Pokémon from your boss team (example: `!remove 1 2`)', '`!legendarybattle` — start/continue the boss battle',
                '`!battle` / `!fight` / `!b` — battle a trainer NPC', '`!challenge` / `!pvp` / `!duel` @user — challenge another trainer; moves are private', '`!cancel` — cancel your current hunt/battle/challenge', '`!fix` — dev-only recovery; reply to a stuck bot message'
            ],
            '💰 Coins & Shop': [
                '`!daily` / `!d` — daily reward and streak', '`!balance` / `!bal` / `!money` — see your coins and level', '`!leaderboard` / `!lb` — see top players',
                '`!shop` / `!market` / `!store` — browse the market in pages', '`!shop buy <item> <quantity>` — buy an item by full name, unique shortform, or product ID',
                'Examples: `!shop buy Oran Berry 5`, `!shop buy ora1 5`, or `!shop buy 1 5`'
            ],
            '🎒 Inventory & Items': [
                '`!inventory` / `!inv` / `!bag` — view inventory, 10 entries per page', '`!giveitem <name|shortform|id> <pokemon_id>` — equip a held item to one Pokémon',
                '`!useitem` / `!use` <name|shortform|id> <pokemon_id> — use a berry or potion; one item is removed each time',
                'Held items return to inventory when replaced. The same held-item type cannot be equipped on two Pokémon at once.'
            ],
            'ℹ️ Other': ['`!help` — show this guide']
        }
        if category:
            key=category.lower().strip().replace('&','').replace(' ','').replace('🤝','').replace('🌱','').replace('💰','').replace('🎒','').replace('ℹ️','')
            mapping={
                'box':'📦 Box & Collection','pokemon':'📦 Box & Collection','collection':'📦 Box & Collection',
                'hunt':'🌱 Adventure & Collection','adventure':'🌱 Adventure & Collection','catch':'🌱 Adventure & Collection',
                'battle':'🤝 Teams & Battles','battles':'🤝 Teams & Battles','team':'🤝 Teams & Battles','teams':'🤝 Teams & Battles','challenge':'🤝 Teams & Battles',
                'shop':'💰 Coins & Shop','coins':'💰 Coins & Shop','money':'💰 Coins & Shop',
                'inventory':'🎒 Inventory & Items','items':'🎒 Inventory & Items','useitem':'🎒 Inventory & Items',
                'other':'ℹ️ Other','help':'ℹ️ Other'
            }
            # Box has a focused subcategory guide, including all supported sorting filters.
            if key=='box':
                embed.title='📦 Help — Box & Pokémon Sorting'
                embed.description='Sort or filter your collection with these commands:'
                embed.add_field(name='Box commands',value='`!box` or `!box all` — all Pokémon\n`!box hp` — sort by highest maximum HP first\n`!box status` — Pokémon with a status condition\n`!box legendary` — legendary Pokémon\n`!box shiny` — shiny Pokémon\n`!box mythical` — mythical Pokémon\n`!box ultrabeast` — Ultra Beasts\n`!box damaged` — Pokémon whose current HP is below max HP\n`!info <pokemon_id>` — show HP bar, status and battle stats\n`!select <pokemon_id>` — select a Pokémon',inline=False)
            else:
                chosen=mapping.get(key)
                if not chosen:
                    embed.title='📘 Help — Categories'
                    embed.description='Unknown category. Available categories: `box`, `adventure`, `battle`, `shop`, `inventory`, `other`.\nExamples: `!help box`, `!help battle`, `!help shop`.'
                else:
                    embed.title=f'📘 Help — {chosen}'
                    embed.description='Commands and usage for this category:'
                    for heading,lines in groups.items():
                        if heading==chosen: embed.add_field(name=heading,value='\n'.join(lines),inline=False)
        else:
            # The main help page intentionally lists categories only.
            embed.title='📘 Pokémon Bot — Help Categories'
            embed.description=None
            embed.add_field(name='📚 Categories', value='`!help box`\n`!help adventure`\n`!help battle`\n`!help shop`\n`!help inventory`\n`!help other`', inline=False)
        if category:
            embed.set_footer(text='Use !help to return to the category list.')
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='pokedex',aliases=['dex','pd'],description='View normal or shiny Pokémon from any generation.')
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
    @commands.hybrid_command(name='box',aliases=['pokemon','pc','storage'],description='View or sort your Pokémon collection.')
    async def box(self,ctx,category:str='all'):
        category=category.lower().replace('-', '').replace('_','')
        aliases={'maxhp':'hp','highesthp':'hp','condition':'status','statuscondition':'status','legendaries':'legendary','shinies':'shiny','ultrabeasts':'ultrabeast','injured':'damaged','notfullhp':'damaged','belowmaxhp':'damaged'}
        category=aliases.get(category,category)
        allowed={'all','hp','status','legendary','shiny','mythical','ultrabeast','damaged'}
        if category not in allowed:
            return await ctx.send('❌ Unknown box category. Try: `!box all`, `!box hp`, `!box status`, `!box legendary`, `!box shiny`, `!box mythical`, `!box ultrabeast`, or `!box damaged`.')
        with db() as c:
            rows=c.execute('SELECT instance_id,dex_id,name,level,shiny,held_item,hp,max_hp,status_condition FROM pokemon WHERE user_id=?',(ctx.author.id,)).fetchall()
        if not rows:return await ctx.send('📦 Your box is empty. Use `!hunt` to find Pokémon!')
        ultra_ids=set(range(793,807))
        if category=='hp': rows=sorted(rows,key=lambda r:(r[7] or 0,r[6] or 0),reverse=True)
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
        entries=[(r[0],r[2],r[3],r[4],r[5],r[6],r[7],r[8]) for r in rows]
        view=BoxView(ctx.author.id,entries,category)
        view.message=await ctx.send(embed=view.make_embed(),view=view)

    @commands.hybrid_command(name='info',aliases=['pinfo','stats'],description="Show a Pokémon's current HP, stats and status conditions.")
    async def info(self,ctx,pokemon_id:Optional[int]=None):
        with db() as c:
            if pokemon_id is None:
                row=c.execute('SELECT p.instance_id,p.dex_id,p.name,p.level,p.shiny,p.hp,p.max_hp,p.held_item,p.status_condition FROM pokemon p JOIN team t ON t.instance_id=p.instance_id WHERE p.user_id=? ORDER BY CASE WHEN t.slot=1 THEN 0 ELSE 1 END,t.slot LIMIT 1',(ctx.author.id,)).fetchone()
            else:
                row=c.execute('SELECT instance_id,dex_id,name,level,shiny,hp,max_hp,held_item,status_condition FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,ctx.author.id)).fetchone()
        if not row:
            return await ctx.send('❌ No Pokémon selected/found. Use `!select <ID>` first, or `!info <ID>`.')
        iid,dex_id,name,level,shiny,hp,maxhp,held,status=row
        try:
            d=await pokemon_data(str(dex_id)); base=stats(d); types=type_text(d); abilities=', '.join(a['ability']['name'].replace('-',' ').title() for a in d.get('abilities',[])) or 'Unknown'
        except Exception:
            base={}; types='Unknown'; abilities='Unknown'; d=None
        hp=max(0,min(hp,maxhp)); maxhp=max(1,maxhp); ratio=hp/maxhp
        filled=max(0,min(10,round(ratio*10))); bar='▰'*filled+'▱'*(10-filled)
        e=discord.Embed(title=f'{"✨ Shiny " if shiny else ""}{name.replace("-"," ").title()} · Lv. {level}',description=f'**Pokémon ID:** `{iid}`\n**Type:** {types}\n**HP** `{hp}/{maxhp}`\n`{bar}` **{round(ratio*100)}%**',color=discord.Color.green() if ratio>.5 else discord.Color.orange() if hp>0 else discord.Color.dark_red())
        e.add_field(name='Battle Stats',value='\n'.join(f'**{label}:** {base.get(key,"?")}' for key,label in [('hp','HP Base'),('attack','Attack'),('defense','Defense'),('special-attack','Sp. Attack'),('special-defense','Sp. Defense'),('speed','Speed')]),inline=True)
        e.add_field(name='Condition',value=f'**Status:** {(status or "healthy").replace("-"," ").title()}\n**Held item:** {held.replace("-"," ").title() if held else "None"}\n**Ability:** {abilities}',inline=True)
        if d and sprite(d,shiny=bool(shiny)): e.set_thumbnail(url=sprite(d,shiny=bool(shiny)))
        e.set_footer(text='Live collection data • !info defaults to your selected Pokémon')
        await ctx.send(embed=e)

    @commands.command(name='pokemonadd',aliases=['pokeadd'])
    async def pokemonadd(self,ctx,member:discord.Member,*,pokemon_name:str):
        if not OWNER_ID or ctx.author.id != OWNER_ID:
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
                cur=c.execute('INSERT INTO pokemon(user_id,dex_id,name,level,shiny,hp,max_hp) VALUES(?,?,?,?,?,?,?)',(member.id,d['id'],d['name'],50,int(shiny),mh,mh)); iid=cur.lastrowid
                if not c.execute('SELECT 1 FROM team WHERE user_id=?',(member.id,)).fetchone(): c.execute('INSERT OR REPLACE INTO team(user_id,slot,instance_id) VALUES(?,?,?)',(member.id,1,iid))
            await interaction.response.edit_message(content=f'✅ Added **{label}** to {member.mention} (ID `{iid}`).',embed=None,view=None)
        async def yes_cb(interaction):
            if interaction.user.id != ctx.author.id: return await interaction.response.send_message('Only the command user can confirm this.',ephemeral=True)
            with db() as c:
                cur=c.execute('INSERT INTO pokemon(user_id,dex_id,name,level,shiny,hp,max_hp) VALUES(?,?,?,?,?,?,?)',(member.id,d['id'],d['name'],50,int(shiny),mh,mh)); iid=cur.lastrowid
                if not c.execute('SELECT 1 FROM team WHERE user_id=?',(member.id,)).fetchone(): c.execute('INSERT OR REPLACE INTO team(user_id,slot,instance_id) VALUES(?,?,?)',(member.id,1,iid))
            await interaction.response.edit_message(content=f'✅ Added **{label}** to {member.mention} (ID `{iid}`).',embed=None,view=None)
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
        if not OWNER_ID or ctx.author.id != OWNER_ID:
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
        embed=discord.Embed(title='✨ A SERVER-WIDE SHINY Pokémon appeared!', description=f'**A wild shiny appeared!**\n**Level:** {lvl}\n**Type:** ???\n\nLook at the artwork and guess its name with `!catch <pokemon name>`.\n💰 First correct guess wins and gets **50 coins**. Only one user can catch it!')
        art=sprite(d,shiny=True)
        if art: embed.set_image(url=art)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='setteam',aliases=['teamset','slotteam'],description='Set a Pokémon into team slot 1-6.')
    async def setteam(self,ctx,pokemon_id:int,slot:int):
        if slot not in range(1,7):return await ctx.send('❌ Slot must be 1-6.')
        with db() as c:r=c.execute('SELECT 1 FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,ctx.author.id)).fetchone()
        if not r:return await ctx.send('❌ That Pokémon ID is not yours.')
        with db() as c:c.execute('INSERT OR REPLACE INTO team VALUES(?,?,?)',(ctx.author.id,slot,pokemon_id))
        await ctx.send(f'✅ Team slot {slot} updated.')
    @commands.hybrid_command(name='select',aliases=['choose','sel'],description='Select one of your Pokémon as your active battle Pokémon.')
    async def select(self,ctx,pokemon_id:Optional[int]=None):
        if pokemon_id is None:return await ctx.send('Usage: `!select <id>` — use `!box` to see your Pokémon IDs.')
        with db() as c: row=c.execute('SELECT instance_id,name,level,hp,max_hp FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,ctx.author.id)).fetchone()
        if not row:return await ctx.send('❌ That Pokémon ID is not in your collection. Check `!box`.')
        with db() as c:c.execute('INSERT OR REPLACE INTO team(user_id,slot,instance_id) VALUES(?,?,?)',(ctx.author.id,1,pokemon_id))
        await ctx.send(f'✅ Selected **{row[1].title()}** Lv. {row[2]} (ID `{pokemon_id}`) as your active battle Pokémon.')

    @commands.hybrid_command(name='team',aliases=['myteam','tm'],description='Show your team.')
    async def team(self,ctx):
        with db() as c:r=c.execute('SELECT t.slot,p.instance_id,p.name,p.level,p.shiny,p.hp,p.max_hp FROM team t JOIN pokemon p ON p.instance_id=t.instance_id WHERE t.user_id=? ORDER BY t.slot',(ctx.author.id,)).fetchall()
        await ctx.send('🎒 **Team**\n'+'\n'.join(f'**{x[0]}.** `{x[1]}` {"✨ " if x[4] else ""}**{x[2].title()}** Lv.{x[3]} · `{x[5]}/{x[6]}` `{'▰'*max(0,min(10,round(x[5]/max(1,x[6])*10)))+'▱'*(10-max(0,min(10,round(x[5]/max(1,x[6])*10))))}`' for x in r) if r else 'Your team is empty.')
    @commands.hybrid_command(name='battle',aliases=['fight','b'],description='Battle an NPC with move buttons.')
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
        if sprite(own_data):e.set_thumbnail(url=sprite(own_data))
        if sprite(enemy):e.set_image(url=sprite(enemy))
        v.message=await ctx.send(embed=e,view=v); ACTIVE_VIEWS[ctx.author.id]=v
    @commands.hybrid_command(name='challenge',aliases=['pvp','duel','chall'],description='Challenge another trainer to a PvP battle.')
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
            # Stop the 30-second invitation timer permanently once accepted; the battle itself has no timeout.
            view.stop()
            self.challenges.pop(ctx.author.id,None);self.challenges.pop(opponent.id,None);p=PvPBattle(ctx.author.id,opponent.id,ra,rb);await p.setup();pv=p.view();await i.response.edit_message(content=None,embed=await p.make_embed(),view=pv);p.message=i.message;pv.message=i.message;ACTIVE_VIEWS[ctx.author.id]=p;ACTIVE_VIEWS[opponent.id]=p;
        async def dec(i):
            if i.user.id!=opponent.id:return await i.response.send_message('Only the challenged player can decline.',ephemeral=True)
            view.stop()
            self.challenges.pop(ctx.author.id,None);self.challenges.pop(opponent.id,None);ACTIVE_VIEWS.pop(ctx.author.id,None);ACTIVE_VIEWS.pop(opponent.id,None);await i.response.edit_message(content='❌ Challenge declined.',view=None)
        accept.callback=acc;decline.callback=dec
        view.message=await ctx.send(f'⚔️ <@{ctx.author.id}> challenged <@{opponent.id}> to a Pokémon battle!\n⏳ They have 30 seconds to accept or decline. After acceptance, the battle stays active until it ends or is cancelled.',view=view); ACTIVE_VIEWS[ctx.author.id]=view; ACTIVE_VIEWS[opponent.id]=view
    @commands.hybrid_command(name='shop',aliases=['market','store'],description='Browse the market or buy items by name, shortform, or ID.')
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
                        return await ctx.send(f'❌ **{label} ×{quantity}** costs {total:,} coins, but you have {balance_before:,}.')
                    c.execute('UPDATE players SET coins=coins-? WHERE user_id=?',(total,ctx.author.id))
                    c.execute('INSERT INTO inventory(user_id,item,amount) VALUES(?,?,?) ON CONFLICT(user_id,item) DO UPDATE SET amount=amount+excluded.amount',(ctx.author.id,key,quantity))
                    balance=balance_before-total
                    c.commit()
            except Exception as exc:
                print(f'Shop purchase failed for user {ctx.author.id}, product {product_id}: {exc!r}')
                return await ctx.send('❌ Purchase failed. Please try again; if it repeats, send the Termux error.')
            consumable = ('berry' in key) or key in {'potion','super-potion','hyper-potion','max-potion','full-restore'}
            howto = f'Use `!useitem {shortform} <pokemon_id>`' if consumable else f'Equip with `!giveitem {shortform} <pokemon_id>`'
            return await ctx.send(f'🛒 **Purchase successful!**\nBought **{label} ×{quantity}** for **{total:,} coins**.\n🎒 Added to your inventory. Shortform: `{shortform}`.\n💰 Remaining balance: **{balance:,} coins**.\n{howto}.')
        view=ShopView(ctx.author.id)
        view.message=await ctx.send(embed=view.make_embed(),view=view)

    @commands.command(name='giveitem',aliases=['equip','holditem'])
    async def giveitem(self,ctx,product:str,pokemon_id:int):
        product_id=resolve_shop_product(product)
        if product_id is None:return await ctx.send('❌ Unknown item. Use `!shop` to see names and shortforms.')
        key,label,cost,desc,shortform=SHOP_ITEMS[product_id]
        with db() as c: row=c.execute('SELECT instance_id,name,held_item FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,ctx.author.id)).fetchone()
        if not row:return await ctx.send('❌ That Pokémon ID is not yours.')
        if 'berry' in key or key in {'potion','super-potion','hyper-potion','max-potion','full-restore'}:return await ctx.send('🧪 This is a consumable; use `!useitem <item> <pokemon_id>`.')
        if inventory_amount(ctx.author.id,key)<=0:return await ctx.send(f'❌ You do not own {label}. Buy it with `!shop buy {product_id}`.')
        with db() as c:
            already=c.execute('SELECT instance_id,name FROM pokemon WHERE user_id=? AND held_item=? AND instance_id<>? LIMIT 1',(ctx.author.id,key,pokemon_id)).fetchone()
        if already:
            return await ctx.send(f'❌ **{label}** is already equipped to **{already[1].title()}** (ID `{already[0]}`). Unequip it from that Pokémon first before equipping it to another.')
        if row[2]:change_item(ctx.author.id,row[2],1)
        change_item(ctx.author.id,key,-1)
        with db() as c:c.execute('UPDATE pokemon SET held_item=? WHERE instance_id=? AND user_id=?',(key,pokemon_id,ctx.author.id))
        await ctx.send(f'🎒 **{label}** is now held by **{row[1].title()}** (ID `{pokemon_id}`).'+(f' Returned previous held item `{row[2]}` to inventory.' if row[2] else ''))

    @commands.command(name='useitem',aliases=['use','itemuse'])
    async def useitem(self,ctx,*,args:str):
        parts=args.rsplit(maxsplit=1)
        if len(parts)!=2 or not parts[1].isdigit():
            return await ctx.send('Usage: `!useitem <berry/potion name|shortform|id> <pokemon_id>` — example: `!useitem Potion 12`')
        product,pokemon_text=parts; pokemon_id=int(pokemon_text)
        product_id=resolve_shop_product(product)
        if product_id is None:return await ctx.send('❌ Unknown item. Use `!shop` or `!inventory` to see item names, shortforms, and IDs.')
        key,label,cost,desc,shortform=SHOP_ITEMS[product_id]
        consumable_keys={k for k,*_ in SHOP_ITEMS.values() if 'berry' in k}
        consumable_keys.update({'potion','super-potion','hyper-potion','max-potion','full-restore'})
        if key not in consumable_keys:return await ctx.send('❌ This is a held item. Equip it with `!giveitem <item_id> <pokemon_id>`.')
        with db() as c:
            row=c.execute('SELECT instance_id,name,hp,max_hp,status_condition FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,ctx.author.id)).fetchone()
            stock=c.execute('SELECT amount FROM inventory WHERE user_id=? AND item=?',(ctx.author.id,key)).fetchone()
        if not row:return await ctx.send('❌ That Pokémon ID is not yours. Use `!box` to check its ID.')
        if not stock or stock[0]<=0:return await ctx.send(f'❌ You do not own **{label}**. Buy it with `!shop buy {shortform} 1`.')
        hp,maxhp,status=row[2],row[3],row[4] or ''
        old_hp,old_status=hp,status
        cure_map={'pecha-berry':'poison','cheri-berry':'paralysis','rawst-berry':'burn','aspear-berry':'freeze','chesto-berry':'sleep'}
        if key in cure_map:
            target=cure_map[key]
            if status not in ((target,'badly-poisoned') if target=='poison' else (target,)):
                return await ctx.send(f'ℹ️ **{row[1].title()}** is not affected by {target.replace("-"," ")}. **{label}** was not consumed.')
            status='';msg=f'cured {target.replace("-"," ")}'
        elif key=='lum-berry':
            if not status:return await ctx.send(f'ℹ️ **{row[1].title()}** has no status condition. **{label}** was not consumed.')
            msg=f'cured {status_label(status).lower()}';status=''
        elif key=='oran-berry':
            if hp>=maxhp:return await ctx.send(f'ℹ️ **{row[1].title()}** already has full HP. **{label}** was not consumed.')
            hp=min(maxhp,hp+10);msg=f'restored {hp-old_hp} HP'
        elif key in ('sitrus-berry','figy-berry','wiki-berry','mago-berry','aguav-berry','iapapa-berry'):
            if hp>=maxhp:return await ctx.send(f'ℹ️ **{row[1].title()}** already has full HP. **{label}** was not consumed.')
            hp=min(maxhp,hp+max(1,maxhp//4));msg=f'restored {hp-old_hp} HP'
        elif key=='leppa-berry':
            if hp>=maxhp:return await ctx.send(f'ℹ️ **{row[1].title()}** already has full HP. **{label}** was not consumed.')
            hp=min(maxhp,hp+5);msg=f'restored {hp-old_hp} HP'
        elif key=='potion':
            if hp>=maxhp:return await ctx.send(f'ℹ️ **{row[1].title()}** already has full HP. **{label}** was not consumed.')
            hp=min(maxhp,hp+20);msg=f'restored {hp-old_hp} HP'
        elif key=='super-potion':
            if hp>=maxhp:return await ctx.send(f'ℹ️ **{row[1].title()}** already has full HP. **{label}** was not consumed.')
            hp=min(maxhp,hp+50);msg=f'restored {hp-old_hp} HP'
        elif key=='hyper-potion':
            if hp>=maxhp:return await ctx.send(f'ℹ️ **{row[1].title()}** already has full HP. **{label}** was not consumed.')
            hp=min(maxhp,hp+120);msg=f'restored {hp-old_hp} HP'
        elif key=='max-potion':
            if hp>=maxhp:return await ctx.send(f'ℹ️ **{row[1].title()}** already has full HP. **{label}** was not consumed.')
            hp=maxhp;msg='restored all HP'
        elif key=='full-restore':
            if hp>=maxhp and not status:return await ctx.send(f'ℹ️ **{row[1].title()}** already has full HP and no status condition. **{label}** was not consumed.')
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
        await ctx.send(f'🧪 Used **{label}** on **{row[1].title()}** (ID `{pokemon_id}`): {msg}. HP: {hp_bar(hp,maxhp)} • Status: **{status_label(status)}**.')

    @commands.hybrid_command(name='inventory',aliases=['inv','bag'],description='View your inventory in pages of ten entries.')
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
            entries.append((f'🔒 {label} — Equipped',f'Equipped to **{name.title()}** (Pokémon ID `{iid}`). This item is not available to equip to another Pokémon while held.'))
        entries.sort(key=lambda x:x[0].casefold())
        view=InventoryView(ctx.author.id,entries)
        view.message=await ctx.send(embed=view.make_embed(),view=view)
    @commands.hybrid_command(name='daily',aliases=['d','claim'],description='Claim your daily coins and Pokémon reward.')
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
            cur=c.execute('INSERT INTO pokemon(user_id,dex_id,name,level,shiny,hp,max_hp) VALUES(?,?,?,?,?,?,?)',(uid,pick['id'],pick['name'],lvl,0,mh,mh));iid=cur.lastrowid
            if not c.execute('SELECT 1 FROM team WHERE user_id=?',(uid,)).fetchone():c.execute('INSERT INTO team VALUES(?,?,?)',(uid,1,iid))
        if legendary:
            await ctx.send(f'🔥 **{streak}-day streak!** Guaranteed legendary reward: **{display_name(pick)}** Lv.{lvl} — ID `{iid}`\n💰 +2,000 coins')
        else:
            await ctx.send(f'🎁 Daily reward: **2,000 coins** + **{display_name(pick)}** Lv.{lvl} — ID `{iid}`\n🔥 Current streak: **{streak}** days')
    @commands.hybrid_command(name='balance',aliases=['bal','money'],description='View your coins, level and XP.')
    async def balance(self,ctx):
        coins,xp,level,_,_=get_player(ctx.author.id)
        e=discord.Embed(title=f"💰 {ctx.author.display_name}'s Trainer Balance",color=discord.Color.gold())
        e.add_field(name='PokéCoins',value=f'**{coins:,}**',inline=True)
        e.add_field(name='Trainer Level',value=f'**{level}**',inline=True)
        e.add_field(name='XP Progress',value=f'**{xp:,} / {level*100:,}**',inline=True)
        e.set_footer(text='Earn coins from catching Pokémon, battles and daily rewards.')
        await ctx.send(embed=e)

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
                await interaction.response.edit_message(content=f'✅ {result}',embed=None,view=None)
            except Exception as exc:
                await interaction.response.edit_message(content=f'❌ Action failed: `{exc}`',embed=None,view=None)
        async def no_cb(interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message('Only the dev who started this action can cancel it.',ephemeral=True)
            await interaction.response.edit_message(content='❎ Action cancelled.',embed=None,view=None)
        yes.callback=yes_cb; no.callback=no_cb; view.add_item(yes); view.add_item(no)
        view.message=await ctx.send(embed=discord.Embed(title=title,description=description,color=discord.Color.orange()),view=view)

    def is_dev(self, ctx):
        return bool(OWNER_ID and ctx.author.id == OWNER_ID)

    @commands.command(name='coinsadd',aliases=['addcoins'])
    async def coinsadd(self,ctx,member:discord.Member,amount:int):
        if not self.is_dev(ctx): return
        if amount <= 0 or amount > 1_000_000_000: return await ctx.send('❌ Amount must be between 1 and 1,000,000,000 coins.')
        def action():
            add_progress(member.id,coins=amount)
            return f'Added **{amount:,} coins** to {member.mention}. New balance: **{get_player(member.id)[0]:,} coins**.'
        await self.dev_confirmation(ctx,'Confirm coin addition',f'Add **{amount:,} coins** to {member.mention}?',action)

    @commands.command(name='removecoins',aliases=['takecoins'])
    async def removecoins(self,ctx,member:discord.Member,amount:int):
        if not self.is_dev(ctx): return
        if amount <= 0 or amount > 1_000_000_000: return await ctx.send('❌ Amount must be between 1 and 1,000,000,000 coins.')
        def action():
            old=get_player(member.id)[0]; new=max(0,old-amount)
            with db() as c: c.execute('UPDATE players SET coins=? WHERE user_id=?',(new,member.id))
            return f'Removed **{old-new:,} coins** from {member.mention}. New balance: **{new:,} coins**.'
        await self.dev_confirmation(ctx,'Confirm coin removal',f'Remove up to **{amount:,} coins** from {member.mention}?',action)

    @commands.command(name='removepokemon',aliases=['removepoke'])
    async def removepokemon(self,ctx,member:discord.Member,pokemon_id:int):
        if not self.is_dev(ctx): return
        with db() as c: row=c.execute('SELECT instance_id,name,shiny,level FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,member.id)).fetchone()
        if not row: return await ctx.send('❌ That Pokémon ID does not belong to that user.')
        def action():
            with db() as c:
                c.execute('DELETE FROM team WHERE instance_id=?',(pokemon_id,))
                c.execute('DELETE FROM pokemon WHERE instance_id=? AND user_id=?',(pokemon_id,member.id))
            return f'Removed {"✨ Shiny " if row[2] else ""}**{row[1].title()}** Lv. {row[3]} (ID `{pokemon_id}`) from {member.mention}.'
        await self.dev_confirmation(ctx,'Confirm Pokémon removal',f'Remove **{row[1].title()}** (ID `{pokemon_id}`) from {member.mention}?',action)

    @commands.hybrid_command(name='leaderboard',aliases=['lb','top'],description='Show richest trainers.')
    async def leaderboard(self,ctx):
        with db() as c:r=c.execute('SELECT user_id,coins,level FROM players ORDER BY coins DESC LIMIT 10').fetchall()
        lines=[]
        for i,(uid,c,l) in enumerate(r,1):
            u=self.bot.get_user(uid);lines.append(f'**{i}.** {u.display_name if u else uid} — 💰 {c:,} — Lv.{l}')
        await ctx.send('🏆 **Leaderboard**\n'+'\n'.join(lines))

class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=PREFIX, intents=intents, help_command=None)
    async def setup_hook(self):
        await self.add_cog(Game(self));await load_pokemon_list();await self.tree.sync()
    async def on_ready(self):print(f'Logged in as {self.user}');print(f'Loaded {len(POKEMON_LIST)} Pokémon species.')
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(f'⏳ Try again in {error.retry_after:.1f} seconds.')
        original = getattr(error, 'original', error)
        if isinstance(original, commands.MissingRequiredArgument):
            name = ctx.command.qualified_name if ctx.command else 'command'
            usage = {
                'catch':'!catch <pokemon name>', 'pokedex':'!pokedex <pokemon name>',
                'select':'!select <id>', 'setteam':'!setteam <pokemon_id> <slot 1-6>',
                'challenge':'!challenge @user',
                'add':'!add <pokemon_id>', 'giveitem':'!giveitem <item_name|shortform|id> <pokemon_id>',
                'useitem':'!useitem <berry name|shortform|id> <pokemon_id>', 'coinsadd':'!coinsadd @user <amount>',
                'removecoins':'!removecoins @user <amount>', 'removepokemon':'!removepokemon @user <pokemon_id>',
                'pokemonadd':'!pokemonadd @user <pokemon>', 'shop':'!shop or !shop buy <item> <quantity>',
            }.get(name, f'!{name}')
            return await ctx.send(f'Usage: `{usage}`')
        if isinstance(original, commands.BadArgument):
            name = ctx.command.qualified_name if ctx.command else 'command'
            usage = {'select':'!select <id>', 'setteam':'!setteam <pokemon_id> <slot 1-6>', 'add':'!add <pokemon_id>', 'giveitem':'!giveitem <item_name|shortform|id> <pokemon_id>', 'useitem':'!useitem <berry name|shortform|id> <pokemon_id>'}.get(name, f'!{name} <valid argument>')
            return await ctx.send(f'Usage: `{usage}` — please check the argument types.')
        print(f'Command error in {getattr(ctx.command, "qualified_name", "unknown")}: {error!r}')
        await ctx.send('❌ That command hit an error. Check the Termux output and send me the error message.')

async def main():
    global SESSION
    setup()
    if not TOKEN:raise RuntimeError('Set DISCORD_TOKEN first.')
    bot=Bot()
    try:await bot.start(TOKEN)
    finally:
        if SESSION:await SESSION.close()
if __name__=='__main__':asyncio.run(main())
