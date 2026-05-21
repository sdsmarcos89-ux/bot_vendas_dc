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
        self.add_item(TextInput(label="Texto do Item (ex: login:senha ou link)", placeholder="Cole aqui o que o cliente vai receber", required=True))
        self.add_item(TextInput(label="Quantidade de Vezes", placeholder="Ex: 100", required=True))

    async def callback(self, interaction: discord.Interaction):
        texto = self.children[0].value
        try:
            quantidade = int(self.children[1].value)
            if quantidade <= 0: raise ValueError
        except:
            return await interaction.response.send_message("❌ Quantidade inválida! Use apenas números positivos.", ephemeral=True)
        
        current_stock = load_stock(self.product_id)
        new_stock = current_stock + ([texto] * quantidade)
        save_stock(self.product_id, new_stock)
        
        await interaction.response.send_message(f"✅ Sucesso! Adicionado **{quantidade}** itens ao estoque de **{PRODUCTS[self.product_id]['name']}**.", ephemeral=True)

# --- Classes de Interface de Vendas ---
class ProductModal(Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="Configurar Novo Produto")
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
        await interaction.response.send_message(f"✅ Produto criado! ID: `{product_id}`.", ephemeral=True)

class AddStockModal(Modal):
    def __init__(self, product_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="Abastecer Estoque")
        self.product_id = product_id
        self.add_item(TextInput(label="Contas (uma por linha)", placeholder="login:senha", style=discord.InputTextStyle.long, required=True))

    async def callback(self, interaction: discord.Interaction):
        new_accounts = [line.strip() for line in self.children[0].value.split("\n") if line.strip()]
        save_stock(self.product_id, load_stock(self.product_id) + new_accounts)
        await interaction.response.send_message(f"✅ {len(new_accounts)} contas adicionadas!", ephemeral=True)

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
            except: await interaction.response.send_message("❌ DM do comprador fechada!", ephemeral=True)
        else: await interaction.response.send_message("❌ Estoque acabou!", ephemeral=True)

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
            options = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items() if get_available_stock_count(pid) > 0]
            if not options: return await interaction.response.send_message("Sem estoque!", ephemeral=True)
            select = Select(placeholder="Escolha o produto...", options=options)
            async def sel_callback(i): await self.show_payment(i, select.values[0])
            select.callback = sel_callback
            v = View(); v.add_item(select); return await interaction.response.send_message("Selecione:", view=v, ephemeral=True)
        await self.show_payment(interaction, pid)

    async def show_payment(self, interaction, pid):
        p = PRODUCTS[pid]
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(PIX_KEY )}"
        embed = discord.Embed(title="⚡ Pagamento Pendente", description=f"Comprando: **{p['name']}**", color=0xf1c40f)
        embed.add_field(name="💰 Valor", value=f"```R$ {p['price']:.2f}```", inline=False)
        embed.add_field(name="🔑 Chave PIX", value=f"```\n{PIX_KEY}\n```", inline=False)
        embed.set_image(url=qr_url)
        btn = Button(label="✅ Já realizei o PIX", style=discord.ButtonStyle.success)
        async def paid_callback(i):
            admin_chan = bot.get_channel(ADMIN_CHANNEL_ID)
            if admin_chan:
                await admin_chan.send(f"🚨 **ALERTA DE VENDA**\n<@{i.user.id}> afirma ter pago **R${p['price']:.2f}** por **{p['name']}**.", view=ApprovalView(i.user.id, pid, p['name']))
                await i.response.send_message("✅ Notificação enviada! Aguarde a conferência.", ephemeral=True)
            else: await i.response.send_message("❌ Erro: Canal Admin não configurado.", ephemeral=True)
        btn.callback = paid_callback
        v = View(); v.add_item(btn)
        await interaction.response.send_message(embed=embed, view=v, ephemeral=True)

    @discord.ui.button(label="⚙️", style=discord.ButtonStyle.secondary, custom_id="admin_btn")
    async def admin(self, button, interaction):
        if interaction.user.id != bot.owner_id: return await interaction.response.send_message("Apenas o dono!", ephemeral=True)
        v = View()
        b1 = Button(label="➕ Criar Produto", style=discord.ButtonStyle.success)
        b1.callback = lambda i: i.response.send_modal(ProductModal())
        b2 = Button(label="📦 Abastecer Estoque", style=discord.ButtonStyle.primary)
        async def b2_c(i):
            opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
            if not opts: return await i.response.send_message("Crie um produto primeiro!", ephemeral=True)
            s = Select(options=opts); s.callback = lambda i2: i2.response.send_modal(AddStockModal(s.values[0]))
            v2 = View(); v2.add_item(s); await i.response.send_message("Selecione:", view=v2, ephemeral=True)
        b2.callback = b2_c
        v.add_item(b1); v.add_item(b2)
        await interaction.response.send_message("Painel Admin:", view=v, ephemeral=True)

@bot.event
async def on_ready():
    print(f"Bot Profissional Online: {bot.user}")
    bot.add_view(SalesMainView())

@bot.slash_command(name="criarproduto", description="Envia o menu de vendas profissional")
async def criarproduto(ctx):
    if PRODUCTS:
        pid = list(PRODUCTS.keys())[0]
        p = PRODUCTS[pid]
        embed = discord.Embed(title=f"💎 {p['name']}", description=p['description'], color=0x2f3136)
        embed.add_field(name="💰 Valor", value=f"```R$ {p['price']:.2f}```", inline=True)
        embed.add_field(name="📦 Estoque", value=f"``` {get_available_stock_count(pid)} unidades ```", inline=True)
        await ctx.respond(embed=embed, view=SalesMainView(pid))
    else: await ctx.respond("Loja vazia! Use o botão ⚙️ para criar um produto.", view=SalesMainView())

@bot.slash_command(name="estoque_artificial", description="Adiciona itens repetidos ao estoque")
async def estoque_artificial(ctx):
    if ctx.author.id != bot.owner_id: return await ctx.respond("Apenas o dono!", ephemeral=True)
    if not PRODUCTS: return await ctx.respond("Crie um produto primeiro!", ephemeral=True)
    
    options = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
    select = Select(placeholder="Escolha o produto para o estoque artificial...", options=options)
    
    async def select_callback(interaction: discord.Interaction):
        await interaction.response.send_modal(ArtificialStockModal(select.values[0]))
    
    select.callback = select_callback
    view = View(); view.add_item(select)
    await ctx.respond("Selecione o produto que deseja abastecer:", view=view, ephemeral=True)

@bot.event
async def on_connect(): await bot.sync_commands()

# Função de Auto-Restart
def start_bot():
    while True:
        try:
            print("Iniciando Bot...")
            bot.run(DISCORD_BOT_TOKEN)
        except Exception as e:
            print(f"Erro: {e}. Reiniciando em 10s...")
            time.sleep(10)

if DISCORD_BOT_TOKEN:
    start_bot()
