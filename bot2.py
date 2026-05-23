import discord
from discord.ext import commands
import asyncio

# ==========================================
# CONFIGURAÇÃO - TOKEN EXPOSTO
# ==========================================
BOT_TOKEN = 'MTUwNzE1ODAzODI3MDk3MTkwNA.Gd5ht2.SuhOphkrMsy80tKAJRP3klLHp8FRQsS4ZocW4g' 
# ==========================================

# Configurações de Intents (Permissões)
intents = discord.Intents.default()
intents.message_content = True  # Ative isso no Portal do Desenvolvedor
intents.members = True          # Ative isso no Portal do Desenvolvedor

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ Bot conectado com sucesso como: {bot.user}')
    print('--- COMANDOS DISPONÍVEIS ---')
    print('!spam <quantidade> <mensagem> - Simula spam (Máx: 50)')
    print('!pingall <mensagem> - Menciona todos os membros')
    print('!stopraid - Desliga o bot imediatamente')

@bot.command()
@commands.has_permissions(administrator=True)
async def spam(ctx, qtd: int, *, msg: str):
    """Simula envio massivo de mensagens"""
    if qtd > 50: qtd = 50
    await ctx.send(f'🚀 Iniciando teste de spam: {qtd} mensagens...')
    for _ in range(qtd):
        await ctx.send(msg)
        await asyncio.sleep(0.6)
    await ctx.send('✅ Teste de spam finalizado.')

@bot.command()
@commands.has_permissions(administrator=True)
async def pingall(ctx, *, msg: str = "Teste de Estresse"):
    """Simula menções em massa"""
    await ctx.send('📣 Iniciando pings em massa...')
    membros = [m for m in ctx.guild.members if not m.bot]
    
    if not membros:
        await ctx.send("Nenhum membro encontrado para pingar.")
        return

    # Envia pings em blocos de 10
    for i in range(0, len(membros), 10):
        chunk = membros[i:i+10]
        mentions = " ".join([m.mention for m in chunk])
        await ctx.send(f'{mentions} {msg}')
        await asyncio.sleep(1.2)
    await ctx.send('✅ Teste de pings finalizado.')

@bot.command()
@commands.has_permissions(administrator=True)
async def stopraid(ctx):
    """Comando de segurança para desligar o bot"""
    await ctx.send('🛑 Desligando o bot...')
    await bot.close()

# Tratamento para quando alguém sem permissão tenta usar os comandos
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Você precisa de permissão de Administrador para este teste.")
    else:
        print(f'Erro detectado: {error}')

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
