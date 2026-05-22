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
PIX_KEY = os.getenv("PIX_KEY") # Sua chave PIX para o modo manual
ADMIN_CHANNEL_ID = int(os.getenv("ADMIN_CHANNEL_ID") or 0)
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID") or 0)
OWNER_ID = int(os.getenv("OWNER_ID") or 0)

PRODUCTS_FILE = "products.json"
SALES_LOG_FILE = "sales_log.json"
PENDING_SALES_FILE = "pending_sales.json" # Para vendas pendentes de aprovação
WALLETS_FILE = "wallets.json" # Novo arquivo para carteiras
PENDING_DEPOSITS_FILE = "pending_deposits.json" # Para depósitos pendentes

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

def load_pending_sales():
    if os.path.exists(PENDING_SALES_FILE):
        if os.path.getsize(PENDING_SALES_FILE) > 0: 
            with open(PENDING_SALES_FILE, "r", encoding="utf-8") as f:
                try: return json.load(f)
                except json.JSONDecodeError: return {} 
        return {}
    return {}

def save_pending_sales(sales):
    with open(PENDING_SALES_FILE, "w", encoding="utf-8") as f:
        json.dump(sales, f, indent=4, ensure_ascii=False)

def load_wallets():
    if os.path.exists(WALLETS_FILE):
        if os.path.getsize(WALLETS_FILE) > 0: 
            with open(WALLETS_FILE, "r", encoding="utf-8") as f:
                try: return json.load(f)
                except json.JSONDecodeError: return {}
        return {}
    return {}

def save_wallets(wallets):
    with open(WALLETS_FILE, "w", encoding="utf-8") as f:
        json.dump(wallets, f, indent=4, ensure_ascii=False)

def load_pending_deposits():
    if os.path.exists(PENDING_DEPOSITS_FILE):
        if os.path.getsize(PENDING_DEPOSITS_FILE) > 0: 
            with open(PENDING_DEPOSITS_FILE, "r", encoding="utf-8") as f:
                try: return json.load(f)
                except json.JSONDecodeError: return {} 
        return {}
    return {}

def save_pending_deposits(deposits):
    with open(PENDING_DEPOSITS_FILE, "w", encoding="utf-8") as f:
        json.dump(deposits, f, indent=4, ensure_ascii=False)

PRODUCTS = load_products()
PEDIDOS_PENDENTES = load_pending_sales()
WALLETS = load_wallets()
DEPOSITOS_PENDENTES = load_pending_deposits()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = discord.Bot(intents=intents)

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

# --- Funções de Notificação ---
async def send_product_to_buyer(buyer_id, product_name, plan_name, item):
    user = await bot.fetch_user(buyer_id)
    if user:
        try:
            embed = discord.Embed(
                title=f"🎉 Sua compra foi entregue!",
                description=f"Aqui está o seu item de **{product_name} ({plan_name})**:\n```\n{item}\n```",
                color=discord.Color.green()
            )
            embed.set_footer(text="Obrigado por comprar conosco!")
            await user.send(embed=embed)
        except discord.Forbidden:
            channel = bot.get_channel(ADMIN_CHANNEL_ID)
            if channel: await channel.send(f"⚠️ Não foi possível enviar o item para o comprador <@{buyer_id}> (DM bloqueada). Item: `{item}`")

async def log_event(message, color=discord.Color.light_grey()):
    if LOG_CHANNEL_ID:
        channel = bot.get_channel(LOG_CHANNEL_ID)
        if channel:
            embed = discord.Embed(description=message, color=color, timestamp=datetime.now())
            await channel.send(embed=embed)

