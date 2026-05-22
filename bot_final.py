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
        self.wfile.write(b"<html><body><h1>Bot Profissional V3 Online!</h1></body></html>")
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

class ProductModal(Modal):
    def __init__(self, product_id=None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="💎 Criar/Editar Produto")
        self.product_id = product_id
        default_name = PRODUCTS[product_id]["name"] if product_id else ""
        default_desc = PRODUCTS[product_id]["description"] if product_id else ""
        self.add_item(TextInput(label="Título do Produto", default_value=default_name, required=True))
        self.add_item(TextInput(label="Descrição", style=discord.InputTextStyle.long, default_value=default_desc, required=True))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        name, desc = self.children[0].value, self.children[1].value
        if self.product_id:
            PRODUCTS[self.product_id]["name"], PRODUCTS[self.product_id]["description"] = name, desc
        else:
            pid = str(uuid.uuid4())[:8]
            PRODUCTS[pid] = {"name": name, "description": desc, "plans": {}}
        save_json(PRODUCTS_FILE, PRODUCTS)
        await interaction.followup.send_message(f"✅ Produto **{name}** salvo!", ephemeral=True)

class AddPlanModal(Modal):
    def __init__(self, product_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="➕ Adicionar Plano")
        self.product_id = product_id
        self.add_item(TextInput(label="Nome do Plano", required=True))
        self.add_item(TextInput(label="Preço", placeholder="29.90", required=True))
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        name = self.children[0].value
        try: price = float(self.children[1].value.replace(",", "."))
        except: return await interaction.followup.send_message("❌ Preço inválido!", ephemeral=True)
        plid = str(uuid.uuid4())[:8]
        PRODUCTS[self.product_id]["plans"][plid] = {"name": name, "price": price}
        save_json(PRODUCTS_FILE, PRODUCTS)
        await interaction.followup.send_message(f"✅ Plano \'{name}\' adicionado!", ephemeral=True)

class AddStockModal(Modal):
    def __init__(self, product_id, plan_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="📦 Abastecer Estoque")
        self.product_id, self.plan_id = product_id, plan_id
        self.add_item(TextInput(label="Contas (uma por linha)", style=discord.InputTextStyle.long, required=True))
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        new = [l.strip() for l in self.children[0].value.split("\n") if l.strip()]
        save_stock(self.product_id, self.plan_id, load_stock(self.product_id, self.plan_id) + new)
        await interaction.followup.send_message(f"✅ {len(new)} itens adicionados!", ephemeral=True)

# --- Views ---
class WalletMainView(View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="💰 Adicionar Saldo", style=discord.ButtonStyle.success, custom_id="w_dep")
    async def dep(self, b, i): await i.response.send_modal(DepositModal())
    @discord.ui.button(label="🔄 Atualizar", style=discord.ButtonStyle.secondary, custom_id="w_ref")
    async def ref(self, b, i):
        await i.response.defer(ephemeral=True)
        w = get_wallet(i.user.id)
        embed = discord.Embed(title="👤 Seu Perfil", color=discord.Color.blue())
        embed.add_field(name="💵 Saldo Atual", value=f"``` R$ {w['balance']:.2f} ```", inline=False)
        await i.followup.edit_message(message_id=i.message.id, embed=embed, view=self)

class ProductBuyPlanSelectView(View):
    def __init__(self, product_id):
        super().__init__(timeout=None)
        self.product_id = product_id
        plans = PRODUCTS[product_id]["plans"]
        options = [discord.SelectOption(label=f"{p['name']} - R$ {p['price']:.2f}", description=f"Estoque: {get_available_stock_count(product_id, plid)}", value=plid) for plid, p in plans.items()]
        if options:
            select = Select(placeholder="Escolha um plano...", options=options, custom_id=f"sel_{product_id}")
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        plan_id = interaction.data["values"][0]
        plan = PRODUCTS[self.product_id]["plans"][plan_id]
        stock_count = get_available_stock_count(self.product_id, plan_id)
        embed = discord.Embed(title=f"🛒 Confirmar Compra", description=f"Produto: **{PRODUCTS[self.product_id]['name']}**\nPlano: **{plan['name']}**\nPreço: **R$ {plan['price']:.2f}**\nEstoque: **{stock_count}**", color=discord.Color.green())
        view = View(timeout=None)
        btn = Button(label="💳 Comprar com Saldo", style=discord.ButtonStyle.green, custom_id=f"buy_{self.product_id}_{plan_id}")
        view.add_item(btn)
        await interaction.followup.send_message(embed=embed, view=view, ephemeral=True)

# --- Comandos ---
@bot.slash_command(name="perfil", description="Veja seu saldo")
async def perfil(ctx):
    w = get_wallet(ctx.author.id)
    embed = discord.Embed(title="👤 Seu Perfil", color=discord.Color.blue())
    embed.add_field(name="💵 Saldo Atual", value=f"``` R$ {w['balance']:.2f} ```", inline=False)
    await ctx.respond(embed=embed, view=WalletMainView())

