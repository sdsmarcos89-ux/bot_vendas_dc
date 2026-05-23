import discord
from discord.ext import commands
import asyncio
from flask import Flask
from threading import Thread
import os

# ==========================================
# CONFIGURAÇÃO - TOKEN
# ==========================================
BOT_TOKEN = 'MTUwNzE1ODAzODI3MDk3MTkwNA.GSMAJG.NdET2ZZMgXbHvCJW6nXSgbNYtlKGWTwCZAty0E' 
# ==========================================

# --- SERVIDOR WEB PARA O RENDER ---
app = Flask('')

@app.route('/')
def home():
    return "Bot Online!"

def run_web():
    # O Render exige que o bot escute na porta definida pela variável de ambiente PORT
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True # Garante que a thread feche se o processo principal fechar
    t.start()
# ----------------------------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ Bot conectado como: {bot.user}')

@bot.command()
@commands.has_permissions(administrator=True)
async def spam(ctx, qtd: int, *, msg: str):
    if qtd > 50: qtd = 50
    await ctx.send(f'🚀 Iniciando spam de {qtd} mensagens...')
    for _ in range(qtd):
        await ctx.send(msg)
        await asyncio.sleep(0.6)
    await ctx.send('✅ Concluído.')

@bot.command()
@commands.has_permissions(administrator=True)
async def pingall(ctx, *, msg: str = "Teste"):
    await ctx.send('📣 Iniciando pings...')
    membros = [m for m in ctx.guild.members if not m.bot]
    for i in range(0, len(membros), 10):
        chunk = membros[i:i+10]
        mentions = " ".join([m.mention for m in chunk])
        await ctx.send(f'{mentions} {msg}')
        await asyncio.sleep(1.2)
    await ctx.send('✅ Concluído.')

@bot.command()
@commands.has_permissions(administrator=True)
async def stopraid(ctx):
    await ctx.send('🛑 Desligando...')
    await bot.close()

if __name__ == "__main__":
    keep_alive() # Inicia o servidor web
    bot.run(BOT_TOKEN) # Inicia o bot do Discord
