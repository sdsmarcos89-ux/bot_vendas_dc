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

# --- Modals ---
class ProductModal(Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="💎 Criar Novo Produto")
        self.add_item(TextInput(label="Título do Produto", placeholder="Ex: Conta Valorant Bronze", required=True))
        self.add_item(TextInput(label="Descrição Detalhada", placeholder="Skins: Vandal Saqueadora...", style=discord.InputTextStyle.long, required=True))

    async def callback(self, interaction: discord.Interaction):
        name = self.children[0].value
        description = self.children[1].value
        product_id = str(uuid.uuid4())[:8]
        PRODUCTS[product_id] = {"name": name, "description": description, "plans": {}}
        save_products(PRODUCTS)
        await interaction.response.send_message(f"✅ Produto **{name}** criado! Agora adicione os planos no /painel.", ephemeral=True)

class EditProductTitleModal(Modal):
    def __init__(self, product_id, current_title, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="✏️ Editar Título")
        self.product_id = product_id
        self.add_item(TextInput(label="Novo Título", default_value=current_title, required=True))
    async def callback(self, interaction: discord.Interaction):
        new_title = self.children[0].value
        PRODUCTS[self.product_id]["name"] = new_title
        save_products(PRODUCTS)
        await interaction.response.send_message(f"✅ Título atualizado para \'{new_title}\'.", ephemeral=True)

class EditProductDescriptionModal(Modal):
    def __init__(self, product_id, current_desc, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="✏️ Editar Descrição")
        self.product_id = product_id
        self.add_item(TextInput(label="Nova Descrição", default_value=current_desc, style=discord.InputTextStyle.long, required=True))
    async def callback(self, interaction: discord.Interaction):
        new_desc = self.children[0].value
        PRODUCTS[self.product_id]["description"] = new_desc
        save_products(PRODUCTS)
        await interaction.response.send_message(f"✅ Descrição atualizada.", ephemeral=True)

class AddPlanModal(Modal):
    def __init__(self, product_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="➕ Adicionar Novo Plano")
        self.product_id = product_id
        self.add_item(TextInput(label="Nome do Plano (Ex: 40 Dias)", required=True))
        self.add_item(TextInput(label="Preço do Plano", placeholder="29.90", required=True))
    async def callback(self, interaction: discord.Interaction):
        plan_name = self.children[0].value
        try: plan_price = float(self.children[1].value.replace(",", "."))
        except: return await interaction.response.send_message("❌ Preço inválido!", ephemeral=True)
        plan_id = str(uuid.uuid4())[:8]
        PRODUCTS[self.product_id]["plans"][plan_id] = {"name": plan_name, "price": plan_price}
        save_products(PRODUCTS)
        await interaction.response.send_message(f"✅ Plano \'{plan_name}\' adicionado!", ephemeral=True)

class EditPlanNameModal(Modal):
    def __init__(self, product_id, plan_id, current_name, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="✏️ Editar Nome do Plano")
        self.product_id, self.plan_id = product_id, plan_id
        self.add_item(TextInput(label="Novo Nome do Plano", default_value=current_name, required=True))
    async def callback(self, interaction: discord.Interaction):
        new_name = self.children[0].value
        PRODUCTS[self.product_id]["plans"][self.plan_id]["name"] = new_name
        save_products(PRODUCTS)
        await interaction.response.send_message(f"✅ Nome do plano atualizado para \'{new_name}\'.", ephemeral=True)

class EditPlanPriceModal(Modal):
    def __init__(self, product_id, plan_id, current_price, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="✏️ Editar Preço do Plano")
        self.product_id, self.plan_id = product_id, plan_id
        self.add_item(TextInput(label="Novo Preço", default_value=str(current_price), required=True))
    async def callback(self, interaction: discord.Interaction):
        try: new_price = float(self.children[0].value.replace(",", "."))
        except: return await interaction.response.send_message("❌ Preço inválido!", ephemeral=True)
        PRODUCTS[self.product_id]["plans"][self.plan_id]["price"] = new_price
        save_products(PRODUCTS)
        await interaction.response.send_message(f"✅ Preço atualizado para R$ {new_price:.2f}.", ephemeral=True)