# --- Geração de QR Code PIX Estático (BRCode) ---
def generate_pix_brcode_payload(pix_key, value, transaction_id):
    # Formato BRCode PIX Estático (com valor)
    # Mais detalhes: https://www.bcb.gov.br/content/estabilidadefinanceira/spb_docs/ManualBRCode.pdf
    # Simplificado para chave aleatória (EVP) e valor

    # ID do Payload (00)
    payload_format_indicator = "0014"

    # Merchant Account Information (26)
    merchant_account_information = "26"
    gui = "0107br.gov.bcb.pix"
    
    # A chave PIX deve ser o campo 01 dentro do 26
    merchant_account_information_data = f"01{len(pix_key):02d}{pix_key}"
    
    # Monta o campo 26 completo
    merchant_account_information_full = f"{merchant_account_information}{len(gui) + len(merchant_account_information_data) + 4:02d}{gui}{merchant_account_information_data}"

    # Merchant Category Code (52)
    merchant_category_code = "52040000"

    # Transaction Currency (53)
    transaction_currency = "5303986" # 986 = BRL

    # Transaction Amount (54)
    transaction_amount = f"54{len(f'{value:.2f}'):02d}{value:.2f}"

    # Country Code (58)
    country_code = "5802BR"

    # Merchant Name (59)
    merchant_name = "5913BOT DE VENDAS"

    # Merchant City (60)
    merchant_city = "6008BRASILIA"

    # Transaction ID (62) - Campo 05 para TXID
    transaction_id_field = f"62{len(f'05{len(transaction_id):02d}{transaction_id}'):02d}05{len(transaction_id):02d}{transaction_id}"

    # Concatena todos os campos
    payload = f"000201{merchant_account_information_full}{merchant_category_code}{transaction_currency}{transaction_amount}{country_code}{merchant_name}{merchant_city}{transaction_id_field}6304"

    # Calcula o CRC16 (Cyclic Redundancy Check)
    def crc16(data):
        poly = 0x1021
        crc = 0xFFFF
        for byte in data.encode("ascii"): # PIX payload é ASCII
            crc ^= (byte << 8)
            for _ in range(8):
                if (crc & 0x8000):
                    crc = (crc << 1) ^ poly
                else:
                    crc <<= 1
        return crc & 0xFFFF

    crc = crc16(payload)
    return f"{payload}{crc:04X}"

def generate_qr_code_image(data):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

# --- Autocomplete para Comandos ---
async def get_products_autocomplete(ctx: discord.AutocompleteContext):
    return [p["name"] for pid, p in PRODUCTS.items() if p["name"].lower().startswith(ctx.value.lower())]

async def get_plans_autocomplete(ctx: discord.AutocompleteContext):
    product_name = ctx.options.get("produto")
    if not product_name: return []
    
    product_id = None
    for pid, p in PRODUCTS.items():
        if p["name"] == product_name: product_id = pid; break
    
    if not product_id or product_id not in PRODUCTS: return []
    
    return [plan["name"] for plid, plan in PRODUCTS[product_id]["plans"].items() if plan["name"].lower().startswith(ctx.value.lower())]

# --- Modals ---
class ProductModal(Modal):
    def __init__(self, product_id=None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="💎 Criar/Editar Produto")
        self.product_id = product_id
        
        default_name = PRODUCTS[product_id]["name"] if product_id else ""
        default_desc = PRODUCTS[product_id]["description"] if product_id else ""

        self.add_item(TextInput(label="Título do Produto", placeholder="Ex: Conta Valorant Bronze", required=True, default_value=default_name))
        self.add_item(TextInput(label="Descrição Detalhada", placeholder="Skins: Vandal Saqueadora...", style=discord.InputTextStyle.long, required=True, default_value=default_desc))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        name = self.children[0].value
        description = self.children[1].value
        
        if self.product_id:
            PRODUCTS[self.product_id]["name"] = name
            PRODUCTS[self.product_id]["description"] = description
            await interaction.followup.send_message(f"✅ Produto **{name}** atualizado!", ephemeral=True)
        else:
            product_id = str(uuid.uuid4())[:8]
            PRODUCTS[product_id] = {"name": name, "description": description, "plans": {}}
            await interaction.followup.send_message(f"✅ Produto **{name}** criado! Agora adicione os planos no /painel.", ephemeral=True)
        save_products(PRODUCTS)

class AddPlanModal(Modal):
    def __init__(self, product_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="➕ Adicionar Novo Plano")
        self.product_id = product_id
        self.add_item(TextInput(label="Nome do Plano (Ex: 40 Dias)", required=True))
        self.add_item(TextInput(label="Preço do Plano", placeholder="29.90", required=True))
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        plan_name = self.children[0].value
        try: plan_price = float(self.children[1].value.replace(",", "."))
        except: return await interaction.followup.send_message("❌ Preço inválido! Use ponto para decimais (ex: 29.90).", ephemeral=True)
        plan_id = str(uuid.uuid4())[:8]
        PRODUCTS[self.product_id]["plans"][plan_id] = {"name": plan_name, "price": plan_price}
        save_products(PRODUCTS)
        await interaction.followup.send_message(f"✅ Plano \'{plan_name}\' adicionado!", ephemeral=True)

