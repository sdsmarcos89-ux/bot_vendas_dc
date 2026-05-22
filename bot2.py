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

# --- CÓDIGO PARA MANTER ONLINE NO RENDER ---
class HealthCheckHandler(BaseHTTPRequestHandler ):
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
OWNER_ID = int(os.getenv("OWNER_ID") or 0)

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

# DURAÇÕES FIXAS
PRODUCT_DURATIONS = {
    "1h": "1 Hora",
    "1d": "1 Dia",
    "1s": "1 Semana",
    "lifetime": "Lifetime"
}

# --- Funções de Estoque ---
def get_stock_file_path(product_id, duration_key):
    return f"stock_{product_id}_{duration_key}.txt"

def load_stock(product_id, duration_key):
    path = get_stock_file_path(product_id, duration_key)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f: return [line.strip() for line in f if line.strip()]
    return []

def save_stock(product_id, duration_key, stock_list):
    path = get_stock_file_path(product_id, duration_key)
    with open(path, "w", encoding="utf-8") as f:
        for item in stock_list: f.write(f"{item}\n")

def get_available_stock_count(product_id, duration_key):
    return len(load_stock(product_id, duration_key))

def get_one_account_from_stock(product_id, duration_key):
    stock = load_stock(product_id, duration_key)
    if stock:
        account = stock.pop(0)
        save_stock(product_id, duration_key, stock)
        return account
    return None

# --- Modals ---
class ProductModal(Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="💎 Criar Novo Produto")
        self.add_item(TextInput(label="Título do Produto", placeholder="Ex: Conta Valorant Bronze", required=True))
        self.add_item(TextInput(label="Descrição Detalhada", placeholder="Skins: Vandal Saqueadora...", style=discord.InputTextStyle.long, required=True))

    async def callback(self, interaction: discord.Interaction):
        name = self.children[0].value
        description = self.children[1].value
        
        product_id = name.lower().replace(" ", "-")
        if product_id in PRODUCTS: return await interaction.response.send_message("❌ Já existe um produto com este nome!", ephemeral=True)
        
        # Inicializa o produto com durações sem preço
        PRODUCTS[product_id] = {"name": name, "description": description, "durations": {}}
        for key in PRODUCT_DURATIONS.keys():
            PRODUCTS[product_id]["durations"][key] = {"price": 0.0}

        save_products(PRODUCTS)
        await interaction.response.send_message(f"✅ Produto **{name}** criado! Agora defina os preços e estoques no /painel.", ephemeral=True)

class EditProductTitleModal(Modal):
    def __init__(self, product_id, current_title, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="✏️ Editar Título")
        self.product_id = product_id
        self.add_item(TextInput(label="Novo Título", default_value=current_title, required=True))

    async def callback(self, interaction: discord.Interaction):
        new_title = self.children[0].value
        PRODUCTS[self.product_id]["name"] = new_title
        save_products(PRODUCTS)
        await interaction.response.send_message(f"✅ Título do produto **{self.product_id}** atualizado para \'{new_title}\'.", ephemeral=True)

class EditProductDescriptionModal(Modal):
    def __init__(self, product_id, current_desc, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="✏️ Editar Descrição")
        self.product_id = product_id
        self.add_item(TextInput(label="Nova Descrição", default_value=current_desc, style=discord.InputTextStyle.long, required=True))

    async def callback(self, interaction: discord.Interaction):
        new_desc = self.children[0].value
        PRODUCTS[self.product_id]["description"] = new_desc
        save_products(PRODUCTS)
        await interaction.response.send_message(f"✅ Descrição do produto **{self.product_id}** atualizada.", ephemeral=True)

class EditProductPriceModal(Modal):
    def __init__(self, product_id, duration_key, current_price, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title=f"✏️ Editar Preço ({PRODUCT_DURATIONS[duration_key]})")
        self.product_id = product_id
        self.duration_key = duration_key
        self.add_item(TextInput(label="Novo Preço (Apenas números)", default_value=str(current_price), required=True))

    async def callback(self, interaction: discord.Interaction):
        try: new_price = float(self.children[0].value.replace(",", "."))
        except: return await interaction.response.send_message("❌ Valor inválido! Use apenas números.", ephemeral=True)
        PRODUCTS[self.product_id]["durations"][self.duration_key]["price"] = new_price
        save_products(PRODUCTS)
        await interaction.response.send_message(f"✅ Preço de {PRODUCT_DURATIONS[self.duration_key]} para **{PRODUCTS[self.product_id]["name"]}** atualizado para R$ {new_price:.2f}.", ephemeral=True)