class AddStockModal(Modal):
    def __init__(self, product_id, plan_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title=f"📦 Abastecer Estoque")
        self.product_id, self.plan_id = product_id, plan_id
        self.add_item(TextInput(label="Contas (uma por linha)", placeholder="login:senha", style=discord.InputTextStyle.long, required=True))
    async def callback(self, interaction: discord.Interaction):
        new_accounts = [line.strip() for line in self.children[0].value.split("\n") if line.strip()]
        save_stock(self.product_id, self.plan_id, load_stock(self.product_id, self.plan_id) + new_accounts)
        await interaction.response.send_message(f"✅ {len(new_accounts)} contas adicionadas!", ephemeral=True)

class ArtificialStockModal(Modal):
    def __init__(self, product_id, plan_id, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title=f"➕ Estoque Artificial")
        self.product_id, self.plan_id = product_id, plan_id
        self.add_item(TextInput(label="Texto do Item", required=True))
        self.add_item(TextInput(label="Quantidade", placeholder="Ex: 100", required=True))
    async def callback(self, interaction: discord.Interaction):
        texto = self.children[0].value
        try: quantidade = int(self.children[1].value)
        except: return await interaction.response.send_message("❌ Quantidade inválida!", ephemeral=True)
        save_stock(self.product_id, self.plan_id, load_stock(self.product_id, self.plan_id) + ([texto] * quantidade))
        await interaction.response.send_message(f"✅ {quantidade} itens artificiais adicionados!", ephemeral=True)

class RestoreBackupModal(Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs, title="🔄 Restaurar Backup de Produtos")
        self.add_item(TextInput(label="Cole o conteúdo do products.json aqui", style=discord.InputTextStyle.long, required=True))

    async def callback(self, interaction: discord.Interaction):
        try:
            global PRODUCTS
            PRODUCTS = json.loads(self.children[0].value)
            save_products(PRODUCTS)
            await interaction.response.send_message("✅ Backup restaurado com sucesso!", ephemeral=True)
        except json.JSONDecodeError: await interaction.response.send_message("❌ Conteúdo JSON inválido!", ephemeral=True)
        except Exception as e: await interaction.response.send_message(f"❌ Erro ao restaurar: {e}", ephemeral=True)

# --- Views ---
class ApprovalView(View):
    def __init__(self, buyer_id, product_id, plan_id, product_name, plan_name):
        super().__init__(timeout=None)
        self.buyer_id, self.product_id, self.plan_id, self.product_name, self.plan_name = buyer_id, product_id, plan_id, product_name, plan_name
    @discord.ui.button(label="✅ Aprovar", style=discord.ButtonStyle.success)
    async def approve(self, button, interaction):
        if interaction.user.id != OWNER_ID: return await interaction.response.send_message("Apenas o dono!", ephemeral=True)
        account = get_one_account_from_stock(self.product_id, self.plan_id)
        if account:
            try:
                buyer = await bot.fetch_user(self.buyer_id)
                await buyer.send(f"✨ **Pagamento Confirmado!**\nSua compra de **{self.product_name} ({self.plan_name})** foi entregue.\n\n🔑 **Dados:** `{account}`")
                await interaction.response.send_message(f"✅ Entregue para <@{self.buyer_id}>!", ephemeral=False)
                await interaction.message.edit(view=None)
                SALES_LOG.append({"timestamp": str(datetime.now()), "buyer_id": self.buyer_id, "product_id": self.product_id, "plan_id": self.plan_id, "status": "approved"})
                save_sales_log(SALES_LOG)
            except: await interaction.response.send_message(f"❌ Erro ao enviar DM!", ephemeral=False)
        else: await interaction.response.send_message("❌ Estoque vazio!", ephemeral=True)
    @discord.ui.button(label="❌ Recusar", style=discord.ButtonStyle.danger)
    async def deny(self, button, interaction):
        if interaction.user.id != OWNER_ID: return await interaction.response.send_message("Apenas o dono!", ephemeral=True)
        await interaction.response.send_message("❌ Recusado.", ephemeral=False)
        await interaction.message.edit(view=None)

