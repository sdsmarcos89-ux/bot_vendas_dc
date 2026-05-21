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

PRODUCTS_FILE = "products.json"

def load_products():
    if os.path.exists(PRODUCTS_FILE):
        with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_products(products):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=4, ensure_ascii=False)

PRODUCTS = load_products()
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

# --- Modal para Estoque Artificial ---
class ArtificialStockModal(Modal):
    def __init__(self, product_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="Criar Estoque Artificial")
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
        await interaction.response.send_message(f"✅ Adicionado **{quantidade}** itens ao estoque de **{PRODUCTS[self.product_id]['name']}**.", ephemeral=True)

# --- Classes de Interface ---
class ProductModal(Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="Novo Produto")
        self.add_item(TextInput(label="Título", placeholder="Ex: Conta Valorant", required=True))
        self.add_item(TextInput(label="Descrição", style=discord.InputTextStyle.long, required=True))
        self.add_item(TextInput(label="Preço", placeholder="49.90", required=True))

    async def callback(self, interaction: discord.Interaction):
        name = self.children[0].value
        desc = self.children[1].value
        try: price = float(self.children[2].value.replace(",", "."))
        except: return await interaction.response.send_message("❌ Valor inválido!", ephemeral=True)
        pid = name.lower().replace(" ", "-")
        PRODUCTS[pid] = {"name": name, "description": desc, "price": price}
        save_products(PRODUCTS)
        await interaction.response.send_message(f"✅ Produto **{name}** criado!", ephemeral=True)

class AddStockModal(Modal):
    def __init__(self, product_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="Abastecer Estoque")
        self.product_id = product_id
        self.add_item(TextInput(label="Contas (uma por linha)", style=discord.InputTextStyle.long, required=True))

    async def callback(self, interaction: discord.Interaction):
        new = [line.strip() for line in self.children[0].value.split("\n") if line.strip()]
        save_stock(self.product_id, load_stock(self.product_id) + new)
        await interaction.response.send_message(f"✅ {len(new)} contas adicionadas!", ephemeral=True)

class ApprovalView(View):
    def __init__(self, buyer_id, product_id, product_name):
        super().__init__(timeout=None)
        self.buyer_id, self.product_id, self.product_name = buyer_id, product_id, product_name

    @discord.ui.button(label="✅ Aprovar", style=discord.ButtonStyle.success)
    async def approve(self, button, interaction):
        acc = get_one_account_from_stock(self.product_id)
        if acc:
            try:
                buyer = await bot.fetch_user(self.buyer_id)
                await buyer.send(f"✨ **Entrega Efetuada!**\nProduto: **{self.product_name}**\n\n🔑 **Dados:**\n`{acc}`")
                await interaction.response.send_message(f"✅ Entregue para <@{self.buyer_id}>!", ephemeral=False)
                await interaction.message.edit(view=None)
            except: await interaction.response.send_message("❌ DM fechada!", ephemeral=True)
        else: await interaction.response.send_message("❌ Sem estoque!", ephemeral=True)

    @discord.ui.button(label="❌ Recusar", style=discord.ButtonStyle.danger)
    async def deny(self, button, interaction):
        await interaction.response.send_message("❌ Venda recusada.", ephemeral=False)
        await interaction.message.edit(view=None)

