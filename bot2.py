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

# --- CÓDIGO PARA MANTER ONLINE NO RENDER (ANTI-SONO) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body><h1>Bot Profissional com Carteira Online!</h1></body></html>")
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

PRODUCTS_FILE = "products.json"
SALES_LOG_FILE = "sales_log.json"
WALLETS_FILE = "wallets.json" 
PENDING_DEPOSITS_FILE = "pending_deposits.json"

def load_json(filename):
    if os.path.exists(filename) and os.path.getsize(filename) > 0:
        with open(filename, "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return {} if "log" not in filename else []
    return {} if "log" not in filename else []

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

# --- Funções de Carteira ---
def get_wallet(user_id):
    user_id = str(user_id)
    if user_id not in WALLETS:
        WALLETS[user_id] = {"balance": 0.0, "total_spent": 0.0, "total_deposited": 0.0}
        save_json(WALLETS_FILE, WALLETS)
    return WALLETS[user_id]

def update_balance(user_id, amount):
    user_id = str(user_id)
    wallet = get_wallet(user_id)
    wallet["balance"] += amount
    if amount > 0: wallet["total_deposited"] += amount
    else: wallet["total_spent"] += abs(amount)
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

# --- Geração de PIX ---
def generate_pix_payload(value, txid):
    # Payload simplificado para exibição (Copia e Cola)
    return f"00020126330014br.gov.bcb.pix0111{PIX_KEY}52040000530398654{len(f'{value:.2f}'):02d}{value:.2f}5802BR5913BOT DE VENDAS6008BRASILIA62070503{txid[:3]}6304"

# --- Modals ---
class DepositModal(Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="💰 Adicionar Saldo")
        self.add_item(TextInput(label="Valor do Depósito (R$)", placeholder="Ex: 50.00", required=True))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            value = float(self.children[0].value.replace(",", "."))
            if value < 1.0: return await interaction.followup.send_message("❌ Valor mínimo para depósito é R$ 1,00.", ephemeral=True)
        except:
            return await interaction.followup.send_message("❌ Valor inválido!", ephemeral=True)

        txid = str(uuid.uuid4())[:8]
        pix_payload = generate_pix_payload(value, txid)
        
        DEPOSITOS_PENDENTES[txid] = {"user_id": interaction.user.id, "value": value, "timestamp": datetime.now().isoformat()}
        save_json(PENDING_DEPOSITS_FILE, DEPOSITOS_PENDENTES)

        embed = discord.Embed(title="💳 Depósito Gerado", description=f"Você solicitou um depósito de **R$ {value:.2f}**.\n\n**PIX Copia e Cola:**\n```\n{pix_payload}\n```\nApós pagar, envie o comprovante para um administrador ou aguarde a aprovação manual.", color=discord.Color.blue())
        
        # Notificar Admin
        admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
        if admin_channel:
            admin_embed = discord.Embed(title="🔔 Novo Pedido de Depósito", color=discord.Color.orange())
            admin_embed.add_field(name="Usuário", value=f"<@{interaction.user.id}>", inline=True)
            admin_embed.add_field(name="Valor", value=f"R$ {value:.2f}", inline=True)
            admin_embed.add_field(name="TXID", value=f"`{txid}`", inline=True)
            
            view = View(timeout=None)
            view.add_item(Button(label="✅ Aprovar", style=discord.ButtonStyle.success, custom_id=f"dep_app_{txid}"))
            view.add_item(Button(label="❌ Recusar", style=discord.ButtonStyle.danger, custom_id=f"dep_rej_{txid}"))
            await admin_channel.send(embed=admin_embed, view=view)

        await interaction.followup.send_message(embed=embed, ephemeral=True)

# --- Views ---
class WalletMainView(View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="💰 Adicionar Saldo", style=discord.ButtonStyle.success, custom_id="wallet_deposit")
    async def deposit_callback(self, button, interaction):
        await interaction.response.send_modal(DepositModal())

    @discord.ui.button(label="🔄 Atualizar", style=discord.ButtonStyle.secondary, custom_id="wallet_refresh")
    async def refresh_callback(self, button, interaction):
        await interaction.response.defer(ephemeral=True)
        wallet = get_wallet(interaction.user.id)
        embed = discord.Embed(title="👤 Seu Perfil", color=discord.Color.blue())
        embed.add_field(name="💵 Saldo Atual", value=f"``` R$ {wallet['balance']:.2f} ```", inline=False)
        embed.add_field(name="📊 Total Gasto", value=f"R$ {wallet['total_spent']:.2f}", inline=True)
        embed.add_field(name="📥 Total Depositado", value=f"R$ {wallet['total_deposited']:.2f}", inline=True)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=self)

