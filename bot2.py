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
import qrcode
import base64
from io import BytesIO

# --- CÓDIGO PARA MANTER ONLINE NO RENDER (ANTI-SONO ) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body><h1>Bot Profissional Online!</h1></body></html>")
    def log_message(self, format, *args): return

def run_health_check():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_health_check, daemon=True).start()
# -------------------------------------------------------

load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
PIX_KEY = os.getenv("PIX_KEY") 
ADMIN_CHANNEL_ID = int(os.getenv("ADMIN_CHANNEL_ID") or 0)
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID") or 0)
OWNER_ID = int(os.getenv("OWNER_ID") or 0)

# Arquivos de Dados
PRODUCTS_FILE = "products.json"
WALLETS_FILE = "wallets.json"
PENDING_DEPOSITS_FILE = "pending_deposits.json"
PENDING_SALES_FILE = "pending_sales.json"

def load_data(file, default):
    if os.path.exists(file) and os.path.getsize(file) > 0:
        with open(file, "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return default
    return default

def save_data(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

PRODUCTS = load_data(PRODUCTS_FILE, {})
WALLETS = load_data(WALLETS_FILE, {})
DEPOSITOS_PENDENTES = load_data(PENDING_DEPOSITS_FILE, {})
PEDIDOS_PENDENTES = load_data(PENDING_SALES_FILE, {})

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = discord.Bot(intents=intents)

# --- SISTEMA DE ESTOQUE ---
def get_stock_file(pid, plid): return f"stock_{pid}_{plid}.txt"

def load_stock(pid, plid):
    path = get_stock_file(pid, plid)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f: return [l.strip() for l in f if l.strip()]
    return []

def save_stock(pid, plid, stock):
    with open(get_stock_file(pid, plid), "w", encoding="utf-8") as f:
        for item in stock: f.write(f"{item}\n")

def get_stock_count(pid, plid): return len(load_stock(pid, plid))

# --- GERAÇÃO DE PIX BRCODE ---
def generate_pix(val, tid):
    # Simplificado para compatibilidade
    payload = f"00020126330014br.gov.bcb.pix01{len(PIX_KEY):02d}{PIX_KEY}52040000530398654{len(f'{val:.2f}'):02d}{val:.2f}5802BR5913BOT DE VENDAS6008BRASILIA62{len(f'05{len(tid):02d}{tid}'):02d}05{len(tid):02d}{tid}6304"
    def crc16(d):
        c = 0xFFFF
        for b in d.encode("ascii"):
            c ^= (b << 8)
            for _ in range(8):
                if (c & 0x8000): c = (c << 1) ^ 0x1021
                else: c <<= 1
        return c & 0xFFFF
    return f"{payload}{crc16(payload):04X}"

# --- INTERFACE DO USUÁRIO ---
class DepositModal(Modal):
    def __init__(self):
        super().__init__(title="Adicionar Saldo")
        self.add_item(TextInput(label="Valor do Depósito (R$)", placeholder="Ex: 50.00"))

    async def callback(self, interaction: discord.Interaction):
        try: val = float(self.children[0].value.replace(",", "."))
        except: return await interaction.response.send_message("Valor inválido!", ephemeral=True)
        
        tid = str(uuid.uuid4())[:8]
        payload = generate_pix(val, tid)
        
        DEPOSITOS_PENDENTES[tid] = {"user_id": interaction.user.id, "value": val, "status": "PENDENTE"}
        save_data(PENDING_DEPOSITS_FILE, DEPOSITOS_PENDENTES)
        
        emb = discord.Embed(title="💳 Depósito via PIX", description=f"Valor: **R$ {val:.2f}**\n\nCopie o código abaixo e pague no seu banco. Após pagar, envie o comprovante para o suporte.", color=discord.Color.blue())
        emb.add_field(name="PIX Copia e Cola", value=f"```\n{payload}\n```")
        await interaction.response.send_message(embed=emb, ephemeral=True)

class BuyView(View):
    def __init__(self, pid):
        super().__init__(timeout=None)
        self.pid = pid
        p = PRODUCTS[pid]
        opts = [discord.SelectOption(label=f"{pl['name']} - R$ {pl['price']:.2f} ({get_stock_count(pid, plid)} em estoque)", value=plid) for plid, pl in p["plans"].items()]
        self.add_item(Select(placeholder="Escolha um plano...", options=opts, custom_id="sel_plan"))

    @discord.ui.button(label="Comprar com Saldo", style=discord.ButtonStyle.green)
    async def buy_balance(self, button, interaction):
        plid = self.children[0].values[0] if self.children[0].values else None
        if not plid: return await interaction.response.send_message("Selecione um plano!", ephemeral=True)
        
        uid = str(interaction.user.id)
        balance = WALLETS.get(uid, 0)
        price = PRODUCTS[self.pid]["plans"][plid]["price"]
        
        if balance < price: return await interaction.response.send_message(f"Saldo insuficiente! Você tem R$ {balance:.2f}", ephemeral=True)
        
        stock = load_stock(self.pid, plid)
        if not stock: return await interaction.response.send_message("Sem estoque!", ephemeral=True)
        
        item = stock.pop(0)
        save_stock(self.pid, plid, stock)
        WALLETS[uid] = balance - price
        save_data(WALLETS_FILE, WALLETS)
        
        await interaction.user.send(f"✅ Compra realizada! Seu item: `{item}`")
        await interaction.response.send_message("✅ Item enviado na sua DM!", ephemeral=True)

# --- COMANDOS ---
@bot.slash_command(name="carteira", description="Ver seu saldo e depositar")
async def carteira(ctx):
    uid = str(ctx.author.id)
    bal = WALLETS.get(uid, 0)
    emb = discord.Embed(title="💰 Minha Carteira", description=f"Seu saldo atual: **R$ {bal:.2f}**", color=discord.Color.gold())
    view = View(); view.add_item(Button(label="Adicionar Saldo", style=discord.ButtonStyle.primary, custom_id="dep"))
    await ctx.respond(embed=emb, view=view)

@bot.slash_command(name="painel", description="Painel Admin")
async def painel(ctx):
    if ctx.author.id != OWNER_ID: return await ctx.respond("Acesso negado!", ephemeral=True)
    await ctx.respond("🛠️ Painel Admin", ephemeral=True)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        cid = interaction.data.get("custom_id")
        if cid == "dep": await interaction.response.send_modal(DepositModal())

@bot.event
async def on_ready():
    print(f"Bot Online: {bot.user}")
    await bot.sync_commands()

bot.run(DISCORD_BOT_TOKEN)
