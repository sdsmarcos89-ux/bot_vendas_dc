import os
import sys
import subprocess

# --- AUTO-INSTALL DE DEPENDÊNCIAS ---
def install_dependencies():
    libs = ["py-cord", "python-dotenv", "qrcode", "pillow"]
    for lib in libs:
        try:
            __import__(lib.replace("-", "_"))
        except ImportError:
            print(f"Instalando {lib}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", lib])

install_dependencies()
# ------------------------------------

import discord
from discord.ui import Button, View, Modal, TextInput, Select
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
import asyncio
import time
from datetime import datetime
import uuid
import qrcode
import base64
from io import BytesIO

# --- HEALTH CHECK PARA O RENDER ---
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
# ----------------------------------

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
PIX_KEY = os.getenv("PIX_KEY") 
ADMIN_ID = int(os.getenv("ADMIN_CHANNEL_ID") or 0)
OWNER_ID = int(os.getenv("OWNER_ID") or 0)

# Arquivos de Dados
DB = {"products": "products.json", "wallets": "wallets.json", "deposits": "pending_deposits.json"}

def load_db(key):
    file = DB[key]
    if os.path.exists(file) and os.path.getsize(file) > 0:
        with open(file, "r", encoding="utf-8") as f: return json.load(f)
    return {}

def save_db(key, data):
    with open(DB[key], "w", encoding="utf-8") as f: json.dump(data, f, indent=4, ensure_ascii=False)

PRODUCTS = load_db("products")
WALLETS = load_db("wallets")
DEPOSITS = load_db("deposits")

bot = discord.Bot(intents=discord.Intents.all())

# --- Lógica de Negócio ---
def get_wallet(uid):
    uid = str(uid)
    if uid not in WALLETS: WALLETS[uid] = {"balance": 0.0}; save_db("wallets", WALLETS)
    return WALLETS[uid]

def add_balance(uid, amount):
    uid = str(uid); w = get_wallet(uid)
    w["balance"] += amount; save_db("wallets", WALLETS)
    return w["balance"]

def get_stock(pid, plid):
    path = f"stock_{pid}_{plid}.txt"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f: return [l.strip() for l in f if l.strip()]
    return []

def save_stock(pid, plid, stock):
    with open(f"stock_{pid}_{plid}.txt", "w", encoding="utf-8") as f:
        for s in stock: f.write(f"{s}\n")