class ProductBuyView(View):
    def __init__(self, product_id, plan_id):
        super().__init__(timeout=None)
        self.product_id = product_id
        self.plan_id = plan_id

    @discord.ui.button(label="🛒 Comprar com Saldo", style=discord.ButtonStyle.green, custom_id="buy_with_wallet")
    async def buy_callback(self, button, interaction):
        await interaction.response.defer(ephemeral=True)
        wallet = get_wallet(interaction.user.id)
        plan = PRODUCTS[self.product_id]["plans"][self.plan_id]
        
        if wallet["balance"] < plan["price"]:
            return await interaction.followup.send_message(f"❌ Saldo insuficiente! Você precisa de mais R$ {plan['price'] - wallet['balance']:.2f}.", ephemeral=True)
        
        stock = load_stock(self.product_id, self.plan_id)
        if not stock:
            return await interaction.followup.send_message("❌ Estoque vazio para este plano no momento.", ephemeral=True)
        
        item = stock.pop(0)
        save_stock(self.product_id, self.plan_id, stock)
        update_balance(interaction.user.id, -plan["price"])
        
        # Entrega
        try:
            embed = discord.Embed(title="🎉 Compra Realizada!", description=f"Produto: **{PRODUCTS[self.product_id]['name']}**\nPlano: **{plan['name']}**\n\n**Seu Item:**\n```\n{item}\n```", color=discord.Color.green())
            await interaction.user.send(embed=embed)
            await interaction.followup.send_message("✅ Produto entregue na sua DM!", ephemeral=True)
        except:
            await interaction.followup.send_message(f"⚠️ Sua DM está fechada! Aqui está seu item: `{item}`", ephemeral=True)

# --- Comandos ---
@bot.slash_command(name="perfil", description="Veja seu saldo e informações da conta")
async def perfil(ctx):
    wallet = get_wallet(ctx.author.id)
    embed = discord.Embed(title="👤 Seu Perfil", color=discord.Color.blue())
    embed.add_field(name="💵 Saldo Atual", value=f"``` R$ {wallet['balance']:.2f} ```", inline=False)
    embed.add_field(name="📊 Total Gasto", value=f"R$ {wallet['total_spent']:.2f}", inline=True)
    embed.add_field(name="📥 Total Depositado", value=f"R$ {wallet['total_deposited']:.2f}", inline=True)
    await ctx.respond(embed=embed, view=WalletMainView(ctx.author.id))

@bot.slash_command(name="depositar", description="Adicione saldo à sua carteira")
async def depositar(ctx):
    await ctx.send_modal(DepositModal())

@bot.slash_command(name="saldo", description="Verifica seu saldo rapidamente")
async def saldo(ctx):
    wallet = get_wallet(ctx.author.id)
    await ctx.respond(f"💰 Seu saldo atual é: **R$ {wallet['balance']:.2f}**", ephemeral=True)

# --- Evento de Interação Global (Para Aprovação de Depósitos) ---
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.application_command:
        await bot.process_application_commands(interaction)
        return

    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id", "")
        
        if custom_id.startswith("dep_app_"):
            await interaction.response.defer(ephemeral=True)
            txid = custom_id.replace("dep_app_", "")
            if txid in DEPOSITOS_PENDENTES:
                dep = DEPOSITOS_PENDENTES.pop(txid)
                save_json(PENDING_DEPOSITS_FILE, DEPOSITOS_PENDENTES)
                
                new_balance = update_balance(dep["user_id"], dep["value"])
                
                # Notificar Usuário
                try:
                    user = await bot.fetch_user(dep["user_id"])
                    await user.send(f"✅ Seu depósito de **R$ {dep['value']:.2f}** foi aprovado! Novo saldo: **R$ {new_balance:.2f}**")
                except: pass
                
                await interaction.followup.send_message(f"✅ Depósito de R$ {dep['value']:.2f} aprovado para <@{dep['user_id']}>.", ephemeral=True)
                await interaction.message.edit(content=f"✅ Depósito Aprovado por <@{interaction.user.id}>", view=None)
            else:
                await interaction.followup.send_message("❌ Depósito não encontrado ou já processado.", ephemeral=True)

        elif custom_id.startswith("dep_rej_"):
            await interaction.response.defer(ephemeral=True)
            txid = custom_id.replace("dep_rej_", "")
            if txid in DEPOSITOS_PENDENTES:
                dep = DEPOSITOS_PENDENTES.pop(txid)
                save_json(PENDING_DEPOSITS_FILE, DEPOSITOS_PENDENTES)
                
                try:
                    user = await bot.fetch_user(dep["user_id"])
                    await user.send(f"❌ Seu depósito de **R$ {dep['value']:.2f}** foi recusado pelo administrador.")
                except: pass
                
                await interaction.followup.send_message(f"❌ Depósito de R$ {dep['value']:.2f} recusado.", ephemeral=True)
                await interaction.message.edit(content=f"❌ Depósito Recusado por <@{interaction.user.id}>", view=None)
            else:
                await interaction.followup.send_message("❌ Depósito não encontrado ou já processado.", ephemeral=True)

# Registro de Views Persistentes
@bot.event
async def on_ready():
    print(f"Bot com Carteira online como {bot.user}")
    # Aqui você adicionaria views persistentes se necessário

if DISCORD_BOT_TOKEN:
    bot.run(DISCORD_BOT_TOKEN)
