import discord
from discord.ui import Button, View, Modal, TextInput, Select
import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
import asyncio
import urllib.parse
import time
from datetime import datetime
import uuid

# --- CÓDIGO PARA MANTER ONLINE NO RENDER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot Online")
    def log_message(self, format, *args): return

def run_health_check():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_health_check, daemon=True).start()
# -------------------------------------------

load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
PIX_KEY = os.getenv("PIX_KEY") or "c84eccdd-893e-4d2b-9392-7a2460b0254d"
ADMIN_CHANNEL_ID = int(os.getenv("ADMIN_CHANNEL_ID") or 0)
OWNER_ID = int(os.getenv("OWNER_ID") or 0)

PRODUCTS_FILE = "products.json"
WALLETS_FILE = "wallets.json"
PENDING_DEPOSITS_FILE = "pending_deposits.json"

def load_json(filename):
    if os.path.exists(filename) and os.path.getsize(filename) > 0:
        with open(filename, "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return {}
    return {}

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

PRODUCTS = load_json(PRODUCTS_FILE)
WALLETS = load_json(WALLETS_FILE)
DEPOSITOS_PENDENTES = load_json(PENDING_DEPOSITS_FILE)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = discord.Bot(intents=intents)

# --- Funções de Apoio ---
def get_wallet(user_id):
    user_id = str(user_id)
    if user_id not in WALLETS:
        WALLETS[user_id] = {"balance": 0.0}
        save_json(WALLETS_FILE, WALLETS)
    return WALLETS[user_id]

def update_balance(user_id, amount):
    user_id = str(user_id)
    wallet = get_wallet(user_id)
    wallet["balance"] += amount
    save_json(WALLETS_FILE, WALLETS)
    return wallet["balance"]

def load_stock(pid, plid):
    path = f"stock_{pid}_{plid}.txt"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f: return [l.strip() for l in f if l.strip()]
    return []

def save_stock(pid, plid, stock):
    with open(f"stock_{pid}_{plid}.txt", "w", encoding="utf-8") as f:
        for s in stock: f.write(f"{s}\n")

def get_one_item(pid, plid):
    stock = load_stock(pid, plid)
    if stock:
        item = stock.pop(0)
        save_stock(pid, plid, stock)
        return item
    return None

def generate_pix(amount):
    # BRCode Simplificado para o Bot
    pix_key = PIX_KEY
    val = f"{amount:.2f}"
    payload = f"00020126330014br.gov.bcb.pix0111{pix_key}52040000530398654{len(val):02d}{val}5802BR5913VENDEDOR6008BRASILIA62070503***6304"
    # CRC16 Simplificado
    return payload + "ABCD" 

# --- Modals ---
class ProductModal(Modal):
    def __init__(self): super().__init__(title="💎 Novo Produto")
    self.add_item(TextInput(label="Nome", required=True))
    self.add_item(TextInput(label="Descrição", style=discord.InputTextStyle.long, required=True))
    async def callback(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        pid = str(uuid.uuid4())[:8]
        PRODUCTS[pid] = {"name": self.children[0].value, "description": self.children[1].value, "plans": {}}
        save_json(PRODUCTS_FILE, PRODUCTS)
        await i.followup.send_message(f"✅ Produto criado! ID: `{pid}`", ephemeral=True)

class PlanModal(Modal):
    def __init__(self, pid): super().__init__(title="➕ Novo Plano"); self.pid = pid
    self.add_item(TextInput(label="Nome do Plano", required=True))
    self.add_item(TextInput(label="Preço (ex: 29.90)", required=True))
    async def callback(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        try: price = float(self.children[1].value.replace(",", "."))
        except: return await i.followup.send_message("❌ Preço inválido!", ephemeral=True)
        plid = str(uuid.uuid4())[:8]
        PRODUCTS[self.pid]["plans"][plid] = {"name": self.children[0].value, "price": price}
        save_json(PRODUCTS_FILE, PRODUCTS)
        await i.followup.send_message("✅ Plano adicionado!", ephemeral=True)

class StockModal(Modal):
    def __init__(self, pid, plid): super().__init__(title="📦 Abastecer"); self.pid, self.plid = pid, plid
    self.add_item(TextInput(label="Itens (um por linha)", style=discord.InputTextStyle.long, required=True))
    async def callback(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        new = [l.strip() for l in self.children[0].value.split("\n") if l.strip()]
        save_stock(self.pid, self.plid, load_stock(self.pid, self.plid) + new)
        await i.followup.send_message(f"✅ {len(new)} itens adicionados!", ephemeral=True)

class DepositModal(Modal):
    def __init__(self): super().__init__(title="💰 Depositar")
    self.add_item(TextInput(label="Valor (R$)", required=True))
    async def callback(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        try: val = float(self.children[0].value.replace(",", "."))
        except: return await i.followup.send_message("❌ Valor inválido!", ephemeral=True)
        txid = str(uuid.uuid4())[:8]
        DEPOSITOS_PENDENTES[txid] = {"uid": i.user.id, "val": val}
        save_json(PENDING_DEPOSITS_FILE, DEPOSITOS_PENDENTES)
        pix = generate_pix(val)
        emb = discord.Embed(title="💳 Depósito PIX", description=f"Valor: **R$ {val:.2f}**\n\n**Copia e Cola:**\n```\n{pix}\n```", color=discord.Color.blue())
        admin = bot.get_channel(ADMIN_CHANNEL_ID)
        if admin:
            v = View(timeout=None)
            v.add_item(Button(label="Aprovar", style=discord.ButtonStyle.success, custom_id=f"dep_app_{txid}"))
            v.add_item(Button(label="Recusar", style=discord.ButtonStyle.danger, custom_id=f"dep_rej_{txid}"))
            await admin.send(f"📥 **Novo Depósito**: R$ {val:.2f} por <@{i.user.id}>", view=v)
        await i.followup.send_message(embed=emb, ephemeral=True)

# --- Views ---
class BuyOptionsView(View):
    def __init__(self, pid, plid):
        super().__init__(timeout=None)
        self.pid, self.plid = pid, plid
    @discord.ui.button(label="✅ Já Paguei (Manual)", style=discord.ButtonStyle.success)
    async def manual(self, b, i):
        await i.response.defer(ephemeral=True)
        admin = bot.get_channel(ADMIN_CHANNEL_ID)
        if admin:
            v = View(timeout=None)
            v.add_item(Button(label="Aprovar Venda", style=discord.ButtonStyle.success, custom_id=f"sale_app_{self.pid}_{self.plid}_{i.user.id}"))
            v.add_item(Button(label="Recusar Venda", style=discord.ButtonStyle.danger, custom_id=f"sale_rej_{i.user.id}"))
            await admin.send(f"🛒 **Venda Manual**: {PRODUCTS[self.pid]['name']} por <@{i.user.id}>", view=v)
        await i.followup.send_message("✅ Notificado! Aguarde aprovação.", ephemeral=True)
    @discord.ui.button(label="💰 Comprar com Saldo", style=discord.ButtonStyle.primary)
    async def wallet(self, b, i):
        await i.response.defer(ephemeral=True)
        w = get_wallet(i.user.id); pl = PRODUCTS[self.pid]["plans"][self.plid]
        if w["balance"] < pl["price"]: return await i.followup.send_message("❌ Saldo insuficiente!", ephemeral=True)
        item = get_one_item(self.pid, self.plid)
        if not item: return await i.followup.send_message("❌ Sem estoque!", ephemeral=True)
        update_balance(i.user.id, -pl["price"])
        try: await i.user.send(f"🎉 Compra Automática: `{item}`"); await i.followup.send_message("✅ Entregue na DM!", ephemeral=True)
        except: await i.followup.send_message(f"⚠️ DM fechada! Item: `{item}`", ephemeral=True)

class PlanSelectView(View):
    def __init__(self, pid):
        super().__init__(timeout=None); self.pid = pid
        opts = [discord.SelectOption(label=f"{p['name']} - R$ {p['price']:.2f}", value=plid) for plid, p in PRODUCTS[pid]["plans"].items()]
        if opts:
            sel = Select(placeholder="Escolha o plano...", options=opts)
            sel.callback = self.sel_cb; self.add_item(sel)
    async def sel_cb(self, i):
        await i.response.defer(ephemeral=True)
        plid = i.data["values"][0]; pl = PRODUCTS[self.pid]["plans"][plid]
        pix = generate_pix(pl["price"])
        emb = discord.Embed(title="🛒 Pagamento", description=f"Produto: **{PRODUCTS[self.pid]['name']}**\nPreço: **R$ {pl['price']:.2f}**\n\n**PIX Copia e Cola:**\n```\n{pix}\n```", color=discord.Color.gold())
        await i.followup.send_message(embed=emb, view=BuyOptionsView(self.pid, plid), ephemeral=True)

# --- Comandos ---
@bot.slash_command(name="perfil")
async def perfil(ctx):
    w = get_wallet(ctx.author.id)
    v = View(); v.add_item(Button(label="💰 Depositar", style=discord.ButtonStyle.success, custom_id="btn_deposit"))
    await ctx.respond(f"👤 **Perfil**: <@{ctx.author.id}>\n💵 **Saldo**: `R$ {w['balance']:.2f}`", view=v)

@bot.slash_command(name="loja")
async def loja(ctx):
    if not PRODUCTS: return await ctx.respond("Loja vazia!", ephemeral=True)
    v = View(); opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
    sel = Select(placeholder="Escolha o produto...", options=opts)
    async def cb(i):
        await i.response.defer(ephemeral=True)
        pid = i.data["values"][0]; p = PRODUCTS[pid]
        emb = discord.Embed(title=p["name"], description=p["description"], color=discord.Color.blue())
        await i.followup.send_message(embed=emb, view=PlanSelectView(pid), ephemeral=True)
    sel.callback = cb; v.add_item(sel); await ctx.respond("🛍️ **Loja**", view=v)

@bot.slash_command(name="painel")
async def painel(ctx):
    if ctx.author.id != OWNER_ID: return await ctx.respond("Negado!", ephemeral=True)
    v = View()
    v.add_item(Button(label="➕ Produto", style=discord.ButtonStyle.success, custom_id="adm_p"))
    v.add_item(Button(label="➕ Plano", style=discord.ButtonStyle.primary, custom_id="adm_pl"))
    v.add_item(Button(label="📦 Estoque", style=discord.ButtonStyle.secondary, custom_id="adm_s"))
    await ctx.respond("🛠️ **Admin**", view=v, ephemeral=True)

# --- Evento Global ---
@bot.event
async def on_interaction(i: discord.Interaction):
    if i.type == discord.InteractionType.application_command:
        await bot.process_application_commands(i)
        return
    
    if i.type == discord.InteractionType.component:
        cid = i.data.get("custom_id", "")
        
        # Aprovações Admin
        if cid.startswith("dep_app_"):
            await i.response.defer(ephemeral=True); txid = cid[8:]
            if txid in DEPOSITOS_PENDENTES:
                d = DEPOSITOS_PENDENTES.pop(txid); save_json(PENDING_DEPOSITS_FILE, DEPOSITOS_PENDENTES)
                update_balance(d["uid"], d["val"])
                try: u = await bot.fetch_user(d["uid"]); await u.send(f"✅ Depósito de R$ {d['val']:.2f} aprovado!")
                except: pass
                await i.followup.send_message("✅ Aprovado!", ephemeral=True); await i.message.edit(view=None)
        
        elif cid.startswith("sale_app_"):
            await i.response.defer(ephemeral=True); _, _, pid, plid, uid = cid.split("_")
            item = get_one_item(pid, plid)
            if item:
                try: u = await bot.fetch_user(int(uid)); await u.send(f"✅ Venda Aprovada! Item: `{item}`")
                except: pass
                await i.followup.send_message("✅ Entregue!", ephemeral=True); await i.message.edit(view=None)
            else: await i.followup.send_message("❌ Sem estoque!", ephemeral=True)

        # Botões Gerais
        elif cid == "btn_deposit": await i.response.send_modal(DepositModal())
        elif cid == "adm_p": await i.response.send_modal(ProductModal())
        elif cid == "adm_pl":
            v = View(); opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
            if not opts: return await i.response.send_message("Crie um produto!", ephemeral=True)
            sel = Select(options=opts); sel.callback = lambda i2: i2.response.send_modal(PlanModal(sel.values[0]))
            v.add_item(sel); await i.response.send_message("Produto:", view=v, ephemeral=True)
        elif cid == "adm_s":
            v = View(); opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
            if not opts: return await i.response.send_message("Crie um produto!", ephemeral=True)
            sel = Select(options=opts)
            async def cb_p(i2):
                pid = sel.values[0]; v2 = View(); opts2 = [discord.SelectOption(label=pl["name"], value=plid) for plid, pl in PRODUCTS[pid]["plans"].items()]
                if not opts2: return await i2.response.send_message("Crie um plano!", ephemeral=True)
                sel2 = Select(options=opts2); sel2.callback = lambda i3: i3.response.send_modal(StockModal(pid, sel2.values[0]))
                v2.add_item(sel2); await i2.response.send_message("Plano:", view=v2, ephemeral=True)
            sel.callback = cb_p; v.add_item(sel); await i.response.send_message("Produto:", view=v, ephemeral=True)

@bot.event
async def on_ready(): print(f"Bot V5 Corrigido online como {bot.user}")

if DISCORD_BOT_TOKEN: bot.run(DISCORD_BOT_TOKEN)