class EditPlanModal(Modal):
    def __init__(self, product_id, plan_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="✏️ Editar Plano")
        self.product_id, self.plan_id = product_id, plan_id
        plan = PRODUCTS[product_id]["plans"][plan_id]
        self.add_item(TextInput(label="Novo Nome do Plano", default_value=plan["name"], required=True))
        self.add_item(TextInput(label="Novo Preço", default_value=str(plan["price"]), required=True))
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        new_name = self.children[0].value
        try: new_price = float(self.children[1].value.replace(",", "."))
        except: return await interaction.followup.send_message("❌ Preço inválido! Use ponto para decimais (ex: 29.90).", ephemeral=True)
        PRODUCTS[self.product_id]["plans"][self.plan_id]["name"] = new_name
        PRODUCTS[self.product_id]["plans"][self.plan_id]["price"] = new_price
        save_products(PRODUCTS)
        await interaction.followup.send_message(f"✅ Plano \'{new_name}\' atualizado para R$ {new_price:.2f}.", ephemeral=True)

class AddStockModal(Modal):
    def __init__(self, product_id, plan_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title=f"📦 Abastecer Estoque")
        self.product_id, self.plan_id = product_id, plan_id
        self.add_item(TextInput(label="Contas (uma por linha)", placeholder="login:senha", style=discord.InputTextStyle.long, required=True))
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        new_accounts = [line.strip() for line in self.children[0].value.split("\n") if line.strip()]
        save_stock(self.product_id, self.plan_id, load_stock(self.product_id, self.plan_id) + new_accounts)
        await interaction.followup.send_message(f"✅ {len(new_accounts)} contas adicionadas ao plano!", ephemeral=True)

class ArtificialStockModal(Modal):
    def __init__(self, product_id, plan_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title=f"➕ Estoque Artificial")
        self.product_id, self.plan_id = product_id, plan_id
        self.add_item(TextInput(label="Texto do Item", required=True))
        self.add_item(TextInput(label="Quantidade", placeholder="Ex: 100", required=True))
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        texto = self.children[0].value
        try: quantidade = int(self.children[1].value)
        except: return await interaction.followup.send_message("❌ Quantidade inválida!", ephemeral=True)
        save_stock(self.product_id, self.plan_id, load_stock(self.product_id, self.plan_id) + ([texto] * quantidade))
        await interaction.followup.send_message(f"✅ {quantidade} itens artificiais adicionados ao plano!", ephemeral=True)

class RestoreBackupModal(Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="🔄 Restaurar Backup de Produtos")
        self.add_item(TextInput(label="Cole o conteúdo do products.json aqui", style=discord.InputTextStyle.long, required=True))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            global PRODUCTS
            PRODUCTS = json.loads(self.children[0].value)
            save_products(PRODUCTS)
            await interaction.followup.send_message("✅ Backup restaurado com sucesso!", ephemeral=True)
        except json.JSONDecodeError: await interaction.followup.send_message("❌ Conteúdo JSON inválido!", ephemeral=True)
        except Exception as e: await interaction.followup.send_message(f"❌ Erro ao restaurar: {e}", ephemeral=True)

class ConfirmPaymentModal(Modal):
    def __init__(self, order_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="✅ Confirmar Pagamento")
        self.order_id = order_id
        self.add_item(TextInput(label="Anexe o comprovante (URL ou print)", placeholder="Cole o link da imagem ou diga \'anexado\'", required=False))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        comprovante_info = self.children[0].value if self.children[0].value else "Comprovante anexado na mensagem anterior."
        
        if self.order_id not in PEDIDOS_PENDENTES:
            return await interaction.followup.send_message("❌ Pedido não encontrado ou já processado.", ephemeral=True)

        sale_info = PEDIDOS_PENDENTES[self.order_id]
        product_name = PRODUCTS[sale_info["product_id"]]["name"]
        plan_name = PRODUCTS[sale_info["product_id"]]["plans"][sale_info["plan_id"]]["name"]
        value = sale_info["value"]

        admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
        if admin_channel:
            embed = discord.Embed(
                title="🔔 NOVA VENDA PENDENTE DE APROVAÇÃO!",
                description=f"**Produto:** {product_name} - {plan_name}\n**Valor:** R$ {value:.2f}\n**Comprador:** <@{sale_info["buyer_id"]}> ({sale_info["buyer_name"]})\n**Comprovante:** {comprovante_info}",
                color=discord.Color.orange()
            )
            embed.set_footer(text=f"ID do Pedido: {self.order_id}")
            
            view = View()
            approve_btn = Button(label="✅ Aprovar e Entregar", style=discord.ButtonStyle.success, custom_id=f"approve_{self.order_id}")
            reject_btn = Button(label="❌ Recusar Venda", style=discord.ButtonStyle.danger, custom_id=f"reject_{self.order_id}")
            view.add_item(approve_btn)
            view.add_item(reject_btn)
            
            await admin_channel.send(embed=embed, view=view)
            await interaction.followup.send_message("✅ Seu comprovante foi enviado para aprovação! Aguarde a entrega do seu produto.", ephemeral=True)
        else:
            await interaction.followup.send_message("❌ Erro: Canal de administração não configurado. Contate o suporte.", ephemeral=True)

