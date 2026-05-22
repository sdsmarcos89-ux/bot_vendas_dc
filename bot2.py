import discord
from discord.ui import Button, View, Modal, TextInput, Select
import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
import asyncio
import time
from datetime import datetime
import uuid

# --- HEALTH CHECK PARA O RENDER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-type", "text/html"); self.end_headers()
        self.wfile.write(b"Bot V6 Online")
    def log_message(self, format, *args): return

def run_health_check():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), HealthCheckHandler).serve_forever()

threading.Thread(target=run_health_check, daemon=True).start()

# --- CONFIGURAÇÕES E DADOS ---
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
PIX_KEY = os.getenv("PIX_KEY") or "c84eccdd-893e-4d2b-9392-7a2460b0254d"
ADMIN_ID = int(os.getenv("ADMIN_CHANNEL_ID") or 0)
OWNER_ID = int(os.getenv("OWNER_ID") or 0)

FILES = {"p": "products.json", "w": "wallets.json", "d": "deposits.json"}

def load_f(k):
    if os.path.exists(FILES[k]) and os.path.getsize(FILES[k]) > 0:
        with open(FILES[k], "r", encoding="utf-8") as f: return json.load(f)
    return {}

def save_f(k, d):
    with open(FILES[k], "w", encoding="utf-8") as f: json.dump(d, f, indent=4, ensure_ascii=False)

PRODUCTS = load_f("p"); WALLETS = load_f("w"); DEPOSITS = load_f("d")

bot = discord.Bot(intents=discord.Intents.all())

# --- LÓGICA DE NEGÓCIO ---
def get_w(uid):
    uid = str(uid)
    if uid not in WALLETS: WALLETS[uid] = {"b": 0.0}; save_f("w", WALLETS)
    return WALLETS[uid]

def upd_b(uid, amt):
    uid = str(uid); w = get_w(uid); w["b"] += amt; save_f("w", WALLETS)
    return w["b"]

def get_s(pid, plid):
    path = f"stock_{pid}_{plid}.txt"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f: return [l.strip() for l in f if l.strip()]
    return []

def save_s(pid, plid, s):
    with open(f"stock_{pid}_{plid}.txt", "w", encoding="utf-8") as f:
        for x in s: f.write(f"{x}\n")

# --- MODALS ---
class DepModal(Modal):
    def __init__(self): super().__init__(title="💰 Adicionar Saldo")
    self.add_item(TextInput(label="Valor (R$)", placeholder="10.00"))
    async def callback(self, i: discord.Interaction):
        try: val = float(self.children[0].value.replace(",", "."))
        except: return await i.response.send_message("❌ Valor inválido!", ephemeral=True)
        txid = str(uuid.uuid4())[:8]; DEPOSITS[txid] = {"u": i.user.id, "v": val}; save_f("d", DEPOSITS)
        pix = f"00020126330014br.gov.bcb.pix0111{PIX_KEY}52040000530398654{len(f'{val:.2f}'):02d}{val:.2f}5802BR5913BOT6008BRASILIA62070503{txid[:3]}6304"
        emb = discord.Embed(title="💳 Depósito", description=f"Valor: **R$ {val:.2f}**\n\n**Copia e Cola:**\n```\n{pix}\n```", color=0x3498db)
        admin = bot.get_channel(ADMIN_ID)
        if admin:
            v = View(timeout=None)
            v.add_item(Button(label="Aprovar", style=discord.ButtonStyle.success, custom_id=f"adm_dep_app_{txid}"))
            v.add_item(Button(label="Recusar", style=discord.ButtonStyle.danger, custom_id=f"adm_dep_rej_{txid}"))
            await admin.send(f"📥 **Novo Depósito**: R$ {val:.2f} por <@{i.user.id}>", view=v)
        await i.response.send_message(embed=emb, ephemeral=True)

class ProdModal(Modal):
    def __init__(self, pid=None):
        super().__init__(title="💎 Produto"); self.pid = pid
        self.add_item(TextInput(label="Nome", default_value=PRODUCTS[pid]["name"] if pid else ""))
        self.add_item(TextInput(label="Descrição", style=discord.InputTextStyle.long, default_value=PRODUCTS[pid]["description"] if pid else ""))
    async def callback(self, i: discord.Interaction):
        pid = self.pid or str(uuid.uuid4())[:8]
        PRODUCTS[pid] = {"name": self.children[0].value, "description": self.children[1].value, "plans": PRODUCTS[pid]["plans"] if self.pid else {}}
        save_f("p", PRODUCTS); await i.response.send_message("✅ Salvo!", ephemeral=True)

