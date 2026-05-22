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
PIX_KEY = "c84eccdd-893e-4d2b-9392-7a2460b0254d"
ADMIN_CHANNEL_ID = int(os.getenv("ADMIN_CHANNEL_ID") or 0)
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID") or 0)

PRODUCTS_FILE = "products.json"
SALES_LOG_FILE = "sales_log.json"

def load_products():
    if os.path.exists(PRODUCTS_FILE):
        with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_products(products):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=4, ensure_ascii=False)

def load_sales_log():
    if os.path.exists(SALES_LOG_FILE):
        with open(SALES_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_sales_log(log):
    with open(SALES_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=4, ensure_ascii=False)

PRODUCTS = load_products()
SALES_LOG = load_sales_log()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = discord.Bot(intents=intents)

# --- Funções de Estoque ---
def get_stock_file_path(product_id): return f"stock_{product_id}.txt"
def load_stock(product_id):
    path = get_stock_file_path(product_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f: return [line.strip() for line in f if line.strip()]
    return []
def save_stock(product_id, stock_list):
    path = get_stock_file_path(product_id)
    with open(path, "w", encoding="utf-8") as f:
        for item in stock_list: f.write(f"{item}\n")
def get_available_stock_count(product_id): return len(load_stock(product_id))
def get_one_account_from_stock(product_id):
    stock = load_stock(product_id)
    if stock:
        account = stock.pop(0)
        save_stock(product_id, stock)
        return account
    return None

# --- Modals ---
class ProductModal(Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="💎 Criar/Editar Produto")
        self.add_item(TextInput(label="Título do Produto", placeholder="Ex: Conta Valorant Bronze", required=True))
        self.add_item(TextInput(label="Descrição Detalhada", placeholder="Skins: Vandal Saqueadora...", style=discord.InputTextStyle.long, required=True))
        self.add_item(TextInput(label="Preço (Apenas números)", placeholder="49.90", required=True))

    async def callback(self, interaction: discord.Interaction):
        name = self.children[0].value
        description = self.children[1].value
        try: price = float(self.children[2].value.replace(",", "."))
        except: return await interaction.response.send_message("❌ Valor inválido!", ephemeral=True)
        
        product_id = name.lower().replace(" ", "-")
        PRODUCTS[product_id] = {"name": name, "description": description, "price": price}
        save_products(PRODUCTS)
        await interaction.response.send_message(f"✅ Produto **{name}** salvo!", ephemeral=True)

class AddStockModal(Modal):
    def __init__(self, product_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="📦 Abastecer Estoque")
        self.product_id = product_id
        self.add_item(TextInput(label="Contas (uma por linha)", placeholder="login:senha", style=discord.InputTextStyle.long, required=True))

    async def callback(self, interaction: discord.Interaction):
        new_accounts = [line.strip() for line in self.children[0].value.split("\n") if line.strip()]
        save_stock(self.product_id, load_stock(self.product_id) + new_accounts)
        await interaction.response.send_message(f"✅ {len(new_accounts)} contas adicionadas!", ephemeral=True)

class ArtificialStockModal(Modal):
    def __init__(self, product_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="➕ Estoque Artificial")
        self.product_id = product_id
        self.add_item(TextInput(label="Texto do Item", placeholder="O que o cliente vai receber", required=True))
        self.add_item(TextInput(label="Quantidade", placeholder="Ex: 100", required=True))

    async def callback(self, interaction: discord.Interaction):
        texto = self.children[0].value
        try:
            quantidade = int(self.children[1].value)
            if quantidade <= 0: raise ValueError
        except: return await interaction.response.send_message("❌ Quantidade inválida!", ephemeral=True)
        save_stock(self.product_id, load_stock(self.product_id) + ([texto] * quantidade))
        await interaction.response.send_message(f"✅ Adicionado **{quantidade}** itens ao estoque!", ephemeral=True)

# --- Views ---
class ApprovalView(View):
    def __init__(self, buyer_id, product_id, product_name):
        super().__init__(timeout=None)
        self.buyer_id, self.product_id, self.product_name = buyer_id, product_id, product_name

    @discord.ui.button(label="✅ Aprovar Pagamento", style=discord.ButtonStyle.success)
    async def approve(self, button, interaction):
        account = get_one_account_from_stock(self.product_id)
        if account:
            try:
                buyer = await bot.fetch_user(self.buyer_id)
                await buyer.send(f"✨ **Pagamento Confirmado!**\nSua compra de **{self.product_name}** foi entregue.\n\n🔑 **Dados da Conta:**\n`{account}`")
                await interaction.response.send_message(f"✅ Venda entregue para <@{self.buyer_id}>!", ephemeral=False)
                await interaction.message.edit(view=None)
                SALES_LOG.append({"timestamp": str(datetime.now()), "buyer_id": self.buyer_id, "product_id": self.product_id, "status": "approved"})
                save_sales_log(SALES_LOG)
                if LOG_CHANNEL_ID:
                    log_chan = bot.get_channel(LOG_CHANNEL_ID)
                    if log_chan: await log_chan.send(f"✅ Venda Aprovada: <@{self.buyer_id}> comprou {self.product_name}")
            except: await interaction.response.send_message("❌ Erro ao enviar DM.", ephemeral=False)
        else: await interaction.response.send_message("❌ Sem estoque!", ephemeral=True)

    @discord.ui.button(label="❌ Recusar", style=discord.ButtonStyle.danger)
    async def deny(self, button, interaction):
        try:
            buyer = await bot.fetch_user(self.buyer_id)
            await buyer.send(f"❌ Sua compra de **{self.product_name}** foi recusada.")
        except: pass
        await interaction.response.send_message("❌ Venda recusada.", ephemeral=False)
        await interaction.message.edit(view=None)
        SALES_LOG.append({"timestamp": str(datetime.now()), "buyer_id": self.buyer_id, "product_id": self.product_id, "status": "denied"})
        save_sales_log(SALES_LOG)

class ProductBuyView(View):
    def __init__(self, product_id):
        super().__init__(timeout=None)
        self.product_id = product_id

    @discord.ui.button(label="💳 Comprar via PIX", style=discord.ButtonStyle.green, custom_id="buy_btn")
    async def buy(self, button, interaction):
        p = PRODUCTS[self.product_id]
        if get_available_stock_count(self.product_id) == 0:
            return await interaction.response.send_message("❌ Sem estoque!", ephemeral=True)
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(PIX_KEY )}"
        embed = discord.Embed(title="⚡ Pagamento Pendente", description=f"Comprando: **{p['name']}**", color=0xf1c40f)
        embed.add_field(name="💰 Valor", value=f"```R$ {p['price']:.2f}```", inline=False)
        embed.add_field(name="🔑 Chave PIX", value=f"```\n{PIX_KEY}\n```", inline=False)
        embed.set_image(url=qr_url)
        btn = Button(label="✅ Já realizei o PIX", style=discord.ButtonStyle.success)
        async def paid_callback(i):
            admin_chan = bot.get_channel(ADMIN_CHANNEL_ID)
            if admin_chan:
                await admin_chan.send(f"🚨 **VENDA PENDENTE**\nComprador: <@{i.user.id}>\nProduto: {p['name']}", view=ApprovalView(i.user.id, self.product_id, p['name']))
                await i.response.send_message("✅ Notificado! Aguarde a conferência.", ephemeral=True)
                SALES_LOG.append({"timestamp": str(datetime.now()), "buyer_id": i.user.id, "product_id": self.product_id, "status": "pending"})
                save_sales_log(SALES_LOG)
            else: await i.response.send_message("❌ Erro: Canal Admin não configurado.", ephemeral=True)
        btn.callback = paid_callback
        v = View(); v.add_item(btn)
        await interaction.response.send_message(embed=embed, view=v, ephemeral=True)

class AdminPanelMainView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="➕ Criar Produto", style=discord.ButtonStyle.success)
    async def create_btn(self, b, i): await i.response.send_modal(ProductModal())

    @discord.ui.button(label="📦 Estoque", style=discord.ButtonStyle.primary)
    async def stock_btn(self, b, i):
        opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
        if not opts: return await i.response.send_message("Crie um produto!", ephemeral=True)
        sel = Select(options=opts); sel.callback = lambda i2: i2.response.send_modal(AddStockModal(sel.values[0]))
        v = View(); v.add_item(sel); await i.response.send_message("Selecione:", view=v, ephemeral=True)

    @discord.ui.button(label="➕ Artificial", style=discord.ButtonStyle.blurple)
    async def art_btn(self, b, i):
        opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
        if not opts: return await i.response.send_message("Crie um produto!", ephemeral=True)
        sel = Select(options=opts); sel.callback = lambda i2: i2.response.send_modal(ArtificialStockModal(sel.values[0]))
        v = View(); v.add_item(sel); await i.response.send_message("Selecione:", view=v, ephemeral=True)

    @discord.ui.button(label="🗑️ Excluir", style=discord.ButtonStyle.danger)
    async def del_btn(self, b, i):
        opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
        if not opts: return await i.response.send_message("Nada para excluir!", ephemeral=True)
        sel = Select(options=opts)
        async def del_cb(i2):
            pid = sel.values[0]
            del PRODUCTS[pid]
            save_products(PRODUCTS)
            await i2.response.send_message(f"✅ Excluído!", ephemeral=True)
        sel.callback = del_cb
        v = View(); v.add_item(sel); await i.response.send_message("Excluir qual?", view=v, ephemeral=True)

    @discord.ui.button(label="📊 Logs", style=discord.ButtonStyle.secondary)
    async def log_btn(self, b, i):
        if not SALES_LOG: return await i.response.send_message("Sem logs.", ephemeral=True)
        emb = discord.Embed(title="📊 Últimas Vendas", color=0x2f3136)
        for e in reversed(SALES_LOG[-5:]):
            emb.add_field(name=f"{e['status'].upper()} - {e['product_id']}", value=f"Comprador: <@{e['buyer_id']}>\nData: {e['timestamp'][:16]}", inline=False)
        await i.response.send_message(embed=emb, ephemeral=True)