class AddStockModal(Modal):
    def __init__(self, product_id, duration_key, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title=f"📦 Abastecer Estoque ({PRODUCT_DURATIONS[duration_key]})")
        self.product_id = product_id
        self.duration_key = duration_key
        self.add_item(TextInput(label="Contas (uma por linha)", placeholder="login:senha", style=discord.InputTextStyle.long, required=True))

    async def callback(self, interaction: discord.Interaction):
        new_accounts = [line.strip() for line in self.children[0].value.split("\n") if line.strip()]
        save_stock(self.product_id, self.duration_key, load_stock(self.product_id, self.duration_key) + new_accounts)
        await interaction.response.send_message(f"✅ {len(new_accounts)} contas adicionadas ao estoque de {PRODUCT_DURATIONS[self.duration_key]} para **{PRODUCTS[self.product_id]["name"]}**!", ephemeral=True)

class ArtificialStockModal(Modal):
    def __init__(self, product_id, duration_key, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title=f"➕ Estoque Artificial ({PRODUCT_DURATIONS[duration_key]})")
        self.product_id = product_id
        self.duration_key = duration_key
        self.add_item(TextInput(label="Texto do Item", placeholder="O que o cliente vai receber (ex: link)", required=True))
        self.add_item(TextInput(label="Quantidade", placeholder="Ex: 100", required=True))

    async def callback(self, interaction: discord.Interaction):
        texto = self.children[0].value
        try:
            quantidade = int(self.children[1].value)
            if quantidade <= 0: raise ValueError
        except: return await interaction.response.send_message("❌ Quantidade inválida! Use apenas números positivos.", ephemeral=True)
        
        current_stock = load_stock(self.product_id, self.duration_key)
        new_stock = current_stock + ([texto] * quantidade)
        save_stock(self.product_id, self.duration_key, new_stock)
        
        await interaction.response.send_message(f"✅ Sucesso! Adicionado **{quantidade}** itens ao estoque de {PRODUCT_DURATIONS[self.duration_key]} para **{PRODUCTS[self.product_id]["name"]}**.", ephemeral=True)

# --- Views ---
class ApprovalView(View):
    def __init__(self, buyer_id, product_id, duration_key, product_name):
        super().__init__(timeout=None)
        self.buyer_id, self.product_id, self.duration_key, self.product_name = buyer_id, product_id, duration_key, product_name

    @discord.ui.button(label="✅ Aprovar Pagamento", style=discord.ButtonStyle.success)
    async def approve(self, button, interaction):
        if interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Apenas o dono pode aprovar vendas.", ephemeral=True)
        account = get_one_account_from_stock(self.product_id, self.duration_key)
        if account:
            try:
                buyer = await bot.fetch_user(self.buyer_id)
                await buyer.send(f"✨ **Pagamento Confirmado!**\nSua compra de **{self.product_name} ({PRODUCT_DURATIONS[self.duration_key]})** foi entregue.\n\n🔑 **Dados da Conta:**\n`{account}`")
                await interaction.response.send_message(f"✅ Venda entregue para <@{self.buyer_id}>!", ephemeral=False)
                await interaction.message.edit(view=None)
                # Log de venda
                SALES_LOG.append({"timestamp": str(datetime.now()), "buyer_id": self.buyer_id, "product_id": self.product_id, "duration": self.duration_key, "status": "approved"})
                save_sales_log(SALES_LOG)
                if LOG_CHANNEL_ID:
                    log_channel = bot.get_channel(LOG_CHANNEL_ID)
                    if log_channel: await log_channel.send(f"✅ Venda Aprovada: <@{self.buyer_id}> comprou {self.product_name} ({PRODUCT_DURATIONS[self.duration_key]})")
            except: 
                await interaction.response.send_message(f"❌ Erro ao enviar DM para <@{self.buyer_id}>. Conta: {account}", ephemeral=False)
        else: 
            await interaction.response.send_message("❌ Estoque vazio! Não foi possível entregar.", ephemeral=True)

    @discord.ui.button(label="❌ Recusar Pagamento", style=discord.ButtonStyle.danger)
    async def deny(self, button, interaction):
        if interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Apenas o dono pode recusar vendas.", ephemeral=True)
        try:
            buyer = await bot.fetch_user(self.buyer_id)
            await buyer.send(f"❌ Sua compra de **{self.product_name} ({PRODUCT_DURATIONS[self.duration_key]})** foi recusada. Entre em contato com o vendedor.")
        except: pass
        await interaction.response.send_message("❌ Venda recusada.", ephemeral=False)
        await interaction.message.edit(view=None)
        # Log de venda
        SALES_LOG.append({"timestamp": str(datetime.now()), "buyer_id": self.buyer_id, "product_id": self.product_id, "duration": self.duration_key, "status": "denied"})
        save_sales_log(SALES_LOG)
        if LOG_CHANNEL_ID:
            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if log_channel: await log_channel.send(f"❌ Venda Recusada: <@{self.buyer_id}> tentou comprar {self.product_name} ({PRODUCT_DURATIONS[self.duration_key]})")