class PlanMod(Modal):
    def __init__(self, pid): super().__init__(title="➕ Novo Plano"); self.pid = pid
    self.add_item(TextInput(label="Nome")); self.add_item(TextInput(label="Preço"))
    async def callback(self, i: discord.Interaction):
        plid = str(uuid.uuid4())[:8]
        PRODUCTS[self.pid]["plans"][plid] = {"name": self.children[0].value, "price": float(self.children[1].value)}
        save_f("p", PRODUCTS); await i.response.send_message("✅ Plano Adicionado!", ephemeral=True)

class StockMod(Modal):
    def __init__(self, pid, plid): super().__init__(title="📦 Abastecer"); self.pid, self.plid = pid, plid
    self.add_item(TextInput(label="Itens", style=discord.InputTextStyle.long))
    async def callback(self, i: discord.Interaction):
        new = [l.strip() for l in self.children[0].value.split("\n") if l.strip()]
        save_s(self.pid, self.plid, get_s(self.pid, self.plid) + new)
        await i.response.send_message(f"✅ {len(new)} itens adicionados!", ephemeral=True)

# --- VIEWS ---
class BuyOptions(View):
    def __init__(self, pid, plid): super().__init__(timeout=None); self.pid, self.plid = pid, plid
    @discord.ui.button(label="✅ Já Paguei (Manual)", style=discord.ButtonStyle.success)
    async def manual(self, b, i):
        admin = bot.get_channel(ADMIN_ID)
        if admin:
            v = View(timeout=None)
            v.add_item(Button(label="Aprovar Venda", style=discord.ButtonStyle.success, custom_id=f"adm_sale_app_{self.pid}_{self.plid}_{i.user.id}"))
            v.add_item(Button(label="Recusar Venda", style=discord.ButtonStyle.danger, custom_id=f"adm_sale_rej_{i.user.id}"))
            await admin.send(f"🛒 **Venda Manual**: {PRODUCTS[self.pid]['name']} por <@{i.user.id}>", view=v)
        await i.response.send_message("✅ Notificado! Aguarde.", ephemeral=True)
    @discord.ui.button(label="💰 Comprar com Saldo", style=discord.ButtonStyle.primary)
    async def wallet(self, b, i):
        w = get_w(i.user.id); pl = PRODUCTS[self.pid]["plans"][self.plid]
        if w["b"] < pl["price"]: return await i.response.send_message("❌ Saldo insuficiente!", ephemeral=True)
        s = get_s(self.pid, self.plid)
        if not s: return await i.response.send_message("❌ Sem estoque!", ephemeral=True)
        item = s.pop(0); save_s(self.pid, self.plid, s); upd_b(i.user.id, -pl["price"])
        try: await i.user.send(f"🎉 Compra: `{item}`"); await i.response.send_message("✅ DM!", ephemeral=True)
        except: await i.response.send_message(f"⚠️ DM fechada! Item: `{item}`", ephemeral=True)

class PlanSelect(View):
    def __init__(self, pid):
        super().__init__(timeout=None); self.pid = pid
        opts = [discord.SelectOption(label=f"{p['name']} - R$ {p['price']:.2f}", value=plid) for plid, p in PRODUCTS[pid]["plans"].items()]
        if opts:
            sel = Select(placeholder="Escolha o plano...", options=opts)
            sel.callback = self.cb; self.add_item(sel)
    async def cb(self, i):
        plid = i.data["values"][0]; pl = PRODUCTS[self.pid]["plans"][plid]
        pix = f"00020126330014br.gov.bcb.pix0111{PIX_KEY}52040000530398654{len(f'{pl['price']:.2f}'):02d}{pl['price']:.2f}5802BR5913BOT6008BRASILIA62070503***6304"
        emb = discord.Embed(title="🛒 Pagamento", description=f"Preço: **R$ {pl['price']:.2f}**\n\n**PIX:**\n```\n{pix}\n```", color=0xf1c40f)
        await i.response.send_message(embed=emb, view=BuyOptions(self.pid, plid), ephemeral=True)

