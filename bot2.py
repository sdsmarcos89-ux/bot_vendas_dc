import discord
from discord.ui import Button, View, Modal, TextInput, Select
import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
import asyncio

# --- CÓDIGO PARA ENGANAR O RENDER (WEB SERVER ) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body><h1>Bot de Vendas Online!</h1></body></html>")

    def log_message(self, format, *args):
        return 

def run_health_check():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_health_check, daemon=True).start()
# --------------------------------------------------

load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
PIX_KEY = os.getenv("PIX_KEY")
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
def get_stock_file_path(product_id):
    return f"stock_{product_id}.txt"

def load_stock(product_id):
    path = get_stock_file_path(product_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    return []

def save_stock(product_id, stock_list):
    path = get_stock_file_path(product_id)
    with open(path, "w", encoding="utf-8") as f:
        for item in stock_list:
            f.write(f"{item}\n")

def get_available_stock_count(product_id):
    return len(load_stock(product_id))

def get_one_account_from_stock(product_id):
    stock = load_stock(product_id)
    if stock:
        account = stock.pop(0)
        save_stock(product_id, stock)
        return account
    return None

# --- Classes de Interface ---
class ProductModal(Modal):
    def __init__(self, product_id=None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="Adicionar/Editar Produto")
        self.product_id = product_id
        self.add_item(TextInput(label="Nome do Produto", placeholder="Ex: Conta de Fortnite", required=True))
        self.add_item(TextInput(label="Descrição", placeholder="Conta com skins raras...", style=discord.InputTextStyle.long, required=True))
        self.add_item(TextInput(label="Preço (R$)", placeholder="Ex: 49.99", required=True))

    async def callback(self, interaction: discord.Interaction):
        name = self.children[0].value
        description = self.children[1].value
        try:
            price = float(self.children[2].value)
        except ValueError:
            await interaction.response.send_message("❌ Preço inválido.", ephemeral=True)
            return
        product_id = name.lower().replace(" ", "-")
        PRODUCTS[product_id] = {"name": name, "description": description, "price": price}
        save_products(PRODUCTS)
        await interaction.response.send_message(f"✅ Produto **{name}** salvo!", ephemeral=True)

class AddStockModal(Modal):
    def __init__(self, product_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="Adicionar Contas")
        self.product_id = product_id
        self.add_item(TextInput(label="Contas (uma por linha)", placeholder="login:senha", style=discord.InputTextStyle.long, required=True))

    async def callback(self, interaction: discord.Interaction):
        new_accounts = [line.strip() for line in self.children[0].value.split("\n") if line.strip()]
        save_stock(self.product_id, load_stock(self.product_id) + new_accounts)
        await interaction.response.send_message(f"✅ {len(new_accounts)} contas adicionadas!", ephemeral=True)

class ApprovalView(View):
    def __init__(self, buyer_id, product_id, product_name, price):
        super().__init__(timeout=None)
        self.buyer_id = buyer_id
        self.product_id = product_id
        self.product_name = product_name
        self.price = price

    @discord.ui.button(label="✅ Aprovar", style=discord.ButtonStyle.success)
    async def approve(self, button, interaction):
        account = get_one_account_from_stock(self.product_id)
        if account:
            try:
                buyer = await bot.fetch_user(self.buyer_id)
                await buyer.send(f"✅ Sua compra de **{self.product_name}** foi aprovada!\nSua conta: ||{account}||")
                await interaction.response.send_message(f"✅ Venda entregue para <@{self.buyer_id}>!", ephemeral=False)
                await interaction.message.edit(view=None)
            except:
                await interaction.response.send_message(f"❌ Erro ao enviar DM.", ephemeral=False)
        else:
            await interaction.response.send_message("❌ Estoque vazio!", ephemeral=True)

    @discord.ui.button(label="❌ Recusar", style=discord.ButtonStyle.danger)
    async def deny(self, button, interaction):
        try:
            buyer = await bot.fetch_user(self.buyer_id)
            await buyer.send(f"❌ Sua compra de **{self.product_name}** foi recusada.")
        except: pass
        await interaction.response.send_message("❌ Venda recusada.", ephemeral=False)
        await interaction.message.edit(view=None)

class SalesMainView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🛒 Ver Produtos", style=discord.ButtonStyle.primary, custom_id="v_prod")
    async def view_products(self, button, interaction):
        if not PRODUCTS: return await interaction.response.send_message("Loja vazia!", ephemeral=True)
        embed = discord.Embed(title="🛍️ Catálogo de Contas", color=discord.Color.blue())
        for pid, p in PRODUCTS.items():
            embed.add_field(name=f"{p['name']} - R${p['price']:.2f}", value=f"Estoque: {get_available_stock_count(pid)}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="💰 Comprar", style=discord.ButtonStyle.green, custom_id="buy")
    async def buy(self, button, interaction):
        options = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items() if get_available_stock_count(pid) > 0]
        if not options: return await interaction.response.send_message("Sem estoque!", ephemeral=True)
        
        select = Select(placeholder="Escolha o produto...", options=options)
        async def sel_callback(interaction):
            pid = select.values[0]
            embed = discord.Embed(title="Pagamento PIX", description=f"Valor: **R${PRODUCTS[pid]['price']:.2f}**\nChave PIX: `{PIX_KEY}`", color=discord.Color.gold())
            view = View()
            btn = Button(label="✅ Já Paguei", style=discord.ButtonStyle.success)
            async def paid_callback(interaction):
                admin_chan = bot.get_channel(ADMIN_CHANNEL_ID)
                if admin_chan:
                    await admin_chan.send(f"🔔 **Venda Pendente!**\nComprador: <@{interaction.user.id}>\nProduto: {PRODUCTS[pid]['name']}", view=ApprovalView(interaction.user.id, pid, PRODUCTS[pid]['name'], PRODUCTS[pid]['price']))
                    await interaction.response.send_message("✅ Vendedor notificado! Aguarde aprovação.", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Erro: Canal Admin não configurado.", ephemeral=True)
            btn.callback = paid_callback
            view.add_item(btn)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        select.callback = sel_callback
        v = View(); v.add_item(select)
        await interaction.response.send_message("Selecione o produto:", view=v, ephemeral=True)

    @discord.ui.button(label="⚙️ Admin", style=discord.ButtonStyle.secondary, custom_id="admin")
    async def admin(self, button, interaction):
        v = View()
        b1 = Button(label="➕ Novo Produto", style=discord.ButtonStyle.success)
        b1.callback = lambda i: i.response.send_modal(ProductModal())
        b2 = Button(label="📦 Adicionar Estoque", style=discord.ButtonStyle.primary)
        async def b2_c(i):
            opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
            if not opts: return await i.response.send_message("Crie um produto primeiro!", ephemeral=True)
            s = Select(options=opts); s.callback = lambda i2: i2.response.send_modal(AddStockModal(s.values[0]))
            v2 = View(); v2.add_item(s); await i.response.send_message("Escolha o produto:", view=v2, ephemeral=True)
        b2.callback = b2_c
        v.add_item(b1); v.add_item(b2)
        await interaction.response.send_message("Painel Administrativo:", view=v, ephemeral=True)

@bot.event
async def on_ready():
    print(f"Bot online como {bot.user}")
    bot.add_view(SalesMainView())

@bot.slash_command(name="criarproduto", description="Abre o menu da loja")
async def criarproduto(ctx):
    await ctx.respond("🛒 **Menu da Loja**", view=SalesMainView())

if DISCORD_BOT_TOKEN:
    bot.run(DISCORD_BOT_TOKEN)
