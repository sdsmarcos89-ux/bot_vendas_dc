import discord
from discord.ext import commands
import asyncio

# ==========================================
# CONFIGURAÇÃO - COLOQUE SEU TOKEN AQUI
# ==========================================
BOT_TOKEN = 'SEU_TOKEN_AQUI' 
# ==========================================

# Configuração de Intents (Permissões necessárias no Portal do Desenvolvedor)
intents = discord.Intents.default()
intents.message_content = True  # Ative "Message Content Intent" no portal
intents.members = True          # Ative "Server Members Intent" no portal

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ Bot conectado como: {bot.user}')
    print(f'📌 Servidores: {len(bot.guilds)}')
    print('--- COMANDOS DE TESTE DISPONÍVEIS ---')
    print('!spam <quantidade> <mensagem>')
    print('!pingall <mensagem>')
    print('!stopraid')

@bot.command()
@commands.has_permissions(administrator=True)
async def spam(ctx, qtd: int, *, msg: str):
    """Envia mensagens repetidas para teste de estresse (Limite: 50)"""
    if qtd > 50:
        await ctx.send("⚠️ Limite de segurança atingido. Enviando apenas 50 mensagens.")
        qtd = 50
    
    await ctx.send(f'🚀 Iniciando teste de spam ({qtd} mensagens)...')
    for _ in range(qtd):
        await ctx.send(msg)
        await asyncio.sleep(0.6) # Delay para evitar banimento por rate limit do Discord
    await ctx.send('✅ Teste de spam concluído.')

@bot.command()
@commands.has_permissions(administrator=True)
async def pingall(ctx, *, msg: str = "Teste de Estresse"):
    """Menciona todos os membros humanos do servidor"""
    await ctx.send('📣 Iniciando pings em massa...')
    membros = [m for m in ctx.guild.members if not m.bot]
    
    if not membros:
        await ctx.send("Nenhum membro encontrado.")
        return

    # Envia pings em grupos de 10 para não travar o chat
    for i in range(0, len(membros), 10):
        chunk = membros[i:i+10]
        mentions = " ".join([m.mention for m in chunk])
        await ctx.send(f'{mentions} {msg}')
        await asyncio.sleep(1.2)
    await ctx.send('✅ Teste de ping em massa concluído.')

@bot.command()
@commands.has_permissions(administrator=True)
async def stopraid(ctx):
    """Desliga o bot imediatamente"""
    await ctx.send('🛑 Comando de segurança recebido. Desligando bot...')
    await bot.close()

# Tratamento de erro básico
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Você precisa ser Administrador para usar este comando.")
    else:
        print(f'Erro: {error}')

if __name__ == "__main__":
    if BOT_TOKEN == 'SEU_TOKEN_AQUI':
        print("❌ ERRO: Você esqueceu de colocar o seu Token no código!")
    else:
        bot.run(BOT_TOKEN)
