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
        self.wfile.write(b"<html><body><h1>Bot Profissional Hibrido Online!</h1></body></html>")
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
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID") or 0)
OWNER_ID = int(os.getenv("OWNER_ID") or 0)

PRODUCTS_FILE = "products.json"
SALES_LOG_FILE = "sales_log.json"
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
SALES_LOG = load_json(SALES_LOG_FILE)
WALLETS = load_json(WALLETS_FILE)
DEPOSITOS_PENDENTES = load_json(PENDING_DEPOSITS_FILE)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = discord.Bot(intents=intents)

# --- Funções de Carteira ---
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

# --- Funções de Estoque ---
def get_stock_file_path(product_id, plan_id):
    return f"stock_{product_id}_{plan_id}.txt"

def load_stock(product_id, plan_id):
    path = get_stock_file_path(product_id, plan_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f: return [line.strip() for line in f if line.strip()]
    return []

def save_stock(product_id, plan_id, stock_list):
    path = get_stock_file_path(product_id, plan_id)
    with open(path, "w", encoding="utf-8") as f:
        for item in stock_list: f.write(f"{item}\n")

def get_available_stock_count(product_id, plan_id):
    return len(load_stock(product_id, plan_id))

def get_total_product_stock_count(product_id):
    total_stock = 0
    if product_id in PRODUCTS:
        for plan_id in PRODUCTS[product_id]["plans"].keys():
            total_stock += get_available_stock_count(product_id, plan_id)
    return total_stock

def get_one_account_from_stock(product_id, plan_id):
    stock = load_stock(product_id, plan_id)
    if stock:
        account = stock.pop(0)
        save_stock(product_id, plan_id, stock)
        return account
    return None

# --- Gerador de PIX BRCode ---
def crc16(data: str):
    crc = 0xFFFF
    for char in data:
        crc ^= ord(char) << 8
        for _ in range(8):
            if crc & 0x8000: crc = (crc << 1) ^ 0x1021
            else: crc <<= 1
            crc &= 0xFFFF
    return f"{crc:04X}"

def generate_pix_payload(pix_key, amount, name="Vendedor", city="Brasilia"):
    payload = "00020126"
    gui = "0014BR.GOV.BR.BCB01"
    key = f"01{len(pix_key):02d}{pix_key}"
    merchant_account = f"{len(gui+key):02d}{gui}{key}"
    payload += merchant_account + "52040000530398654"
    val_str = f"{amount:.2f}"
    payload += f"{len(val_str):02d}{val_str}5802BR59{len(name):02d}{name}60{len(city):02d}{city}62070503***6304"
    payload += crc16(payload)
    return payload

# --- Modals ---
class DepositModal(Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="💰 Adicionar Saldo")
        self.add_item(TextInput(label="Valor (R$)", placeholder="Ex: 50.00", required=True))
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try: val = float(self.children[0].value.replace(",", "."))
        except: return await interaction.followup.send_message("❌ Valor inválido!", ephemeral=True)
        txid = str(uuid.uuid4())[:8]
        DEPOSITOS_PENDENTES[txid] = {"user_id": interaction.user.id, "value": val}
        save_json(PENDING_DEPOSITS_FILE, DEPOSITOS_PENDENTES)
        pix = generate_pix_payload(PIX_KEY, val)
        embed = discord.Embed(title="💳 Depósito PIX", description=f"Valor: **R$ {val:.2f}**\n\n**Copia e Cola:**\n```\n{pix}\n```", color=discord.Color.blue())
        admin = bot.get_channel(ADMIN_CHANNEL_ID)
        if admin:
            v = View(timeout=None)
            v.add_item(Button(label="Aprovar", style=discord.ButtonStyle.success, custom_id=f"dep_app_{txid}"))
            v.add_item(Button(label="Recusar", style=discord.ButtonStyle.danger, custom_id=f"dep_rej_{txid}"))
            await admin.send(f"📥 **Novo Depósito**: R$ {val:.2f} por <@{interaction.user.id}>", view=v)
        await interaction.followup.send_message(embed=embed, ephemeral=True)

# (Outros Modals de Admin do código antigo seriam mantidos aqui...)
class ProductModal(Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="💎 Criar Novo Produto")
        self.add_item(TextInput(label="Título", required=True))
        self.add_item(TextInput(label="Descrição", style=discord.InputTextStyle.long, required=True))
    async def callback(self, interaction: discord.Interaction):
        pid = str(uuid.uuid4())[:8]
        PRODUCTS[pid] = {"name": self.children[0].value, "description": self.children[1].value, "plans": {}}
        save_json(PRODUCTS_FILE, PRODUCTS)
        await interaction.response.send_message("✅ Produto criado!", ephemeral=True)

class AddPlanModal(Modal):
    def __init__(self, product_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="➕ Novo Plano")
        self.product_id = product_id
        self.add_item(TextInput(label="Nome", required=True))
        self.add_item(TextInput(label="Preço", required=True))
    async def callback(self, interaction: discord.Interaction):
        try: price = float(self.children[1].value.replace(",", "."))
        except: return await interaction.response.send_message("❌ Preço inválido!", ephemeral=True)
        plid = str(uuid.uuid4())[:8]
        PRODUCTS[self.product_id]["plans"][plid] = {"name": self.children[0].value, "price": price}
        save_json(PRODUCTS_FILE, PRODUCTS)
        await interaction.response.send_message("✅ Plano adicionado!", ephemeral=True)

class AddStockModal(Modal):
    def __init__(self, product_id, plan_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="📦 Abastecer")
        self.product_id, self.plan_id = product_id, plan_id
        self.add_item(TextInput(label="Contas (uma por linha)", style=discord.InputTextStyle.long, required=True))
    async def callback(self, interaction: discord.Interaction):
        new = [l.strip() for l in self.children[0].value.split("\n") if l.strip()]
        save_stock(self.product_id, self.plan_id, load_stock(self.product_id, self.plan_id) + new)
        await interaction.response.send_message(f"✅ {len(new)} itens adicionados!", ephemeral=True)

# --- Views ---
class ApprovalView(View):
    def __init__(self, buyer_id, product_id, plan_id, product_name, plan_name):
        super().__init__(timeout=None)
        self.buyer_id, self.product_id, self.plan_id, self.product_name, self.plan_name = buyer_id, product_id, plan_id, product_name, plan_name
    @discord.ui.button(label="✅ Aprovar", style=discord.ButtonStyle.success)
    async def approve(self, button, interaction):
        if interaction.user.id != OWNER_ID: return
        await interaction.response.defer(ephemeral=True)
        item = get_one_account_from_stock(self.product_id, self.plan_id)
        if item:
            try:
                u = await bot.fetch_user(self.buyer_id)
                await u.send(f"✅ Compra Aprovada: **{self.product_name}**\n🔑 Item: `{item}`")
                await interaction.followup.send_message("✅ Entregue!", ephemeral=True)
                await interaction.message.edit(view=None)
            except: await interaction.followup.send_message("❌ Erro DM!", ephemeral=True)
        else: await interaction.followup.send_message("❌ Sem estoque!", ephemeral=True)

class ProductBuyPlanSelectView(View):
    def __init__(self, product_id):
        super().__init__(timeout=None)
        self.product_id = product_id
        options = [discord.SelectOption(label=f"{p['name']} - R$ {p['price']:.2f}", value=plid) for plid, p in PRODUCTS[product_id]["plans"].items() if get_available_stock_count(product_id, plid) > 0]
        if options: self.add_item(Select(placeholder="Escolha o plano...", options=options, custom_id="plan_sel"))
    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.data.get("custom_id") == "plan_sel":
            await interaction.response.defer(ephemeral=True)
            plid = interaction.data["values"][0]; p = PRODUCTS[self.product_id]; pl = p["plans"][plid]
            pix = generate_pix_payload(PIX_KEY, pl["price"])
            emb = discord.Embed(title=f"🛒 {p['name']} - {pl['name']}", description=f"Preço: **R$ {pl['price']:.2f}**\n\n**Opção 1: Pagar Agora (Manual)**\n```\n{pix}\n```\nApós pagar, clique no botão abaixo.\n\n**Opção 2: Automático (Carteira)**\nUse seu saldo para receber na hora.", color=discord.Color.gold())
            v = View(timeout=None)
            v.add_item(Button(label="✅ Já Paguei (Manual)", style=discord.ButtonStyle.success, custom_id=f"paid_man_{self.product_id}_{plid}"))
            v.add_item(Button(label="💰 Comprar com Saldo", style=discord.ButtonStyle.primary, custom_id=f"paid_auto_{self.product_id}_{plid}"))
            await interaction.followup.send_message(embed=emb, view=v, ephemeral=True)
        return True

# --- Comandos ---
@bot.slash_command(name="perfil")
async def perfil(ctx):
    w = get_wallet(ctx.author.id)
    v = View(); v.add_item(Button(label="💰 Depositar", style=discord.ButtonStyle.success, custom_id="w_dep"))
    await ctx.respond(f"👤 **Perfil**: <@{ctx.author.id}>\n💵 **Saldo**: `R$ {w['balance']:.2f}`", view=v)

@bot.slash_command(name="loja")
async def loja(ctx):
    if not PRODUCTS: return await ctx.respond("Loja vazia!", ephemeral=True)
    v = View(); options = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
    sel = Select(placeholder="Produto...", options=options)
    async def cb(i):
        await i.response.defer(ephemeral=True)
        pid = sel.values[0]; p = PRODUCTS[pid]
        emb = discord.Embed(title=p["name"], description=p["description"], color=discord.Color.blue())
        await i.followup.send_message(embed=emb, view=ProductBuyPlanSelectView(pid), ephemeral=True)
    sel.callback = cb; v.add_item(sel); await ctx.respond("🛍️ **Loja**", view=v)

@bot.slash_command(name="painel")
async def painel(ctx):
    if ctx.author.id != OWNER_ID: return await ctx.respond("Negado!", ephemeral=True)
    v = View()
    v.add_item(Button(label="➕ Produto", style=discord.ButtonStyle.success, custom_id="adm_p"))
    v.add_item(Button(label="➕ Plano", style=discord.ButtonStyle.primary, custom_id="adm_pl"))
    v.add_item(Button(label="📦 Estoque", style=discord.ButtonStyle.secondary, custom_id="adm_s"))
    await ctx.respond("🛠️ Admin", view=v, ephemeral=True)

# --- Evento Global ---
@bot.event
async def on_interaction(i: discord.Interaction):
    if i.type == discord.InteractionType.application_command: await bot.process_application_commands(i)
    if i.type == discord.InteractionType.component:
        cid = i.data.get("custom_id", "")
        
        # Pagamento Manual (Antigo)
        if cid.startswith("paid_man_"):
            await i.response.defer(ephemeral=True); _, _, pid, plid = cid.split("_"); p = PRODUCTS[pid]; pl = p["plans"][plid]
            admin = bot.get_channel(ADMIN_CHANNEL_ID)
            if admin:
                v = ApprovalView(i.user.id, pid, plid, p["name"], pl["name"])
                await admin.send(f"🛒 **Venda Manual**: {p['name']} ({pl['name']}) por <@{i.user.id}>", view=v)
            await i.followup.send_message("✅ Notificado! Aguarde a aprovação.", ephemeral=True)

        # Pagamento Automático (Carteira)
        elif cid.startswith("paid_auto_"):
            await i.response.defer(ephemeral=True); _, _, pid, plid = cid.split("_"); w = get_wallet(i.user.id); pl = PRODUCTS[pid]["plans"][plid]
            if w["balance"] < pl["price"]: return await i.followup.send_message("❌ Saldo insuficiente!", ephemeral=True)
            item = get_one_account_from_stock(pid, plid)
            if not item: return await i.followup.send_message("❌ Sem estoque!", ephemeral=True)
            update_balance(i.user.id, -pl["price"])
            try: await i.user.send(f"🎉 Compra Automática: `{item}`"); await i.followup.send_message("✅ Entregue na DM!", ephemeral=True)
            except: await i.followup.send_message(f"⚠️ DM fechada! Item: `{item}`", ephemeral=True)

        # Depósito
        elif cid.startswith("dep_app_"):
            await i.response.defer(ephemeral=True); txid = cid[8:]
            if txid in DEPOSITOS_PENDENTES:
                d = DEPOSITOS_PENDENTES.pop(txid); save_json(PENDING_DEPOSITS_FILE, DEPOSITOS_PENDENTES)
                update_balance(d["user_id"], d["value"])
                try: u = await bot.fetch_user(d["user_id"]); await u.send(f"✅ Depósito de R$ {d['value']:.2f} aprovado!")
                except: pass
                await i.followup.send_message("✅ Aprovado!", ephemeral=True); await i.message.edit(view=None)

        # Botões
        elif cid == "w_dep": await i.response.send_modal(DepositModal())
        elif cid == "adm_p": await i.response.send_modal(ProductModal())
        elif cid == "adm_pl":
            v = View(); sel = Select(placeholder="Produto...")
            for pid, p in PRODUCTS.items(): sel.add_item(discord.SelectOption(label=p["name"], value=pid))
            async def cb(i2): await i2.response.send_modal(AddPlanModal(sel.values[0]))
            sel.callback = cb; v.add_item(sel); await i.response.send_message("Produto:", view=v, ephemeral=True)
        elif cid == "adm_s":
            v = View(); sel = Select(placeholder="Produto...")
            for pid, p in PRODUCTS.items(): sel.add_item(discord.SelectOption(label=p["name"], value=pid))
            async def cb(i2):
                pid = sel.values[0]; v2 = View(); sel2 = Select(placeholder="Plano...")
                for plid, pl in PRODUCTS[pid]["plans"].items(): sel2.add_item(discord.SelectOption(label=pl["name"], value=plid))
                async def cb2(i3): await i3.response.send_modal(AddStockModal(pid, sel2.values[0]))
                sel2.callback = cb2; v2.add_item(sel2); await i2.response.send_message("Plano:", view=v2, ephemeral=True)
            sel.callback = cb; v.add_item(sel); await i.response.send_message("Produto:", view=v, ephemeral=True)

@bot.event
async def on_ready(): print(f"Bot Hibrido V4 online como {bot.user}")

if DISCORD_BOT_TOKEN: bot.run(DISCORD_BOT_TOKEN)