class ProductBuyDurationSelectView(View):
    def __init__(self, product_id):
        super().__init__(timeout=None)
        self.product_id = product_id
        options = []
        for key, name in PRODUCT_DURATIONS.items():
            price = PRODUCTS[product_id]["durations"][key]["price"]
            stock_count = get_available_stock_count(product_id, key)
            if price > 0 and stock_count > 0: # Só mostra se tiver preço e estoque
                options.append(discord.SelectOption(label=f"{name} - R$ {price:.2f} ({stock_count} em estoque)", value=key))
        
        if options:
            self.add_item(Select(placeholder="Selecione a duração...", options=options, custom_id="duration_selector"))
        else:
            self.add_item(Button(label="Sem opções disponíveis", style=discord.ButtonStyle.red, disabled=True))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data.get("custom_id") == "duration_selector":
            selected_duration_key = interaction.data["values"][0]
            p = PRODUCTS[self.product_id]
            price = p["durations"][selected_duration_key]["price"]
            
            if get_available_stock_count(self.product_id, selected_duration_key) == 0:
                await interaction.response.send_message("❌ Este plano está sem estoque no momento!", ephemeral=True)
                return False

            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(PIX_KEY )}"
            embed = discord.Embed(title="⚡ Pagamento Pendente", description=f"Você está comprando: **{p["name"]} ({PRODUCT_DURATIONS[selected_duration_key]})**", color=0xf1c40f)
            embed.add_field(name="💰 Valor a pagar", value=f"```R$ {price:.2f}```", inline=False)
            embed.add_field(name="🔑 Chave PIX", value=f"```\n{PIX_KEY}\n```", inline=False)
            embed.set_image(url=qr_url)
            embed.set_footer(text="Após pagar, clique no botão abaixo para avisar o vendedor.")
            
            btn = Button(label="✅ Já realizei o PIX", style=discord.ButtonStyle.success)
            async def paid_callback(i):
                admin_chan = bot.get_channel(ADMIN_CHANNEL_ID)
                if admin_chan:
                    await admin_chan.send(f"🚨 **ALERTA DE VENDA**\nComprador: <@{i.user.id}>\nProduto: {p["name"]} ({PRODUCT_DURATIONS[selected_duration_key]}) (R${price:.2f})", view=ApprovalView(i.user.id, self.product_id, selected_duration_key, p["name"]))
                    await i.response.send_message("✅ **Notificação enviada!** Aguarde a conferência do vendedor. Sua conta chegará na DM.", ephemeral=True)
                    SALES_LOG.append({"timestamp": str(datetime.now()), "buyer_id": i.user.id, "product_id": self.product_id, "duration": selected_duration_key, "status": "pending"})
                    save_sales_log(SALES_LOG)
                    if LOG_CHANNEL_ID:
                        log_channel = bot.get_channel(LOG_CHANNEL_ID)
                        if log_channel: await log_channel.send(f"⏳ Venda Pendente: <@{i.user.id}> iniciou compra de {p["name"]} ({PRODUCT_DURATIONS[selected_duration_key]})")
                else: await i.response.send_message("❌ Erro: Canal de Admin não configurado. Contate o suporte.", ephemeral=True)
            btn.callback = paid_callback
            v = View(); v.add_item(btn)
            await interaction.response.send_message(embed=embed, view=v, ephemeral=True)
            return False # Não queremos que a interação continue para o callback padrão do Select
        return True