class ProductBuyPlanSelectView(View):
    def __init__(self, product_id):
        super().__init__(timeout=None)
        self.product_id = product_id
        options = []
        for plid, pl in PRODUCTS[product_id]["plans"].items():
            stock_count = get_available_stock_count(product_id, plid)
            if stock_count > 0:
                options.append(discord.SelectOption(label=f"{pl["name"]} - R$ {pl["price"]:.2f} ({stock_count} em estoque)", value=plid))
        
        if options: self.add_item(Select(placeholder="Selecione o plano...", options=options, custom_id="plan_selector"))
        else: self.add_item(Button(label="Sem planos disponíveis", style=discord.ButtonStyle.red, disabled=True))
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data.get("custom_id") == "plan_selector":
            plan_id = interaction.data["values"][0]
            p = PRODUCTS[self.product_id]
            plan = p["plans"][plan_id]
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(PIX_KEY )}"
            emb = discord.Embed(title="⚡ Pagamento PIX", description=f"Comprando: **{p["name"]} ({plan["name"]})**", color=0xf1c40f)
            emb.add_field(name="💰 Valor", value=f"```R$ {plan["price"]:.2f}```")
            emb.add_field(name="🔑 Chave", value=f"```\n{PIX_KEY}\n```", inline=False)
            emb.set_image(url=qr_url)
            btn = Button(label="✅ Já paguei", style=discord.ButtonStyle.success)
            async def paid_cb(i):
                admin = bot.get_channel(ADMIN_CHANNEL_ID)
                if admin:
                    await admin.send(f"🚨 **VENDA** de <@{i.user.id}>: {p["name"]} ({plan["name"]})", view=ApprovalView(i.user.id, self.product_id, plan_id, p["name"], plan["name"]))
                    await i.response.send_message("✅ Notificado!", ephemeral=True)
                else: await i.response.send_message("Erro no canal admin.", ephemeral=True)
            btn.callback = paid_cb
            v = View(); v.add_item(btn)
            await interaction.response.send_message(embed=emb, view=v, ephemeral=True)
            return False
        return True

class ProductSelectView(View):
    def __init__(self):
        super().__init__(timeout=None)
        options = []
        for pid, p in PRODUCTS.items():
            total_stock = get_total_product_stock_count(pid)
            if total_stock > 0:
                options.append(discord.SelectOption(label=f"{p["name"]} ({total_stock} em estoque)", value=pid))
        
        if options: self.add_item(Select(placeholder="Escolha um produto...", options=options, custom_id="prod_sel"))
        else: self.add_item(Button(label="Sem produtos disponíveis", style=discord.ButtonStyle.red, disabled=True))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data.get("custom_id") == "prod_sel":
            pid = interaction.data["values"][0]
            p = PRODUCTS[pid]
            embed = discord.Embed(title=f"💎 {p["name"]}", description=p["description"], color=0x2f3136)
            total_stock = get_total_product_stock_count(pid)
            embed.add_field(name="📦 Estoque Total", value=f"``` {total_stock} unidades ```", inline=True)
            embed.set_footer(text="🛒 Selecione o plano abaixo para comprar")
            await interaction.response.send_message(embed=embed, view=ProductBuyPlanSelectView(pid), ephemeral=False)
            return False
        return True

