import discord
from discord.ext import commands
import asyncio

# ==========================================
# CONFIGURAÇÃO - TOKEN INTEGRADO
# ==========================================
BOT_TOKEN = 'MTUwNzE1ODAzODI3MDk3MTkwNA.GpXQ_J.0uaTkeZDRML0y5n0r_dM5pR58URWypDNrfwGd8' 
# ==========================================

intents = discord.Intents.default()
intents.message_content = True  
intents.members = True          

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ Bot conectado como: {bot.user}')
    print('--- SISTEMA PRONTO PARA TESTES ---')

@bot.command()
@commands.has_permissions(administrator=True)
async def spam(ctx, qtd: int, *, msg: str):
    """Teste de estresse: !spam <quantidade> <mensagem>"""
    if qtd > 50: qtd = 50
    await ctx.send(f'🚀 Iniciando teste de spam ({qtd} mensagens)...')
    for _ in range(qtd):
        await ctx.send(msg)
        await asyncio.sleep(0.6)
    await ctx.send('✅ Teste concluído.')

@bot.command()
@commands.has_permissions(administrator=True)
async def pingall(ctx, *, msg: str = "Teste de Estresse"):
    """Teste de menção: !pingall <mensagem>"""
    await ctx.send('📣 Iniciando pings em massa...')
    membros = [m for m in ctx.guild.members if not m.bot]
    for i in range(0, len(membros), 10):
        chunk = membros[i:i+10]
        mentions = " ".join([m.mention for m in chunk])
        await ctx.send(f'{mentions} {msg}')
        await asyncio.sleep(1.2)
    await ctx.send('✅ Teste concluído.')

@bot.command()
@commands.has_permissions(administrator=True)
async def stopraid(ctx):
    """Desliga o bot: !stopraid"""
    await ctx.send('🛑 Desligando...')
    await bot.close()

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Erro: Você precisa ser Administrador.")

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
