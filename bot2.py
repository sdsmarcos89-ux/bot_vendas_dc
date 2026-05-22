import disnake
from disnake.ext import commands
import aiosqlite
import mercadopago
import uuid
import os

# --- CONFIGURAÇÃO DO BANCO DE DATOS ---
DB_NAME = "shop_bot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS guild_config (guild_id INTEGER PRIMARY KEY, log_channel_id INTEGER, pix_key TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, name TEXT, price REAL, stock INTEGER, description TEXT)")
        await db.commit()

# --- BOT E COMANDOS ---
bot = commands.Bot(command_prefix="!", intents=disnake.Intents.all())

@bot.event
async def on_ready():
    await init_db()
    print(f"✅ Bot Online como {bot.user}")

@bot.slash_command(name="config", description="Configuração da Loja")
async def setup(inter: disnake.ApplicationCommandInteraction, log_channel: disnake.TextChannel, pix_key: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO guild_config (guild_id, log_channel_id, pix_key) VALUES (?, ?, ?)", 
                         (inter.guild.id, log_channel.id, pix_key))
        await db.commit()
    await inter.response.send_message(f"✅ Configurado! Logs em: {log_channel.mention}")

@bot.slash_command(name="adicionar", description="Adicionar Produto")
async def add_prod(inter: disnake.ApplicationCommandInteraction, nome: str, preco: float, estoque: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO products (guild_id, name, price, stock) VALUES (?, ?, ?, ?)", 
                         (inter.guild.id, nome, preco, estoque))
        await db.commit()
    await inter.response.send_message(f"📦 Produto {nome} adicionado!")

@bot.slash_command(name="loja", description="Abrir Painel de Vendas")
async def shop(inter: disnake.ApplicationCommandInteraction):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM products WHERE guild_id = ?", (inter.guild.id,)) as cursor:
            products = await cursor.fetchall()
    
    if not products: return await inter.response.send_message("❌ Loja vazia.")

    embed = disnake.Embed(title=f"🛒 Loja {inter.guild.name}", color=0x2b2d31)
    options = [disnake.SelectOption(label=p[2], value=str(p[0]), description=f"R${p[3]:.2f}") for p in products]
    
    view = disnake.ui.View()
    view.add_item(disnake.ui.StringSelect(placeholder="Escolha um produto", options=options, custom_id="buy"))
    await inter.response.send_message(embed=embed, view=view)

# TOKEN DO SEU BOT (Pegue no Discord Developer Portal)
# bot.run("COLOQUE_SEU_TOKEN_AQUI")