class AdminProductEditView(View):
    def __init__(self, product_id):
        super().__init__(timeout=None)
        self.product_id = product_id
    @discord.ui.button(label="✏️ Título", style=discord.ButtonStyle.secondary, row=0)
    async def edit_title(self, b, i): await i.response.send_modal(EditProductTitleModal(self.product_id, PRODUCTS[self.product_id]["name"]))
    @discord.ui.button(label="✏️ Descrição", style=discord.ButtonStyle.secondary, row=0)
    async def edit_desc(self, b, i): await i.response.send_modal(EditProductDescriptionModal(self.product_id, PRODUCTS[self.product_id]["description"]))
    @discord.ui.button(label="➕/✏️ Planos", style=discord.ButtonStyle.primary, row=1)
    async def manage_plans(self, b, i): await i.response.send_message(f"Gerenciar planos de **{PRODUCTS[self.product_id]["name"]}**:", view=AdminProductEditPlanView(self.product_id), ephemeral=True)

class AdminProductEditPlanView(View):
    def __init__(self, product_id):
        super().__init__(timeout=None)
        self.product_id = product_id
        opts = [discord.SelectOption(label=f"{pl["name"]} (R$ {pl["price"]:.2f})", value=plid) for plid, pl in PRODUCTS[product_id]["plans"].items()]
        if opts:
            sel = Select(placeholder="Selecione um plano para editar...", options=opts)
            async def sel_cb(i):
                plid = sel.values[0]
                pl = PRODUCTS[self.product_id]["plans"][plid]
                v = View()
                b1 = Button(label="✏️ Nome", style=discord.ButtonStyle.secondary)
                b1.callback = lambda i2: i2.response.send_modal(EditPlanNameModal(self.product_id, plid, pl["name"]))
                b2 = Button(label="✏️ Preço", style=discord.ButtonStyle.secondary)
                b2.callback = lambda i2: i2.response.send_modal(EditPlanPriceModal(self.product_id, plid, pl["price"]))
                v.add_item(b1); v.add_item(b2)
                await i.response.send_message(f"Editando plano \'{pl["name"]}\':", view=v, ephemeral=True)
            sel.callback = sel_cb
            self.add_item(sel)
    @discord.ui.button(label="➕ Adicionar Plano", style=discord.ButtonStyle.success, row=1)
    async def add_pl(self, b, i): await i.response.send_modal(AddPlanModal(self.product_id))
    @discord.ui.button(label="🗑️ Remover Plano", style=discord.ButtonStyle.danger, row=1)
    async def rem_pl(self, b, i):
        opts = [discord.SelectOption(label=pl["name"], value=plid) for plid, pl in PRODUCTS[self.product_id]["plans"].items()]
        if not opts: return await i.response.send_message("Vazio!", ephemeral=True)
        sel = Select(options=opts)
        async def sel_cb(i2):
            plid = sel.values[0]
            del PRODUCTS[self.product_id]["plans"][plid]
            save_products(PRODUCTS)
            await i2.response.send_message("✅ Removido!", ephemeral=True)
        sel.callback = sel_cb
        v = View(); v.add_item(sel); await i.response.send_message("Remover qual?", view=v, ephemeral=True)

class AdminProductStockPlanSelectView(View):
    def __init__(self, product_id, modal_class):
        super().__init__(timeout=None)
        opts = [discord.SelectOption(label=f"{pl["name"]} ({get_available_stock_count(product_id, plid)} em estoque)", value=plid) for plid, pl in PRODUCTS[product_id]["plans"].items()]
        if opts:
            sel = Select(placeholder="Escolha o plano...", options=opts)
            sel.callback = lambda i: i.response.send_modal(modal_class(product_id, sel.values[0]))
            self.add_item(sel)

