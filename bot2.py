import discord
from discord.ext import commands
from discord import app_commands
import json
import os

# Configuração básica
TOKEN = 'SEU_TOKEN_AQUI'

class SalesBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        self.products = {}
        self.load_products()

    async def setup_hook(self):
        # Sincroniza os slash commands
        await self.tree.sync()
        print(f"Slash commands sincronizados para {self.user}")

    def load_products(self):
        if os.path.exists('products.json'):
            with open('products.json', 'r') as f:
                self.products = json.load(f)

    def save_products(self):
        with open('products.json', 'w') as f:
            json.dump(self.products, f, indent=4)

bot = SalesBot()

@bot.event
async def on_ready():
    print(f'Bot logado como {bot.user.name}')

# Comando para criar um produto
@bot.tree.command(name="configurar_produto", description="Configura um novo produto para venda")
@app_commands.describe(nome="Nome do produto", preco="Preço do produto", descricao="Descrição do produto")
async def configurar_produto(interaction: discord.Interaction, nome: str, preco: float, descricao: str):
    # Verifica se o usuário tem permissão de administrador
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Você não tem permissão para usar este comando.", ephemeral=True)
        return

    product_id = str(len(bot.products) + 1)
    bot.products[product_id] = {
        "nome": nome,
        "preco": preco,
        "descricao": descricao,
        "mensagem_id": None,
        "canal_id": interaction.channel_id
    }
    bot.save_products()

    embed = discord.Embed(title=f"Produto: {nome}", description=descricao, color=discord.Color.green())
    embed.add_field(name="Preço", value=f"R$ {preco:.2f}")
    embed.set_footer(text=f"ID do Produto: {product_id}")

    await interaction.response.send_message(f"Produto '{nome}' configurado com sucesso!", ephemeral=True)
    
    # Envia a mensagem do produto no canal
    message = await interaction.channel.send(embed=embed)
    bot.products[product_id]["mensagem_id"] = message.id
    bot.save_products()

# Comando para editar a mensagem do bot (Requisito especial do usuário)
@bot.tree.command(name="editar_mensagem_produto", description="Edita a mensagem de um produto já configurado")
@app_commands.describe(product_id="ID do produto", nova_descricao="Nova descrição para a mensagem")
async def editar_mensagem_produto(interaction: discord.Interaction, product_id: str, nova_descricao: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Você não tem permissão.", ephemeral=True)
        return

    if product_id not in bot.products:
        await interaction.response.send_message("Produto não encontrado.", ephemeral=True)
        return

    product = bot.products[product_id]
    canal = bot.get_channel(product["canal_id"])
    
    try:
        message = await canal.fetch_message(product["mensagem_id"])
        
        # Atualiza a descrição no banco de dados
        product["descricao"] = nova_descricao
        bot.save_products()

        # Edita a mensagem original
        embed = message.embeds[0]
        embed.description = nova_descricao
        await message.edit(embed=embed)
        
        await interaction.response.send_message("Mensagem do produto editada com sucesso!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Erro ao editar mensagem: {str(e)}", ephemeral=True)

# Comandos clássicos de bot de vendas (Inspirados no open source)
@bot.tree.command(name="estoque", description="Verifica o estoque de um produto")
async def estoque(interaction: discord.Interaction, product_id: str):
    if product_id not in bot.products:
        await interaction.response.send_message("Produto não encontrado.", ephemeral=True)
        return
    
    product = bot.products[product_id]
    # Simulação de estoque (em um bot real, isso viria de uma lista de itens)
    await interaction.response.send_message(f"O produto {product['nome']} está disponível!", ephemeral=True)

@bot.tree.command(name="comprar", description="Inicia o processo de compra de um produto")
async def comprar(interaction: discord.Interaction, product_id: str):
    if product_id not in bot.products:
        await interaction.response.send_message("Produto não encontrado.", ephemeral=True)
        return
    
    product = bot.products[product_id]
    
    # Criação de um ticket/canal privado para a compra
    guild = interaction.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    
    channel = await guild.create_text_channel(f"compra-{interaction.user.name}", overwrites=overwrites)
    
    embed = discord.Embed(title="Checkout de Venda", description=f"Você está comprando: **{product['nome']}**", color=discord.Color.blue())
    embed.add_field(name="Valor", value=f"R$ {product['preco']:.2f}")
    embed.add_field(name="Instruções", value="Realize o pagamento via PIX (Simulação) e envie o comprovante aqui.")
    
    await channel.send(content=f"{interaction.user.mention}", embed=embed)
    await interaction.response.send_message(f"Canal de compra criado: {channel.mention}", ephemeral=True)

if __name__ == "__main__":
    # bot.run(TOKEN) # Comentado para não travar a execução no sandbox
    print("Código do bot gerado com sucesso.")
    