class ProductBuyPlanSelectView(View):
    def __init__(self, product_id, *args, **kwargs):
        super().__init__(*args, **kwargs, timeout=300)
        self.product_id = product_id
        product = PRODUCTS[product_id]

        options = []
        for plid, pl in product["plans"].items():
            stock_count = get_available_stock_count(product_id, plid)
            options.append(discord.SelectOption(label=f"{pl["name"]} - R$ {pl["price"]:.2f} ({stock_count} em estoque)", value=plid))
        
        if options:
            self.add_item(Select(placeholder="Escolha um plano para comprar...", options=options, custom_id="plan_selector"))
            self.add_item(Button(label="Comprar", style=discord.ButtonStyle.green, custom_id="buy_button"))
        else: 
            self.add_item(Button(label="Sem planos disponíveis", style=discord.ButtonStyle.red, disabled=True))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        await interaction.response.defer(ephemeral=True)
        if interaction.data.get("custom_id") == "plan_selector":
            # Apenas para exibir a seleção, não faz nada ainda
            return True
        elif interaction.data.get("custom_id") == "buy_button":
            selected_plan_id = None
            for component in self.children:
                if isinstance(component, Select) and component.custom_id == "plan_selector":
                    if component.values: selected_plan_id = component.values[0]
                    break
            
            if not selected_plan_id:
                await interaction.followup.send_message("❌ Por favor, selecione um plano antes de clicar em comprar.", ephemeral=True)
                return False

            product = PRODUCTS[self.product_id]
            plan = product["plans"][selected_plan_id]
            
            stock_count = get_available_stock_count(self.product_id, selected_plan_id)
            if stock_count == 0:
                await interaction.followup.send_message("❌ Este plano está sem estoque no momento!", ephemeral=True)
                return False

            # Gerar PIX Copia e Cola e QR Code
            order_id = str(uuid.uuid4())[:8]
            pix_payload = generate_pix_brcode_payload(PIX_KEY, plan["price"], order_id)
            qr_code_base64 = generate_qr_code_image(pix_payload)
            qr_code_url = f"data:image/png;base64,{qr_code_base64}"

            embed = discord.Embed(
                title=f"🛒 Finalizar Compra: {product["name"]} - {plan["name"]}",
                description=f"**Valor: R$ {plan["price"]:.2f}**\n\nEscaneie o QR Code ou use o PIX Copia e Cola para pagar.\n\n**Sua Chave PIX:** `{PIX_KEY}`",
                color=discord.Color.blue()
            )
            embed.set_image(url=qr_code_url)
            embed.add_field(name="PIX Copia e Cola", value=f"```\n{pix_payload}\n```", inline=False)
            embed.set_footer(text="Após pagar, clique em \'Já Paguei\' para enviar o comprovante.")

            view = View()
            confirm_btn = Button(label="✅ Já Paguei! (Enviar Comprovante)", style=discord.ButtonStyle.success, custom_id=f"confirm_payment_{order_id}")
            view.add_item(confirm_btn)

            # Salvar pedido pendente
            PEDIDOS_PENDENTES[order_id] = {
                "product_id": self.product_id,
                "plan_id": selected_plan_id,
                "buyer_id": interaction.user.id,
                "buyer_name": interaction.user.display_name,
                "value": plan["price"],
                "timestamp": datetime.now().isoformat(),
                "status": "AGUARDANDO_COMPROVANTE"
            }
            save_pending_sales(PEDIDOS_PENDENTES)

            await log_event(f"🔔 Nova Venda Pendente (Manual): {product["name"]} ({plan["name"]}) para {interaction.user.display_name}. Valor: R$ {plan["price"]:.2f}. Pedido ID: {order_id}", discord.Color.orange())
            await interaction.followup.send_message(embed=embed, view=view, ephemeral=True)
            return False # Não desativa o select
        return False

    async def on_timeout(self):
        # Limpar pedidos pendentes após timeout se necessário
        pass