@bot.event
async def on_ready():
    print(f"Bot Online: {bot.user}")

@bot.slash_command(name="criarproduto", description="Envia a vitrine")
async def criarproduto(ctx):
    if PRODUCTS:
        pid = list(PRODUCTS.keys())[0]
        p = PRODUCTS[pid]
        emb = discord.Embed(title=f"💎 {p['name']}", description=p['description'], color=0x2f3136)
        emb.add_field(name="💰 Valor", value=f"```R$ {p['price']:.2f}```", inline=True)
        emb.add_field(name="📦 Estoque", value=f"``` {get_available_stock_count(pid)} ```", inline=True)
        await ctx.respond(embed=emb, view=ProductBuyView(pid))
    else: await ctx.respond("Use /painel para criar produtos.", view=AdminPanelMainView())

@bot.slash_command(name="produtos", description="Catálogo completo")
async def produtos(ctx):
    if not PRODUCTS: return await ctx.respond("Vazio!", ephemeral=True)
    await ctx.defer()
    for pid, p in PRODUCTS.items():
        emb = discord.Embed(title=f"💎 {p['name']}", description=p['description'], color=0x2f3136)
        emb.add_field(name="💰 Valor", value=f"```R$ {p['price']:.2f}```", inline=True)
        emb.add_field(name="📦 Estoque", value=f"``` {get_available_stock_count(pid)} ```", inline=True)
        await ctx.channel.send(embed=emb, view=ProductBuyView(pid))
    await ctx.interaction.edit_original_response(content="✅ Enviado!")

@bot.slash_command(name="painel", description="Painel Admin")
async def painel(ctx):
    if ctx.author.id != bot.owner_id: return await ctx.respond("Apenas o dono!", ephemeral=True)
    await ctx.respond("🛠️ **Painel Administrativo**", view=AdminPanelMainView(), ephemeral=True)

@bot.event
async def on_connect(): await bot.sync_commands()

def start_bot():
    while True:
        try: bot.run(DISCORD_BOT_TOKEN)
        except: time.sleep(10)

if DISCORD_BOT_TOKEN: start_bot()