# --- Modals ---
class DepositModal(Modal):
    def __init__(self): super().__init__(title="💰 Adicionar Saldo")
    self.add_item(TextInput(label="Valor (R$)", placeholder="10.00"))
    async def callback(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        try: val = float(self.children[0].value.replace(",", "."))
        except: return await i.followup.send_message("❌ Valor inválido!", ephemeral=True)
        txid = str(uuid.uuid4())[:8]
        DEPOSITS[txid] = {"uid": i.user.id, "val": val}
        save_db("deposits", DEPOSITS)
        pix = f"00020126330014br.gov.bcb.pix0111{PIX_KEY}52040000530398654{len(f'{val:.2f}'):02d}{val:.2f}5802BR5913BOT6008BRASILIA62070503{txid[:3]}6304"
        emb = discord.Embed(title="💳 PIX Gerado", description=f"Valor: **R$ {val:.2f}**\n\n**Copia e Cola:**\n```\n{pix}\n```", color=0x00ff00)
        admin = bot.get_channel(ADMIN_ID)
        if admin:
            v = View(timeout=None)
            v.add_item(Button(label="Aprovar", style=discord.ButtonStyle.success, custom_id=f"app_{txid}"))
            v.add_item(Button(label="Recusar", style=discord.ButtonStyle.danger, custom_id=f"rej_{txid}"))
            await admin.send(f"🔔 Depósito de R$ {val:.2f} por <@{i.user.id}>", view=v)
        await i.followup.send_message(embed=emb, ephemeral=True)

class ProductModal(Modal):
    def __init__(self, pid=None):
        super().__init__(title="💎 Produto")
        self.pid = pid
        self.add_item(TextInput(label="Nome", default_value=PRODUCTS[pid]["name"] if pid else ""))
        self.add_item(TextInput(label="Descrição", style=discord.InputTextStyle.long, default_value=PRODUCTS[pid]["description"] if pid else ""))
    async def callback(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        pid = self.pid or str(uuid.uuid4())[:8]
        PRODUCTS[pid] = {"name": self.children[0].value, "description": self.children[1].value, "plans": PRODUCTS[pid]["plans"] if self.pid else {}}
        save_db("products", PRODUCTS); await i.followup.send_message("✅ Salvo!", ephemeral=True)

class PlanModal(Modal):
    def __init__(self, pid): super().__init__(title="➕ Novo Plano"); self.pid = pid
    self.add_item(TextInput(label="Nome")); self.add_item(TextInput(label="Preço"))
    async def callback(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        plid = str(uuid.uuid4())[:8]
        PRODUCTS[self.pid]["plans"][plid] = {"name": self.children[0].value, "price": float(self.children[1].value)}
        save_db("products", PRODUCTS); await i.followup.send_message("✅ Plano Adicionado!", ephemeral=True)

# --- Comandos ---
@bot.slash_command(name="perfil")
async def perfil(ctx):
    w = get_wallet(ctx.author.id)
    v = View(); v.add_item(Button(label="💰 Depositar", style=discord.ButtonStyle.success, custom_id="btn_dep"))
    await ctx.respond(f"👤 **Seu Perfil**\n💵 Saldo: `R$ {w['balance']:.2f}`", view=v)

@bot.slash_command(name="loja")
async def loja(ctx):
    if not PRODUCTS: return await ctx.respond("Loja vazia!", ephemeral=True)
    v = View(); sel = Select(placeholder="Escolha um produto...")
    for pid, p in PRODUCTS.items(): sel.add_item(discord.SelectOption(label=p["name"], value=pid))
    async def sel_cb(i):
        await i.response.defer(ephemeral=True)
        pid = sel.values[0]; p = PRODUCTS[pid]; plans = p["plans"]
        emb = discord.Embed(title=p["name"], description=p["description"], color=0x0000ff)
        v2 = View()
        for plid, pl in plans.items():
            stock = len(get_stock(pid, plid))
            v2.add_item(Button(label=f"{pl['name']} - R$ {pl['price']:.2f} ({stock})", style=discord.ButtonStyle.primary, custom_id=f"buy_{pid}_{plid}"))
        await i.followup.send_message(embed=emb, view=v2, ephemeral=True)
    sel.callback = sel_cb; v.add_item(sel); await ctx.respond("🛍️ **Nossa Loja**", view=v)

@bot.slash_command(name="painel")
async def painel(ctx):
    if ctx.author.id != OWNER_ID: return await ctx.respond("Acesso negado!", ephemeral=True)
    v = View()
    v.add_item(Button(label="➕ Novo Produto", style=discord.ButtonStyle.success, custom_id="adm_p"))
    v.add_item(Button(label="➕ Novo Plano", style=discord.ButtonStyle.primary, custom_id="adm_pl"))
    v.add_item(Button(label="📦 Estoque", style=discord.ButtonStyle.secondary, custom_id="adm_s"))
    await ctx.respond("🛠️ **Painel Admin**", view=v, ephemeral=True)

# --- Evento Global ---
@bot.event
async def on_interaction(i: discord.Interaction):
    if i.type == discord.InteractionType.application_command: await bot.process_application_commands(i)
    if i.type == discord.InteractionType.component:
        cid = i.data.get("custom_id", "")
        if cid == "btn_dep": await i.response.send_modal(DepositModal())
        elif cid.startswith("app_"):
            await i.response.defer(ephemeral=True); txid = cid[4:]
            if txid in DEPOSITS:
                d = DEPOSITS.pop(txid); save_db("deposits", DEPOSITS); add_balance(d["uid"], d["val"])
                try: u = await bot.fetch_user(d["uid"]); await u.send(f"✅ Depósito de R$ {d['val']:.2f} aprovado!")
                except: pass
                await i.followup.send_message("✅ Aprovado!", ephemeral=True); await i.message.edit(view=None)
        elif cid.startswith("buy_"):
            await i.response.defer(ephemeral=True); _, pid, plid = cid.split("_")
            w = get_wallet(i.user.id); pl = PRODUCTS[pid]["plans"][plid]
            if w["balance"] < pl["price"]: return await i.followup.send_message("❌ Saldo insuficiente!", ephemeral=True)
            s = get_stock(pid, plid)
            if not s: return await i.followup.send_message("❌ Sem estoque!", ephemeral=True)
            item = s.pop(0); save_stock(pid, plid, s); add_balance(i.user.id, -pl["price"])
            try: await i.user.send(f"🎉 Compra: `{item}`"); await i.followup.send_message("✅ Entregue na DM!", ephemeral=True)
            except: await i.followup.send_message(f"⚠️ DM fechada! Item: `{item}`", ephemeral=True)
        elif cid == "adm_p": await i.response.send_modal(ProductModal())
        elif cid == "adm_pl":
            v = View(); sel = Select(placeholder="Produto...")
            for pid, p in PRODUCTS.items(): sel.add_item(discord.SelectOption(label=p["name"], value=pid))
            async def cb(i2): await i2.response.send_modal(PlanModal(sel.values[0]))
            sel.callback = cb; v.add_item(sel); await i.response.send_message("Escolha:", view=v, ephemeral=True)
        elif cid == "adm_s":
            v = View(); sel = Select(placeholder="Produto...")
            for pid, p in PRODUCTS.items(): sel.add_item(discord.SelectOption(label=p["name"], value=pid))
            async def cb(i2):
                pid = sel.values[0]; v2 = View(); sel2 = Select(placeholder="Plano...")
                for plid, pl in PRODUCTS[pid]["plans"].items(): sel2.add_item(discord.SelectOption(label=pl["name"], value=plid))
                async def cb2(i3):
                    class SModal(Modal):
                        def __init__(self): super().__init__(title="Estoque")
                        self.add_item(TextInput(label="Contas", style=discord.InputTextStyle.long))
                        async def callback(self, i4):
                            await i4.response.defer(ephemeral=True)
                            new = [l.strip() for l in self.children[0].value.split("\n") if l.strip()]
                            save_stock(pid, sel2.values[0], get_stock(pid, sel2.values[0]) + new)
                            await i4.followup.send_message("✅ Adicionado!", ephemeral=True)
                    await i3.response.send_modal(SModal())
                sel2.callback = cb2; v2.add_item(sel2); await i2.response.send_message("Plano:", view=v2, ephemeral=True)
            sel.callback = cb; v.add_item(sel); await i.response.send_message("Produto:", view=v, ephemeral=True)

@bot.event
async def on_ready(): print(f"Bot Online: {bot.user}")

if TOKEN: bot.run(TOKEN)