# --- COMANDOS ---
@bot.slash_command(name="perfil")
async def perfil(ctx):
    w = get_w(ctx.author.id); v = View()
    v.add_item(Button(label="💰 Depositar", style=discord.ButtonStyle.success, custom_id="btn_deposit"))
    await ctx.respond(f"👤 **Perfil**: <@{ctx.author.id}>\n💵 **Saldo**: `R$ {w['b']:.2f}`", view=v)

@bot.slash_command(name="loja")
async def loja(ctx):
    if not PRODUCTS: return await ctx.respond("Loja vazia!", ephemeral=True)
    v = View(); opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
    sel = Select(placeholder="Escolha...", options=opts)
    async def cb(i): await i.response.send_message(embed=discord.Embed(title=PRODUCTS[sel.values[0]]["name"], description=PRODUCTS[sel.values[0]]["description"]), view=PlanSelect(sel.values[0]), ephemeral=True)
    sel.callback = cb; v.add_item(sel); await ctx.respond("🛍️ **Loja**", view=v)

@bot.slash_command(name="painel")
async def painel(ctx):
    if ctx.author.id != OWNER_ID: return await ctx.respond("Negado!", ephemeral=True)
    v = View()
    v.add_item(Button(label="➕ Produto", style=discord.ButtonStyle.success, custom_id="adm_p"))
    v.add_item(Button(label="➕ Plano", style=discord.ButtonStyle.primary, custom_id="adm_pl"))
    v.add_item(Button(label="📦 Estoque", style=discord.ButtonStyle.secondary, custom_id="adm_s"))
    await ctx.respond("🛠️ **Admin**", view=v, ephemeral=True)

# --- EVENTO GLOBAL (APENAS COMPONENTES PERSISTENTES) ---
@bot.event
async def on_interaction(i: discord.Interaction):
    if i.type == discord.InteractionType.application_command:
        await bot.process_application_commands(i)
        return
    
    if i.type == discord.InteractionType.component:
        cid = i.data.get("custom_id", "")
        if cid == "btn_deposit": await i.response.send_modal(DepModal())
        elif cid == "adm_p": await i.response.send_modal(ProdModal())
        elif cid == "adm_pl":
            v = View(); opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
            if not opts: return await i.response.send_message("Crie um produto!", ephemeral=True)
            s = Select(options=opts); s.callback = lambda i2: i2.response.send_modal(PlanMod(s.values[0]))
            v.add_item(s); await i.response.send_message("Produto:", view=v, ephemeral=True)
        elif cid == "adm_s":
            v = View(); opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
            if not opts: return await i.response.send_message("Crie um produto!", ephemeral=True)
            s = Select(options=opts)
            async def cb(i2):
                pid = s.values[0]; v2 = View(); opts2 = [discord.SelectOption(label=pl["name"], value=plid) for plid, pl in PRODUCTS[pid]["plans"].items()]
                if not opts2: return await i2.response.send_message("Crie um plano!", ephemeral=True)
                s2 = Select(options=opts2); s2.callback = lambda i3: i3.response.send_modal(StockMod(pid, s2.values[0]))
                v2.add_item(s2); await i2.response.send_message("Plano:", view=v2, ephemeral=True)
            s.callback = cb; v.add_item(s); await i.response.send_message("Produto:", view=v, ephemeral=True)
        
        # Aprovações (Persistentes)
        elif cid.startswith("adm_dep_app_"):
            txid = cid[12:]; d = DEPOSITS.pop(txid, None); save_f("d", DEPOSITS)
            if d: upd_b(d["u"], d["v"]); await i.response.send_message("✅ Aprovado!", ephemeral=True); await i.message.edit(view=None)
        elif cid.startswith("adm_sale_app_"):
            _, _, _, pid, plid, uid = cid.split("_"); s = get_s(pid, plid)
            if s:
                item = s.pop(0); save_s(pid, plid, s)
                try: u = await bot.fetch_user(int(uid)); await u.send(f"✅ Aprovado! Item: `{item}`")
                except: pass
                await i.response.send_message("✅ Entregue!", ephemeral=True); await i.message.edit(view=None)
            else: await i.response.send_message("❌ Sem estoque!", ephemeral=True)

@bot.event
async def on_ready(): print(f"Bot V6 Final Online: {bot.user}")

if TOKEN: bot.run(TOKEN)