class ProductSelectView(View):
    def __init__(self):
        super().__init__(timeout=None)
        options = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
        self.add_item(Select(placeholder="Selecione um produto para ver detalhes...", options=options, custom_id="product_selector"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data.get("custom_id") == "product_selector":
            selected_product_id = interaction.data["values"][0]
            p = PRODUCTS[selected_product_id]
            embed = discord.Embed(title=f"💎 {p["name"]}", description=p["description"], color=0x2f3136)
            
            for key, name in PRODUCT_DURATIONS.items():
                price = p["durations"][key]["price"]
                stock_count = get_available_stock_count(selected_product_id, key)
                if price > 0 or stock_count > 0:
                    embed.add_field(name=f"**{name}**", value=f"```R$ {price:.2f} | Estoque: {stock_count}```", inline=True)

            embed.set_footer(text="🛒 Selecione a duração abaixo para comprar")
            await interaction.response.send_message(embed=embed, view=ProductBuyDurationSelectView(selected_product_id), ephemeral=False)
            return False # Não queremos que a interação continue para o callback padrão do Select
        return True

class AdminProductEditView(View):
    def __init__(self, product_id):
        super().__init__(timeout=None)
        self.product_id = product_id

    @discord.ui.button(label="✏️ Título", style=discord.ButtonStyle.secondary, custom_id="edit_title")
    async def edit_title_btn(self, button, interaction):
        p = PRODUCTS[self.product_id]
        await interaction.response.send_modal(EditProductTitleModal(self.product_id, p["name"]))

    @discord.ui.button(label="✏️ Descrição", style=discord.ButtonStyle.secondary, custom_id="edit_desc")
    async def edit_desc_btn(self, button, interaction):
        p = PRODUCTS[self.product_id]
        await interaction.response.send_modal(EditProductDescriptionModal(self.product_id, p["description"]))

    @discord.ui.button(label="✏️ Preço", style=discord.ButtonStyle.secondary, custom_id="edit_price")
    async def edit_price_btn(self, button, interaction):
        p = PRODUCTS[self.product_id]
        await interaction.response.send_modal(EditProductPriceModal(self.product_id, p["price"]))

class AdminProductEditDurationView(View):
    def __init__(self, product_id):
        super().__init__(timeout=None)
        self.product_id = product_id

    @discord.ui.button(label="✏️ 1 Hora", style=discord.ButtonStyle.secondary, custom_id="edit_price_1h", row=0)
    async def edit_price_1h_btn(self, button, interaction):
        p = PRODUCTS[self.product_id]
        await interaction.response.send_modal(EditProductPriceModal(self.product_id, "1h", p["durations"]["1h"]["price"]))

    @discord.ui.button(label="✏️ 1 Dia", style=discord.ButtonStyle.secondary, custom_id="edit_price_1d", row=0)
    async def edit_price_1d_btn(self, button, interaction):
        p = PRODUCTS[self.product_id]
        await interaction.response.send_modal(EditProductPriceModal(self.product_id, "1d", p["durations"]["1d"]["price"]))

    @discord.ui.button(label="✏️ 1 Semana", style=discord.ButtonStyle.secondary, custom_id="edit_price_1s", row=1)
    async def edit_price_1s_btn(self, button, interaction):
        p = PRODUCTS[self.product_id]
        await interaction.response.send_modal(EditProductPriceModal(self.product_id, "1s", p["durations"]["1s"]["price"]))

    @discord.ui.button(label="✏️ Lifetime", style=discord.ButtonStyle.secondary, custom_id="edit_price_lifetime", row=1)
    async def edit_price_lifetime_btn(self, button, interaction):
        p = PRODUCTS[self.product_id]
        await interaction.response.send_modal(EditProductPriceModal(self.product_id, "lifetime", p["durations"]["lifetime"]["price"]))

class AdminProductStockDurationSelectView(View):
    def __init__(self, product_id, modal_class):
        super().__init__(timeout=None)
        self.product_id = product_id
        self.modal_class = modal_class
        options = []
        for key, name in PRODUCT_DURATIONS.items():
            options.append(discord.SelectOption(label=f"{name} ({get_available_stock_count(product_id, key)} em estoque)", value=key))
        
        self.add_item(Select(placeholder="Selecione a duração...", options=options, custom_id="stock_duration_selector"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data.get("custom_id") == "stock_duration_selector":
            selected_duration_key = interaction.data["values"][0]
            await interaction.response.send_modal(self.modal_class(self.product_id, selected_duration_key))
            return False
        return True

class AdminPanelMainView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="➕ Criar Produto", style=discord.ButtonStyle.success, row=0)
    async def create_btn(self, b, i): await i.response.send_modal(ProductModal())

    @discord.ui.button(label="✏️ Editar Produto", style=discord.ButtonStyle.secondary, row=0)
    async def edit_product_btn(self, button, interaction):
        opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
        if not opts: return await interaction.response.send_message("Nenhum produto para editar!", ephemeral=True)
        select = Select(placeholder="Escolha o produto para editar...", options=opts)
        async def sel_cb(i):
            selected_pid = select.values[0]
            await i.response.send_message(f"Editando **{PRODUCTS[selected_pid]["name"]}**:", view=AdminProductEditDurationView(selected_pid), ephemeral=True)
        select.callback = sel_cb
        view = View(); view.add_item(select)
        await interaction.response.send_message("Selecione o produto para editar preços:", view=view, ephemeral=True)

    @discord.ui.button(label="📦 Abastecer Estoque", style=discord.ButtonStyle.primary, row=1)
    async def stock_btn(self, b, i):
        opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
        if not opts: return await i.response.send_message("Crie um produto!", ephemeral=True)
        select = Select(placeholder="Selecione o produto...", options=opts)
        async def sel_cb(i):
            selected_pid = select.values[0]
            await i.response.send_message(f"Abastecer estoque de **{PRODUCTS[selected_pid]["name"]}**:", view=AdminProductStockDurationSelectView(selected_pid, AddStockModal), ephemeral=True)
        select.callback = sel_cb
        v = View(); v.add_item(select)
        await interaction.response.send_message("Selecione o produto para abastecer:", view=v, ephemeral=True)

    @discord.ui.button(label="➕ Estoque Artificial", style=discord.ButtonStyle.blurple, row=1)
    async def art_btn(self, b, i):
        opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
        if not opts: return await interaction.response.send_message("Crie um produto!", ephemeral=True)
        select = Select(placeholder="Selecione o produto...", options=opts)
        async def sel_cb(i):
            selected_pid = select.values[0]
            await i.response.send_message(f"Estoque artificial para **{PRODUCTS[selected_pid]["name"]}**:", view=AdminProductStockDurationSelectView(selected_pid, ArtificialStockModal), ephemeral=True)
        select.callback = sel_cb
        v = View(); v.add_item(select)
        await interaction.response.send_message("Selecione o produto para estoque artificial:", view=v, ephemeral=True)

    @discord.ui.button(label="🗑️ Excluir Produto", style=discord.ButtonStyle.danger, row=2)
    async def del_btn(self, b, i):
        opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
        if not opts: return await i.response.send_message("Nada para excluir!", ephemeral=True)
        sel = Select(options=opts)
        async def del_cb(i2):
            pid = sel.values[0]
            del PRODUCTS[pid]
            save_products(PRODUCTS)
            # Deletar todos os arquivos de estoque associados
            for key in PRODUCT_DURATIONS.keys():
                stock_path = get_stock_file_path(pid, key)
                if os.path.exists(stock_path): os.remove(stock_path)
            await i2.response.send_message(f"✅ Produto **{pid}** e seus estoques excluídos!", ephemeral=True)
        sel.callback = del_cb
        v = View(); v.add_item(sel); await i.response.send_message("Excluir qual?", view=v, ephemeral=True)

    @discord.ui.button(label="📊 Logs de Vendas", style=discord.ButtonStyle.secondary, row=2)
    async def log_btn(self, b, i):
        if not SALES_LOG: return await i.response.send_message("Sem logs.", ephemeral=True)
        emb = discord.Embed(title="📊 Últimas Vendas", color=0x2f3136)
        for e in reversed(SALES_LOG[-5:]):
            duration_name = PRODUCT_DURATIONS.get(e.get("duration", ""), "N/A")
            emb.add_field(name=f"{e["status"].upper()} - {e["product_id"]} ({duration_name})", value=f"Comprador: <@{e["buyer_id"]}>\nData: {e["timestamp"][:16]}", inline=False)
        await i.response.send_message(embed=emb, ephemeral=True)

    @discord.ui.button(label="💾 Backup", style=discord.ButtonStyle.blurple, row=2)
    async def backup_btn(self, b, i):
        await i.response.defer(ephemeral=True)
        # Envia o products.json
        with open(PRODUCTS_FILE, "rb") as f:
            await i.followup.send("📦 Aqui está o backup dos seus produtos. Salve este arquivo no seu GitHub para não perder nada!", file=discord.File(f, "products.json"), ephemeral=True)
        
        # Envia os arquivos de estoque
        for pid in PRODUCTS:
            for key in PRODUCT_DURATIONS.keys():
                path = get_stock_file_path(pid, key)
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        await i.followup.send(file=discord.File(f, os.path.basename(path)), ephemeral=True)
        await i.followup.send("✅ Backup completo enviado!", ephemeral=True)

@bot.event
async def on_ready():
    print(f"Bot Online: {bot.user}")

# --- Comandos de Barra ---
@bot.slash_command(name="definirproduto", description="Envia a vitrine de um produto específico no canal")
async def definirproduto(ctx, produto: discord.Option(str, "Escolha o produto", autocomplete=lambda ctx: [p["name"] for p in PRODUCTS.values()])):
    if not PRODUCTS: return await ctx.respond("Nenhum produto cadastrado! Use /painel para criar um.", ephemeral=True)
    
    product_id = None
    for pid, p_data in PRODUCTS.items():
        if p_data["name"] == produto:
            product_id = pid
            break

    if not product_id: return await ctx.respond("Produto não encontrado!", ephemeral=True)

    p = PRODUCTS[product_id]
    embed = discord.Embed(title=f"💎 {p["name"]}", description=p["description"], color=0x2f3136)
    
    # Adiciona os campos de duração e estoque
    for key, name in PRODUCT_DURATIONS.items():
        price = p["durations"][key]["price"]
        stock_count = get_available_stock_count(product_id, key)
        if price > 0 or stock_count > 0: # Só mostra se tiver preço ou estoque
            embed.add_field(name=f"**{name}**", value=f"```R$ {price:.2f} | Estoque: {stock_count}```", inline=True)

    embed.set_footer(text="🛒 Selecione a duração abaixo para comprar")
    await ctx.respond(embed=embed, view=ProductBuyDurationSelectView(product_id))

@bot.slash_command(name="produtos", description="Mostra todos os produtos da loja com opções de seleção")
async def produtos(ctx):
    if not PRODUCTS: return await ctx.respond("Nenhum produto cadastrado! Use /painel para criar um.", ephemeral=True)
    await ctx.respond("Selecione um produto para ver os detalhes:", view=ProductSelectView(), ephemeral=False)

@bot.slash_command(name="estoque_artificial", description="Adiciona itens repetidos ao estoque")
async def estoque_artificial(ctx):
    if ctx.author.id != OWNER_ID: return await ctx.respond("❌ Apenas o dono pode usar este comando.", ephemeral=True)
    opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
    if not opts: return await ctx.respond("Crie um produto primeiro!", ephemeral=True)
    select = Select(placeholder="Escolha o produto...", options=opts)
    async def sel_cb(i): await i.response.send_modal(ArtificialStockModal(select.values[0]))
    select.callback = sel_cb
    view = View(); view.add_item(select)
    await ctx.respond("Selecione o produto para estoque artificial:", view=view, ephemeral=True)

@bot.slash_command(name="painel", description="Abre o painel administrativo da loja")
async def painel(ctx):
    if ctx.author.id != OWNER_ID: return await ctx.respond(f"❌ Apenas o dono (ID: {OWNER_ID}) pode acessar o painel administrativo. Seu ID: {ctx.author.id}", ephemeral=True)
    await ctx.respond("🛠️ **Painel Administrativo da Loja**", view=AdminPanelMainView(), ephemeral=True)

@bot.slash_command(name="backup", description="Faz backup dos dados da loja")
async def backup(ctx):
    if ctx.author.id != OWNER_ID: return await ctx.respond("❌ Apenas o dono pode usar este comando.", ephemeral=True)
    
    await ctx.defer(ephemeral=True)
    # Envia o products.json
    with open(PRODUCTS_FILE, "rb") as f:
        await ctx.followup.send("📦 Aqui está o backup dos seus produtos. Salve este arquivo no seu GitHub para não perder nada!", file=discord.File(f, "products.json"), ephemeral=True)
    
    # Envia os arquivos de estoque
    for pid in PRODUCTS:
        for key in PRODUCT_DURATIONS.keys():
            path = get_stock_file_path(pid, key)
            if os.path.exists(path):
                with open(path, "rb") as f:
                    await ctx.followup.send(file=discord.File(f, os.path.basename(path)), ephemeral=True)
    await ctx.followup.send("✅ Backup completo enviado!", ephemeral=True)

@bot.event
async def on_connect(): 
    print("Sincronizando comandos...")
    await bot.sync_commands()
    print("Comandos sincronizados!")

def start_bot():
    while True:
        try:
            print("Iniciando Bot...")
            bot.run(DISCORD_BOT_TOKEN)
        except Exception as e:
            print(f"O bot caiu com o erro: {e}. Reiniciando em 10 segundos...")
            time.sleep(10)

if DISCORD_BOT_TOKEN:
    start_bot()
