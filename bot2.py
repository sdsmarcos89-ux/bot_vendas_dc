import discord
from discord.ext import commands
import asyncio
import os

# Função para carregar o token de forma segura
def carregar_token():
    if os.path.exists('token.txt'):
        with open('token.txt', 'r') as f:
            return f.read().strip()
    else:
        print("❌ ERRO: Arquivo 'token.txt' não encontrado!")
        print("Crie um arquivo chamado token.txt e cole seu token dentro dele.")
        return None

TOKEN = carregar_token()

# Configurações do Bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ Bot online: {bot.user}')
    print('Use !stopraid para desligar com segurança.')

@bot.command()
@commands.has_permissions(administrator=True)
async def spam(ctx, qtd: int, *, msg: str):
    """Envia mensagens repetidas (Máx: 50)"""
    qtd = min(qtd, 50)
    await ctx.send(f'🚀 Iniciando spam de {qtd} mensagens...')
    for _ in range(qtd):
        await ctx.send(msg)
        await asyncio.sleep(0.6)
    await ctx.send('✅ Concluído.')

@bot.command()
@commands.has_permissions(administrator=True)
async def pingall(ctx, *, msg: str = ""):
    """Menciona todos os membros em blocos"""
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
    """Desliga o bot"""
    await ctx.send('🛑 Desligando...')
    await bot.close()

if __name__ == "__main__":
    if TOKEN:
        try:
            bot.run(TOKEN)
        except discord.LoginFailure:
            print("❌ ERRO: O Token no arquivo 'token.txt' é inválido!")
