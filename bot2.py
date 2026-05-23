import discord
from discord.ext import commands
import asyncio
from config import BOT_TOKEN

# Configuração inicial do bot e permissões (Intents)
intents = discord.Intents.default()
intents.message_content = True  # Permite ler o conteúdo das mensagens
intents.members = True          # Permite ver a lista de membros

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    print('--- PRONTO PARA TESTES DE RAID CONTROLADO ---')

@bot.command(name='spam')
@commands.has_permissions(administrator=True)
async def spam_messages(ctx, count: int, *, message: str):
    """Envia um número especificado de mensagens para o canal atual."""
    if count > 50:
        await ctx.send("⚠️ Limite de segurança: máximo 50 mensagens por vez.")
        return

    await ctx.send(f"🚀 Iniciando teste de spam: {count} mensagens...")
    for _ in range(count):
        await ctx.send(message)
        await asyncio.sleep(0.5) # Delay para não ser bloqueado pelo Discord
    await ctx.send("✅ Teste de spam concluído.")

@bot.command(name='pingall')
@commands.has_permissions(administrator=True)
async def ping_all_members(ctx, *, message: str = "Teste de Estresse"):
    """Pinga todos os membros do servidor (exceto bots) no canal atual."""
    await ctx.send("📣 Iniciando ping em massa...")
    members = [member for member in ctx.guild.members if not member.bot]
    
    if not members:
        await ctx.send("Nenhum membro humano encontrado.")
        return

    # Envia pings em blocos de 10 para evitar limites de caracteres
    chunk_size = 10 
    for i in range(0, len(members), chunk_size):
        chunk = members[i:i + chunk_size]
        mentions = " ".join([member.mention for member in chunk])
        await ctx.send(f"{mentions} {message}")
        await asyncio.sleep(1)
    await ctx.send("✅ Teste de ping em massa concluído.")

@bot.command(name='stopraid')
@commands.has_permissions(administrator=True)
async def stop_raid(ctx):
    """Desliga o bot imediatamente por segurança."""
    await ctx.send("🛑 Comando de parada recebido. Desligando...")
    await bot.close()

# Inicia o bot usando o token do arquivo config.py
if __name__ == "__main__":
    bot.run(BOT_TOKEN)