class ProductSelectView(View):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, timeout=300)
        options = []
        for pid, p in PRODUCTS.items():
            total_stock = get_total_product_stock_count(pid)
            options.append(discord.SelectOption(label=p["name"], value=pid, description=f"Estoque: {total_stock}"))
        
        if options: self.add_item(Select(placeholder="Selecione um produto...", options=options, custom_id="product_selector"))
        else: self.add_item(Button(label="Nenhum produto cadastrado", style=discord.ButtonStyle.red, disabled=True))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        await interaction.response.defer(ephemeral=True)
        if interaction.data.get("custom_id") == "product_selector":
            product_id = interaction.data["values"][0]
            product = PRODUCTS[product_id]
            total_stock = get_total_product_stock_count(product_id)

            embed = discord.Embed(
                title=f"💎 {product["name"]}",
                description=product["description"],
                color=0x2f3136 # Cor para Dark Mode
            )
            embed.add_field(name="📦 Estoque Total", value=f"``` {total_stock} unidades ```", inline=True)
            embed.set_footer(text="🛒 Selecione o plano abaixo para comprar")
            await interaction.followup.send_message(embed=embed, view=ProductBuyPlanSelectView(product_id), ephemeral=False)
        return False

# --- COMANDOS DE BARRA ---
@bot.slash_command(name="definirproduto", description="Define a vitrine de um produto no canal")
async def definirproduto(ctx, product_id: discord.Option(str, "Escolha o produto", autocomplete=get_products_autocomplete)):
    if not PRODUCTS: return await ctx.respond("Nenhum produto cadastrado! Use /painel para criar.", ephemeral=True)
    if product_id not in PRODUCTS: return await ctx.respond("Produto não encontrado!", ephemeral=True)
    
    product = PRODUCTS[product_id]
    total_stock = get_total_product_stock_count(product_id)

    embed = discord.Embed(
        title=f"💎 {product["name"]}",
        description=product["description"],
        color=0x2f3136 # Cor para Dark Mode
    )
    embed.add_field(name="📦 Estoque Total", value=f"``` {total_stock} unidades ```", inline=True)
    embed.set_footer(text="🛒 Selecione o plano abaixo para comprar")
    await ctx.respond(embed=embed, view=ProductBuyPlanSelectView(product_id))

@bot.slash_command(name="produtos", description="Mostra todos os produtos da loja")
async def produtos(ctx):
    if not PRODUCTS: return await ctx.respond("Nenhum produto cadastrado!", ephemeral=True)
    await ctx.respond("Selecione um produto para ver os detalhes:", view=ProductSelectView(), ephemeral=False)

@bot.slash_command(name="painel", description="Abre o painel administrativo")
async def painel(ctx):
    if ctx.author.id != OWNER_ID: return await ctx.respond(f"❌ Apenas o dono pode acessar.", ephemeral=True)
    await ctx.respond("🛠️ **Painel Administrativo da Loja**", view=AdminPanelMainView(), ephemeral=True)

@bot.slash_command(name="backup", description="Faz backup dos dados")
async def backup(ctx):
    if ctx.author.id != OWNER_ID: return await ctx.respond("❌ Apenas o dono!", ephemeral=True)
    await ctx.defer(ephemeral=True)
    with open(PRODUCTS_FILE, "rb") as f:
        await ctx.followup.send("📦 Backup:", file=discord.File(f, "products.json"), ephemeral=True)
    for pid in PRODUCTS:
        for plan_id in PRODUCTS[pid]["plans"].keys():
            path = get_stock_file_path(pid, plan_id)
            if os.path.exists(path):
                with open(path, "rb") as f:
                    await ctx.followup.send(file=discord.File(f, os.path.basename(path)), ephemeral=True)
    await ctx.followup.send("✅ Backup completo enviado!", ephemeral=True)