class AdminPanelMainView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="➕ Criar Produto", style=discord.ButtonStyle.success, row=0)
    async def create(self, b, i): await i.response.send_modal(ProductModal())

    @discord.ui.button(label="✏️ Editar Produto", style=discord.ButtonStyle.secondary, row=0)
    async def edit(self, b, i):
        opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
        if not opts: return await i.response.send_message("Vazio!", ephemeral=True)
        sel = Select(options=opts)
        sel.callback = lambda i2: i2.response.send_message(f"Editando **{PRODUCTS[sel.values[0]]["name"]}**:", view=AdminProductEditView(sel.values[0]), ephemeral=True)
        v = View(); v.add_item(sel); await i.response.send_message("Editar qual?", view=v, ephemeral=True)

    @discord.ui.button(label="📦 Abastecer Estoque", style=discord.ButtonStyle.primary, row=1)
    async def stock(self, b, i):
        opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
        if not opts: return await i.response.send_message("Vazio!", ephemeral=True)
        sel = Select(placeholder="Selecione o produto...", options=opts)
        sel.callback = lambda i2: i2.response.send_message("Escolha o plano:", view=AdminProductStockPlanSelectView(sel.values[0], AddStockModal), ephemeral=True)
        v = View(); v.add_item(sel); await i.response.send_message("Abastecer qual?", view=v, ephemeral=True)

    @discord.ui.button(label="➕ Estoque Artificial", style=discord.ButtonStyle.blurple, row=1)
    async def art(self, b, i):
        opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
        if not opts: return await i.response.send_message("Vazio!", ephemeral=True)
        sel = Select(placeholder="Selecione o produto...", options=opts)
        sel.callback = lambda i2: i2.response.send_message("Escolha o plano:", view=AdminProductStockPlanSelectView(sel.values[0], ArtificialStockModal), ephemeral=True)
        v = View(); v.add_item(sel); await i.response.send_message("Qual produto?", view=v, ephemeral=True)

    @discord.ui.button(label="🗑️ Excluir Produto", style=discord.ButtonStyle.danger, row=2)
    async def del_p(self, b, i):
        opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
        if not opts: return await i.response.send_message("Nada para excluir!", ephemeral=True)
        sel = Select(options=opts)
        async def sel_cb(i2):
            pid_to_delete = sel.values[0]
            product_name = PRODUCTS[pid_to_delete]["name"]
            del PRODUCTS[pid_to_delete]
            save_products(PRODUCTS)
            # Remover arquivos de estoque associados
            for plan_id in PRODUCTS.get(pid_to_delete, {}).get("plans", {}).keys():
                stock_path = get_stock_file_path(pid_to_delete, plan_id)
                if os.path.exists(stock_path): os.remove(stock_path)
            await i2.response.send_message(f"✅ Produto **{product_name}** e seus estoques excluídos!", ephemeral=True)
        sel.callback = sel_cb
        v = View(); v.add_item(sel); await i.response.send_message("Excluir qual?", view=v, ephemeral=True)

    @discord.ui.button(label="📊 Logs de Vendas", style=discord.ButtonStyle.secondary, row=2)
    async def log_btn(self, b, i):
        if not SALES_LOG: return await i.response.send_message("Sem logs.", ephemeral=True)
        emb = discord.Embed(title="📊 Últimas Vendas", color=0x2f3136)
        for e in reversed(SALES_LOG[-5:]):
            plan_name = "N/A"
            if e.get("product_id") in PRODUCTS and e.get("plan_id") in PRODUCTS[e["product_id"]]["plans"]:
                plan_name = PRODUCTS[e["product_id"]]["plans"][e["plan_id"]]["name"]
            emb.add_field(name=f"{e["status"].upper()} - {e["product_id"]} ({plan_name})", value=f"Comprador: <@{e["buyer_id"]}>\nData: {e["timestamp"][:16]}", inline=False)
        await i.response.send_message(embed=emb, ephemeral=True)

    @discord.ui.button(label="💾 Backup", style=discord.ButtonStyle.blurple, row=2)
    async def backup_btn(self, b, i):
        await i.response.defer(ephemeral=True)
        with open(PRODUCTS_FILE, "rb") as f:
            await i.followup.send("📦 Backup de produtos:", file=discord.File(f, "products.json"), ephemeral=True)
        for pid in PRODUCTS:
            for plan_id in PRODUCTS[pid]["plans"].keys():
                path = get_stock_file_path(pid, plan_id)
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        await i.followup.send(file=discord.File(f, os.path.basename(path)), ephemeral=True)
        await i.followup.send("✅ Backup completo enviado!", ephemeral=True)

    @discord.ui.button(label="🔄 Restaurar Backup", style=discord.ButtonStyle.danger, row=3)
    async def restore_backup_btn(self, button, interaction):
        await interaction.response.send_modal(RestoreBackupModal())

