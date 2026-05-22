import discord
from discord.ui import Button, View, Modal, TextInput, Select
import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
import asyncio

# --- CÓDIGO PARA MANTER ONLINE NO RENDER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot de Vendas Online")

def run_health_check():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_health_check, daemon=True).start()
# -------------------------------------------

load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
PIX_KEY = os.getenv("PIX_KEY") # Sua chave PIX
ADMIN_CHANNEL_ID = int(os.getenv("ADMIN_CHANNEL_ID")) # ID do canal para notificações de admin

# Arquivo para armazenar produtos (nome, preço, descrição) e seus estoques (arquivos .txt)
PRODUCTS_FILE = "products.json"

def load_products():
    if os.path.exists(PRODUCTS_FILE):
        with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_products(products):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=4, ensure_ascii=False)

# Carrega os produtos existentes
PRODUCTS = load_products()

# Configuração do bot do Discord
intents = discord.Intents.default()
intents.message_content = True
intents.members = True # Para interações com membros, se necessário
bot = discord.Bot(intents=intents)

# --- Funções de Estoque --- #

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
        account = stock.pop(0) # Pega a primeira conta
        save_stock(product_id, stock) # Salva o estoque atualizado
        return account
    return None

# --- Classes de Modais e Views --- #

# Modal para adicionar/editar produtos
class ProductModal(Modal):
    def __init__(self, product_id=None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="Adicionar/Editar Produto")
        self.product_id = product_id

        self.add_item(TextInput(label="Nome do Produto", placeholder="Ex: Conta de Fortnite", required=True))
        self.add_item(TextInput(label="Descrição", placeholder="Conta com skins raras...", style=discord.InputTextStyle.long, required=True))
        self.add_item(TextInput(label="Preço (R$)", placeholder="Ex: 49.99", required=True))

        if product_id and product_id in PRODUCTS:
            product = PRODUCTS[product_id]
            self.children[0].default_value = product["name"]
            self.children[1].default_value = product["description"]
            self.children[2].default_value = str(product["price"])

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        name = self.children[0].value
        description = self.children[1].value
        try:
            price = float(self.children[2].value)
        except ValueError:
            await interaction.followup.send_message("❌ Preço inválido. Use números.", ephemeral=True)
            return

        if self.product_id:
            product_id = self.product_id
        else:
            product_id = name.lower().replace(" ", "-").replace("ç", "c").replace("ã", "a").replace("õ", "o").replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
            i = 1
            original_product_id = product_id
            while product_id in PRODUCTS:
                product_id = f"{original_product_id}-{i}"
                i += 1

        PRODUCTS[product_id] = {
            "name": name,
            "description": description,
            "price": price
        }
        save_products(PRODUCTS)
        await interaction.followup.send_message(f"✅ Produto **{name}** salvo com sucesso! Estoque inicial é 0. Use o botão \'Gerenciar Estoque\' para adicionar contas.", ephemeral=True)

# Modal para remover produtos
class RemoveProductModal(Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="Remover Produto")
        self.add_item(TextInput(label="ID do Produto", placeholder="Ex: conta-de-fortnite", required=True))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        product_id = self.children[0].value.lower()
        if product_id in PRODUCTS:
            del PRODUCTS[product_id]
            stock_path = get_stock_file_path(product_id)
            if os.path.exists(stock_path):
                os.remove(stock_path)
            save_products(PRODUCTS)
            await interaction.followup.send_message(f"✅ Produto com ID **{product_id}** e seu estoque removidos com sucesso!", ephemeral=True)
        else:
            await interaction.followup.send_message(f"❌ Produto com ID **{product_id}** não encontrado.", ephemeral=True)

# Modal para adicionar estoque (contas)
class AddStockModal(Modal):
    def __init__(self, product_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title=f"Adicionar Contas para {PRODUCTS[product_id]["name"]}")
        self.product_id = product_id
        self.add_item(TextInput(label="Contas (uma por linha)", placeholder="login:senha\nlogin2:senha2", style=discord.InputTextStyle.long, required=True))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        new_accounts = [line.strip() for line in self.children[0].value.split("\n") if line.strip()]
        current_stock = load_stock(self.product_id)
        updated_stock = current_stock + new_accounts
        save_stock(self.product_id, updated_stock)
        await interaction.followup.send_message(f"✅ {len(new_accounts)} contas adicionadas para **{PRODUCTS[self.product_id]["name"]}**! Estoque total: {len(updated_stock)}.", ephemeral=True)