@bot.event
async def on_connect(): 
    print("Sincronizando comandos...")
    await bot.sync_commands()
    print("Comandos sincronizados!")

# --- Handlers para botões de aprovação/recusa --- 
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id")
        if custom_id and custom_id.startswith("approve_"):
            order_id = custom_id.replace("approve_", "")
            if order_id in PEDIDOS_PENDENTES:
                sale_info = PEDIDOS_PENDENTES.pop(order_id)
                save_pending_sales(PEDIDOS_PENDENTES)

                product_id = sale_info["product_id"]
                plan_id = sale_info["plan_id"]
                buyer_id = sale_info["buyer_id"]
                buyer_name = sale_info["buyer_name"]
                product_name = PRODUCTS[product_id]["name"]
                plan_name = PRODUCTS[product_id]["plans"][plan_id]["name"]
                value = sale_info["value"]

                stock = load_stock(product_id, plan_id)
                if stock:
                    item_to_deliver = stock.pop(0)
                    save_stock(product_id, plan_id, stock)

                    sales_log = load_sales_log()
                    sales_log.append({
                        "id": order_id,
                        "timestamp": datetime.now().isoformat(),
                        "product_id": product_id,
                        "plan_id": plan_id,
                        "buyer_id": buyer_id,
                        "buyer_name": buyer_name,
                        "value": value,
                        "status": "APROVADO_MANUAL",
                        "delivered_item": item_to_deliver
                    })
                    save_sales_log(sales_log)

                    await send_product_to_buyer(buyer_id, product_name, plan_name, item_to_deliver)
                    await log_event(f"✅ Venda Aprovada (Manual): {product_name} ({plan_name}) para {buyer_name}. Item entregue. Valor: R$ {value:.2f}. Pedido ID: {order_id}", discord.Color.green())
                    await interaction.followup.send_message(f"✅ Venda Aprovada e produto entregue para <@{buyer_id}>!", ephemeral=True)
                    await interaction.message.edit(view=None) # Remove botões após aprovação
                else:
                    await log_event(f"⚠️ Erro (Manual): Pagamento aprovado para {product_name} ({plan_name}), mas estoque vazio. Notificar <@{buyer_id}>. Valor: R$ {value:.2f}. Pedido ID: {order_id}", discord.Color.red())
                    await interaction.followup.send_message(f"❌ Erro: Estoque vazio para {product_name} ({plan_name}). Notifique o comprador para reembolso.", ephemeral=True)
                    await interaction.message.edit(view=None) # Remove botões
            else:
                await interaction.response.defer(ephemeral=True)
                await interaction.followup.send_message("❌ Pedido não encontrado ou já processado.", ephemeral=True)
        
        elif custom_id and custom_id.startswith("reject_"):
            await interaction.response.defer(ephemeral=True)
            order_id = custom_id.replace("reject_", "")
            if order_id in PEDIDOS_PENDENTES:
                sale_info = PEDIDOS_PENDENTES.pop(order_id)
                save_pending_sales(PEDIDOS_PENDENTES)

                product_name = PRODUCTS[sale_info["product_id"]]["name"]
                plan_name = PRODUCTS[sale_info["product_id"]]["plans"][sale_info["plan_id"]]["name"]
                value = sale_info["value"]
                buyer_id = sale_info["buyer_id"]
                buyer_name = sale_info["buyer_name"]

                sales_log = load_sales_log()
                sales_log.append({
                    "id": order_id,
                    "timestamp": datetime.now().isoformat(),
                    "product_id": sale_info["product_id"],
                    "plan_id": sale_info["plan_id"],
                    "buyer_id": buyer_id,
                    "buyer_name": buyer_name,
                    "value": value,
                    "status": "RECUSADO_MANUAL"
                })
                save_sales_log(sales_log)

                await log_event(f"❌ Venda Recusada (Manual): {product_name} ({plan_name}) para {buyer_name}. Valor: R$ {value:.2f}. Pedido ID: {order_id}", discord.Color.red())
                await interaction.followup.send_message(f"❌ Venda recusada para <@{buyer_id}>. Notifique o comprador.", ephemeral=True)
                await interaction.message.edit(view=None) # Remove botões
            else:
                await interaction.followup.send_message("❌ Pedido não encontrado ou já processado.", ephemeral=True)
    
    # Garante que outras interações (modals, selects) ainda funcionem
    await bot.process_application_commands(interaction)

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