@bot.event
async def on_ready():
    print(f"Bot Online: {bot.user}")

# --- Comandos de Barra ---
@bot.slash_command(name="definirproduto", description="Envia a vitrine de um produto específico no canal")
async def definirproduto(ctx, produto: discord.Option(str, "Escolha o produto", autocomplete=lambda ctx: [p["name"] for p in PRODUCTS.values()])):
    if not PRODUCTS: return await ctx.respond("Nenhum produto cadastrado!", ephemeral=True)
    product_id = next((pid for pid, p in PRODUCTS.items() if p["name"] == produto), None)
    if not product_id: return await ctx.respond("Produto não encontrado!", ephemeral=True)
    p = PRODUCTS[product_id]
    embed = discord.Embed(title=f"💎 {p["name"]}", description=p["description"], color=0x2f3136)
    total_stock = get_total_product_stock_count(product_id)
    embed.add_field(name="📦 Estoque Total", value=f"``` {total_stock} unidades ```", inline=True)
    embed.set_footer(text="🛒 Selecione o plano abaixo para comprar")
    await ctx.respond(embed=embed, view=ProductBuyPlanSelectView(product_id))

@bot.slash_command(name="produtos", description="Mostra todos os produtos da loja")
async def produtos(ctx):
    if not PRODUCTS: return await ctx.respond("Nenhum produto cadastrado!", ephemeral=True)
    await ctx.respond("Selecione um produto para ver os detalhes:", view=ProductSelectView(), ephemeral=False)

@bot.slash_command(name="estoque_artificial", description="Adiciona itens repetidos ao estoque")
async def estoque_artificial(ctx):
    if ctx.author.id != OWNER_ID: return await ctx.respond("❌ Apenas o dono!", ephemeral=True)
    opts = [discord.SelectOption(label=p["name"], value=pid) for pid, p in PRODUCTS.items()]
    if not opts: return await ctx.respond("Crie um produto primeiro!", ephemeral=True)
    select = Select(placeholder="Escolha o produto...", options=opts)
    async def sel_cb(i):
        selected_pid = select.values[0]
        await i.response.send_message(f"Estoque artificial para **{PRODUCTS[selected_pid]["name"]}**:", view=AdminProductStockPlanSelectView(selected_pid, ArtificialStockModal), ephemeral=True)
    select.callback = sel_cb
    view = View(); view.add_item(select)
    await ctx.respond("Selecione o produto para estoque artificial:", view=view, ephemeral=True)

@bot.slash_command(name="painel", description="Abre o painel administrativo da loja")
async def painel(ctx):
    if ctx.author.id != OWNER_ID: return await ctx.respond(f"❌ Apenas o dono pode acessar.", ephemeral=True)
    await ctx.respond("🛠️ **Painel Administrativo da Loja**", view=AdminPanelMainView(), ephemeral=True)

@bot.slash_command(name="backup", description="Faz backup dos dados da loja")
async def backup(ctx):
    if ctx.author.id != OWNER_ID: return await ctx.respond("❌ Apenas o dono pode usar este comando.", ephemeral=True)
    await ctx.defer(ephemeral=True)
    with open(PRODUCTS_FILE, "rb") as f:
        await ctx.followup.send("📦 Backup de produtos:", file=discord.File(f, "products.json"), ephemeral=True)
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