# View para gerenciar estoque
class StockManagementView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="➕ Adicionar Contas", style=discord.ButtonStyle.success, custom_id="add_accounts")
    async def add_accounts_callback(self, button: Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not PRODUCTS:
            await interaction.followup.send_message("Nenhum produto cadastrado para adicionar estoque.", ephemeral=True)
            return
        
        options = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
        if not options:
            await interaction.followup.send_message("Nenhum produto disponível para adicionar estoque.", ephemeral=True)
            return

        select = Select(placeholder="Escolha o produto para adicionar contas...", options=options, custom_id="select_product_for_stock")
        async def select_callback(interaction: discord.Interaction):
            selected_product_id = select.values[0]
            await interaction.response.send_modal(AddStockModal(selected_product_id))
        select.callback = select_callback
        
        view = View(timeout=60)
        view.add_item(select)
        await interaction.followup.send_message("Selecione o produto:", view=view, ephemeral=True)

    @discord.ui.button(label="📊 Ver Estoque", style=discord.ButtonStyle.primary, custom_id="view_stock")
    async def view_stock_callback(self, button: Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not PRODUCTS:
            await interaction.followup.send_message("Nenhum produto cadastrado.", ephemeral=True)
            return
        
        embed = discord.Embed(title="📊 Estoque Atual", color=discord.Color.orange())
        for pid, product in PRODUCTS.items():
            stock_count = get_available_stock_count(pid)
            embed.add_field(name=product["name"], value=f"Disponível: {stock_count}", inline=True)
        await interaction.followup.send_message(embed=embed, ephemeral=True)

# View para aprovação de vendas (Admin)
class ApprovalView(View):
    def __init__(self, buyer_id, product_id, product_name, price, original_message_id):
        super().__init__(timeout=300) # 5 minutos para aprovar/recusar
        self.buyer_id = buyer_id
        self.product_id = product_id
        self.product_name = product_name
        self.price = price
        self.original_message_id = original_message_id

    @discord.ui.button(label="✅ Aprovar Venda", style=discord.ButtonStyle.success, custom_id="approve_sale")
    async def approve_sale_callback(self, button: Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # Apenas admins podem aprovar (verificação básica)
        if interaction.user.id != bot.owner_id and interaction.user.id not in [bot.owner_id]: # Adicione IDs de admins aqui
            await interaction.followup.send_message("❌ Você não tem permissão para aprovar vendas.", ephemeral=True)
            return

        account = get_one_account_from_stock(self.product_id)
        if account:
            try:
                buyer = await bot.fetch_user(self.buyer_id)
                await buyer.send(f"✅ Sua compra de **{self.product_name}** foi aprovada!\nSua conta: ||{account}||")
                await buyer.send("Por favor, teste sua conta e nos avise se tiver qualquer problema.")
                await interaction.followup.send_message(f"✅ Venda de **{self.product_name}** para <@{self.buyer_id}> aprovada e conta entregue!", ephemeral=False)
                # Edita a mensagem original para indicar que foi aprovada
                original_message = await interaction.channel.fetch_message(self.original_message_id)
                await original_message.edit(content=f"✅ Venda Aprovada para <@{self.buyer_id}>: **{self.product_name}** (R${self.price:.2f})", view=None)
            except discord.Forbidden:
                await interaction.followup.send_message(f"❌ Não foi possível enviar DM para <@{self.buyer_id}>. A conta **{account}** foi removida do estoque. Por favor, entre em contato com o comprador manualmente.", ephemeral=False)
                original_message = await interaction.channel.fetch_message(self.original_message_id)
                await original_message.edit(content=f"❌ Venda Aprovada (DM Bloqueada) para <@{self.buyer_id}>: **{self.product_name}** (R${self.price:.2f})", view=None)
            except Exception as e:
                await interaction.followup.send_message(f"❌ Erro ao entregar a conta: {e}. A conta **{account}** foi removida do estoque. Por favor, entre em contato com o comprador manualmente.", ephemeral=False)
                original_message = await interaction.channel.fetch_message(self.original_message_id)
                await original_message.edit(content=f"❌ Venda Aprovada (Erro na Entrega) para <@{self.buyer_id}>: **{self.product_name}** (R${self.price:.2f})", view=None)
        else:
            await interaction.followup.send_message(f"❌ Não há contas disponíveis no estoque para **{self.product_name}**. Venda não aprovada.", ephemeral=False)
            original_message = await interaction.channel.fetch_message(self.original_message_id)
            await original_message.edit(content=f"❌ Venda Recusada (Estoque Vazio) para <@{self.buyer_id}>: **{self.product_name}** (R${self.price:.2f})", view=None)
        self.stop()

    @discord.ui.button(label="❌ Recusar Venda", style=discord.ButtonStyle.danger, custom_id="deny_sale")
    async def deny_sale_callback(self, button: Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # Apenas admins podem recusar
        if interaction.user.id != bot.owner_id and interaction.user.id not in [bot.owner_id]: # Adicione IDs de admins aqui
            await interaction.followup.send_message("❌ Você não tem permissão para recusar vendas.", ephemeral=True)
            return

        buyer = await bot.fetch_user(self.buyer_id)
        await buyer.send(f"❌ Sua compra de **{self.product_name}** foi recusada. Por favor, entre em contato com o suporte.")
        await interaction.followup.send_message(f"❌ Venda de **{self.product_name}** para <@{self.buyer_id}> recusada.", ephemeral=False)
        original_message = await interaction.channel.fetch_message(self.original_message_id)
        await original_message.edit(content=f"❌ Venda Recusada para <@{self.buyer_id}>: **{self.product_name}** (R${self.price:.2f})", view=None)
        self.stop()

# View para o menu principal de vendas
class SalesMainView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🛒 Ver Produtos", style=discord.ButtonStyle.primary, custom_id="view_products")
    async def view_products_callback(self, button: Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not PRODUCTS:
            await interaction.followup.send_message("Nenhum produto cadastrado ainda.", ephemeral=True)
            return

        embed = discord.Embed(title="🛍️ Nossas Contas de Jogos", color=discord.Color.blue())
        for pid, product in PRODUCTS.items():
            stock_count = get_available_stock_count(pid)
            embed.add_field(name=f"{product["name"]} - R${product["price"]:.2f}", 
                            value=f"{product["description"]}\nEstoque: {stock_count}", 
                            inline=False)
        await interaction.followup.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="💰 Comprar Agora", style=discord.ButtonStyle.green, custom_id="buy_product")
    async def buy_product_callback(self, button: Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not PRODUCTS or all(get_available_stock_count(pid) == 0 for pid in PRODUCTS):
            await interaction.followup.send_message("Nenhum produto disponível para compra no momento.", ephemeral=True)
            return
        
        options = []
        for pid, product in PRODUCTS.items():
            if get_available_stock_count(pid) > 0:
                options.append(discord.SelectOption(label=product["name"], description=f"R${product["price"]:.2f} - Estoque: {get_available_stock_count(pid)}", value=pid))
        
        if not options:
            await interaction.followup.send_message("Nenhum produto disponível para compra no momento.", ephemeral=True)
            return

        select = Select(placeholder="Escolha a conta que deseja comprar...", options=options, custom_id="select_product_to_buy")
        async def select_callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            selected_product_id = select.values[0]
            product = PRODUCTS[selected_product_id]
            
            if not PIX_KEY:
                await interaction.followup.send_message("❌ Chave PIX não configurada pelo administrador.", ephemeral=True)
                return

            embed = discord.Embed(title=f"💰 Compra de {product["name"]}", color=discord.Color.gold())
            embed.add_field(name="Valor", value=f"R${product["price"]:.2f}", inline=False)
            embed.add_field(name="Chave PIX", value=f"```\n{PIX_KEY}\n```", inline=False)
            embed.set_footer(text="Faça o pagamento e clique em 'Já Paguei' para notificar o vendedor.")
            
            confirm_view = View(timeout=300) # 5 minutos para confirmar pagamento
            confirm_view.add_item(Button(label="✅ Já Paguei", style=discord.ButtonStyle.success, custom_id=f"paid_{interaction.user.id}_{selected_product_id}"))

            await interaction.followup.send_message(embed=embed, view=confirm_view, ephemeral=True)

        select.callback = select_callback
        
        view = View(timeout=60)
        view.add_item(select)
        await interaction.followup.send_message("Selecione a conta que deseja comprar:", view=view, ephemeral=True)

    @discord.ui.button(label="⚙️ Gerenciar Produtos (Admin)", style=discord.ButtonStyle.secondary, custom_id="admin_products", row=2)
    async def admin_products_callback(self, button: Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # Verificação de permissão de admin (exemplo simples)
        if interaction.user.id != bot.owner_id and interaction.user.id not in [bot.owner_id]: # Adicione IDs de admins aqui
            await interaction.followup.send_message("❌ Você não tem permissão para acessar o painel de administração.", ephemeral=True)
            return

        admin_view = View(timeout=60)
        admin_view.add_item(Button(label="➕ Adicionar Produto", style=discord.ButtonStyle.success, custom_id="add_prod_admin"))
        admin_view.add_item(Button(label="➖ Remover Produto", style=discord.ButtonStyle.danger, custom_id="remove_prod_admin"))
        admin_view.add_item(Button(label="📊 Gerenciar Estoque", style=discord.ButtonStyle.primary, custom_id="manage_stock_admin"))

        async def add_prod_admin_callback(interaction: discord.Interaction):
            await interaction.response.send_modal(ProductModal())
        admin_view.children[0].callback = add_prod_admin_callback

        async def remove_prod_admin_callback(interaction: discord.Interaction):
            await interaction.response.send_modal(RemoveProductModal())
        admin_view.children[1].callback = remove_prod_admin_callback

        async def manage_stock_admin_callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send_message("Gerenciamento de Estoque:", view=StockManagementView(), ephemeral=True)
        admin_view.children[2].callback = manage_stock_admin_callback

        await interaction.followup.send_message("Painel de Administração de Produtos:", view=admin_view, ephemeral=True)

# --- Eventos do Bot --- #

@bot.event
async def on_ready():
    print(f"Bot de Vendas online como {bot.user}")
    # Adiciona as views persistentes ao iniciar o bot
    bot.add_view(SalesMainView())
    bot.add_view(StockManagementView())

@bot.slash_command(name="loja", description="Abre o menu principal da loja de vendas.")
async def sales_menu(ctx):
    await ctx.respond("Bem-vindo à nossa loja de contas! Escolha uma opção abaixo:", view=SalesMainView())

@bot.event
async def on_interaction(interaction: discord.Interaction):
    # Processa comandos de barra primeiro
    if interaction.type == discord.InteractionType.application_command:
        await bot.process_application_commands(interaction)
        return

    # Processa interações de componentes (botões/menus) que NÃO estão em Views
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id", "")
        
        if custom_id.startswith("paid_"):
            await interaction.response.defer(ephemeral=True)
            parts = custom_id.split("_")
            buyer_id = int(parts[1])
            product_id = parts[2]
            
            if not ADMIN_CHANNEL_ID:
                await interaction.followup.send_message("❌ Canal de administração não configurado. O vendedor não pode ser notificado.", ephemeral=True)
                return

            admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
            if not admin_channel:
                await interaction.followup.send_message("❌ Canal de administração não encontrado. Verifique o ID configurado.", ephemeral=True)
                return
            
            product = PRODUCTS.get(product_id)
            if not product:
                await interaction.followup.send_message("❌ Produto não encontrado no catálogo.", ephemeral=True)
                return

            # Envia notificação para o canal de admin
            embed = discord.Embed(title="🔔 Nova Venda Pendente!", color=discord.Color.orange())
            embed.add_field(name="Comprador", value=f"<@{buyer_id}> (ID: {buyer_id})", inline=False)
            embed.add_field(name="Produto", value=f"{product["name"]} (ID: {product_id})", inline=False)
            embed.add_field(name="Valor", value=f"R${product["price"]:.2f}", inline=False)
            embed.set_footer(text="Verifique o pagamento e aprove ou recuse a venda.")
            
            # Criamos a view de aprovação. Importante: ela precisa de um ID de mensagem para ser editada depois.
            # Como a mensagem de admin ainda não foi enviada, passamos 0 e atualizamos depois.
            approval_view = ApprovalView(buyer_id, product_id, product["name"], product["price"], 0)
            
            admin_message = await admin_channel.send(embed=embed, view=approval_view)
            approval_view.original_message_id = admin_message.id 

            await interaction.followup.send_message("✅ Sua notificação de pagamento foi enviada ao vendedor. Aguarde a aprovação!", ephemeral=True)

# Executa o bot com o token
if DISCORD_BOT_TOKEN:
    bot.run(DISCORD_BOT_TOKEN)
else:
    print("Erro: O token do bot do Discord não foi encontrado. Por favor, defina a variável de ambiente \'DISCORD_BOT_TOKEN\'.")