class SalesMainView(View):
    def __init__(self, product_id=None):
        super().__init__(timeout=None)
        self.product_id = product_id

    @discord.ui.button(label="💳 Comprar via PIX", style=discord.ButtonStyle.green, custom_id="buy_btn")
    async def buy(self, button, interaction):
        pid = self.product_id
        if not pid:
            opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items() if get_available_stock_count(pid) > 0]
            if not opts: return await interaction.response.send_message("Sem estoque!", ephemeral=True)
            sel = Select(placeholder="Escolha o produto...", options=opts)
            async def sel_cb(i): await self.show_payment(i, sel.values[0])
            sel.callback = sel_cb
            v = View(); v.add_item(sel); return await interaction.response.send_message("Selecione:", view=v, ephemeral=True)
        await self.show_payment(interaction, pid)

    async def show_payment(self, interaction, pid):
        p = PRODUCTS[pid]
        qr = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(PIX_KEY )}"
        emb = discord.Embed(title="⚡ Pagamento", description=f"Produto: **{p['name']}**", color=0xf1c40f)
        emb.add_field(name="💰 Valor", value=f"```R$ {p['price']:.2f}```", inline=False)
        emb.add_field(name="🔑 Chave PIX", value=f"```\n{PIX_KEY}\n```", inline=False)
        emb.set_image(url=qr)
        btn = Button(label="✅ Já realizei o PIX", style=discord.ButtonStyle.success)
        async def paid_cb(i):
            chan = bot.get_channel(ADMIN_CHANNEL_ID)
            if chan:
                await chan.send(f"🚨 **VENDA PENDENTE**\n<@{i.user.id}> pagou **R${p['price']:.2f}** por **{p['name']}**.", view=ApprovalView(i.user.id, pid, p['name']))
                await i.response.send_message("✅ Notificado! Aguarde a entrega na DM.", ephemeral=True)
            else: await i.response.send_message("❌ Erro: Canal Admin não configurado.", ephemeral=True)
        btn.callback = paid_cb
        v = View(); v.add_item(btn)
        await interaction.response.send_message(embed=emb, view=v, ephemeral=True)

    @discord.ui.button(label="⚙️", style=discord.ButtonStyle.secondary, custom_id="admin_btn")
    async def admin(self, button, interaction):
        if interaction.user.id != bot.owner_id: return await interaction.response.send_message("Apenas o dono!", ephemeral=True)
        v = View()
        b1 = Button(label="➕ Novo Produto", style=discord.ButtonStyle.success)
        b1.callback = lambda i: i.response.send_modal(ProductModal())
        b2 = Button(label="📦 Estoque", style=discord.ButtonStyle.primary)
        async def b2_c(i):
            opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
            if not opts: return await i.response.send_message("Crie um produto!", ephemeral=True)
            s = Select(options=opts); s.callback = lambda i2: i2.response.send_modal(AddStockModal(s.values[0]))
            v2 = View(); v2.add_item(s); await i.response.send_message("Selecione:", view=v2, ephemeral=True)
        b2.callback = b2_c
        v.add_item(b1); v.add_item(b2)
        await interaction.response.send_message("Painel Admin:", view=v, ephemeral=True)

@bot.event
async def on_ready():
    print(f"Bot Online: {bot.user}")
    bot.add_view(SalesMainView())

@bot.slash_command(name="criarproduto", description="Envia a vitrine do primeiro produto")
async def criarproduto(ctx):
    if PRODUCTS:
        pid = list(PRODUCTS.keys())[0]
        p = PRODUCTS[pid]
        emb = discord.Embed(title=f"💎 {p['name']}", description=p['description'], color=0x2f3136)
        emb.add_field(name="💰 Valor", value=f"```R$ {p['price']:.2f}```", inline=True)
        emb.add_field(name="📦 Estoque", value=f"``` {get_available_stock_count(pid)} ```", inline=True)
        await ctx.respond(embed=emb, view=SalesMainView(pid))
    else: await ctx.respond("Loja vazia!", view=SalesMainView())

@bot.slash_command(name="produtos", description="Lista todos os produtos da loja")
async def produtos(ctx):
    if not PRODUCTS: return await ctx.respond("Nenhum produto cadastrado!", ephemeral=True)
    await ctx.defer(ephemeral=False)
    for pid, p in PRODUCTS.items():
        emb = discord.Embed(title=f"💎 {p['name']}", description=p['description'], color=0x2f3136)
        emb.add_field(name="💰 Valor", value=f"```R$ {p['price']:.2f}```", inline=True)
        emb.add_field(name="📦 Estoque", value=f"``` {get_available_stock_count(pid)} ```", inline=True)
        await ctx.channel.send(embed=emb, view=SalesMainView(pid))
    await ctx.interaction.edit_original_response(content="✅ Catálogo enviado!")

@bot.slash_command(name="estoque_artificial", description="Adiciona itens repetidos ao estoque")
async def estoque_artificial(ctx):
    if ctx.author.id != bot.owner_id: return await ctx.respond("Apenas o dono!", ephemeral=True)
    opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
    if not opts: return await ctx.respond("Crie um produto primeiro!", ephemeral=True)
    sel = Select(placeholder="Escolha o produto...", options=opts)
    async def sel_cb(i): await i.response.send_modal(ArtificialStockModal(sel.values[0]))
    sel.callback = sel_cb
    v = View(); v.add_item(sel)
    await ctx.respond("Selecione o produto:", view=v, ephemeral=True)

@bot.event
async def on_connect(): await bot.sync_commands()

def start_bot():
    while True:
        try: bot.run(DISCORD_BOT_TOKEN)
        except: time.sleep(10)

if DISCORD_BOT_TOKEN: start_bot()