@bot.slash_command(name="loja", description="Abre a loja")
async def loja(ctx):
    if not PRODUCTS: return await ctx.respond("Nenhum produto!", ephemeral=True)
    embed = discord.Embed(title="🛍️ Nossa Loja", description="Selecione um produto abaixo:", color=discord.Color.blue())
    view = View()
    options = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
    select = Select(placeholder="Selecione o produto...", options=options)
    async def sel_prod(i):
        await i.response.defer(ephemeral=True)
        pid = select.values[0]
        p = PRODUCTS[pid]
        total = get_total_product_stock_count(pid)
        emb = discord.Embed(title=f"💎 {p['name']}", description=p['description'], color=discord.Color.blue())
        emb.add_field(name="📦 Estoque", value=f"``` {total} unidades ```")
        await i.followup.send_message(embed=emb, view=ProductBuyPlanSelectView(pid), ephemeral=True)
    select.callback = sel_prod
    view.add_item(select)
    await ctx.respond(embed=embed, view=view)

@bot.slash_command(name="painel", description="Painel Admin")
async def painel(ctx):
    if ctx.author.id != OWNER_ID: return await ctx.respond("❌ Apenas o dono!", ephemeral=True)
    view = View()
    view.add_item(Button(label="➕ Criar Produto", style=discord.ButtonStyle.success, custom_id="adm_new_p"))
    view.add_item(Button(label="➕ Adicionar Plano", style=discord.ButtonStyle.primary, custom_id="adm_new_pl"))
    view.add_item(Button(label="📦 Abastecer", style=discord.ButtonStyle.secondary, custom_id="adm_stock"))
    await ctx.respond("🛠️ Painel Admin", view=view, ephemeral=True)

# --- Evento Global ---
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.application_command:
        await bot.process_application_commands(interaction)
        return
    if interaction.type == discord.InteractionType.component:
        cid = interaction.data.get("custom_id", "")
        if cid.startswith("dep_app_"):
            await interaction.response.defer(ephemeral=True)
            txid = cid.replace("dep_app_", "")
            if txid in DEPOSITOS_PENDENTES:
                dep = DEPOSITOS_PENDENTES.pop(txid)
                save_json(PENDING_DEPOSITS_FILE, DEPOSITOS_PENDENTES)
                update_balance(dep["user_id"], dep["value"])
                try:
                    u = await bot.fetch_user(dep["user_id"])
                    await u.send(f"✅ Depósito de **R$ {dep['value']:.2f}** aprovado!")
                except: pass
                await interaction.followup.send_message("✅ Aprovado!", ephemeral=True)
                await interaction.message.edit(view=None)
        elif cid.startswith("buy_"):
            await interaction.response.defer(ephemeral=True)
            _, pid, plid = cid.split("_")
            w = get_wallet(interaction.user.id)
            plan = PRODUCTS[pid]["plans"][plid]
            if w["balance"] < plan["price"]: return await interaction.followup.send_message("❌ Saldo insuficiente!", ephemeral=True)
            stock = load_stock(pid, plid)
            if not stock: return await interaction.followup.send_message("❌ Sem estoque!", ephemeral=True)
            item = stock.pop(0)
            save_stock(pid, plid, stock)
            update_balance(interaction.user.id, -plan["price"])
            try:
                await interaction.user.send(f"🎉 Compra entregue: `{item}`")
                await interaction.followup.send_message("✅ Entregue na DM!", ephemeral=True)
            except:
                await interaction.followup.send_message(f"⚠️ DM fechada! Item: `{item}`", ephemeral=True)
        elif cid == "adm_new_p": await interaction.response.send_modal(ProductModal())
        elif cid == "adm_new_pl":
            options = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
            if not options: return await interaction.response.send_message("Crie um produto primeiro!", ephemeral=True)
            v = View(); s = Select(options=options)
            async def sel(i): await i.response.send_modal(AddPlanModal(s.values[0]))
            s.callback = sel; v.add_item(s)
            await interaction.response.send_message("Selecione o produto:", view=v, ephemeral=True)
        elif cid == "adm_stock":
            options = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
            v = View(); s = Select(options=options)
            async def sel_p(i):
                pid = s.values[0]
                pl_opts = [discord.SelectOption(label=pl["name"], value=plid) for plid, pl in PRODUCTS[pid]["plans"].items()]
                v2 = View(); s2 = Select(options=pl_opts)
                async def sel_pl(i2): await i2.response.send_modal(AddStockModal(pid, s2.values[0]))
                s2.callback = sel_pl; v2.add_item(s2)
                await i.response.send_message("Selecione o plano:", view=v2, ephemeral=True)
            s.callback = sel_p; v.add_item(s)
            await interaction.response.send_message("Selecione o produto:", view=v, ephemeral=True)

@bot.event
async def on_ready(): print(f"Bot Final online como {bot.user}")

if DISCORD_BOT_TOKEN: bot.run(DISCORD_BOT_TOKEN)

