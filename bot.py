from discord.ext import commands
from mistralai import Mistral
from dotenv import load_dotenv
from datetime import datetime
from typing import List, Tuple, Optional, Dict
import discord
import logging
import json
import os
import asyncio
from dataclasses import dataclass
import sqlite3
from pathlib import Path

@dataclass
class ModerationResult:
    """Classe pour représenter le résultat d'une modération"""
    violations: List[Tuple[str, float]]
    response_id: str
    latency: float

@dataclass
class BotConfig:
    """Classe pour stocker la configuration du bot"""
    discord_token: str
    mistral_api_key: str
    default_mod_role_id: Optional[int]
    default_mod_channel_id: Optional[int]
    bot_name: str
    bot_version: str

    @classmethod
    def from_env(cls):
        """Charge la configuration depuis les variables d'environnement"""
        load_dotenv()
        
        required_vars = [
            "DISCORD_TOKEN",
            "MISTRAL_API_KEY",
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
            
        return cls(
            discord_token=os.getenv("DISCORD_TOKEN"),
            mistral_api_key=os.getenv("MISTRAL_API_KEY"),
            default_mod_role_id=int(os.getenv("MOD_ROLE_ID", 0)) or None,
            default_mod_channel_id=int(os.getenv("MOD_CHANNEL_ID", 0)) or None,
            bot_name=os.getenv("BOT_NAME", "ModBot"),
            bot_version=os.getenv("BOT_VERSION", "1.0.0")
        )

class ConfigDB:
    """Gestion de la configuration par serveur dans une base SQLite"""
    def __init__(self, db_path: str = "bot_config.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialise la base de données"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS server_config (
                    guild_id INTEGER PRIMARY KEY,
                    mod_role_id INTEGER,
                    mod_channel_id INTEGER
                )
            ''')

    async def get_config(self, guild_id: int) -> Tuple[Optional[int], Optional[int]]:
        """Récupère la configuration d'un serveur"""
        def _get():
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    'SELECT mod_role_id, mod_channel_id FROM server_config WHERE guild_id = ?',
                    (guild_id,)
                )
                result = cursor.fetchone()
                return result if result else (None, None)
                
        return await asyncio.to_thread(_get)

    async def set_config(self, guild_id: int, mod_role_id: Optional[int] = None, 
                        mod_channel_id: Optional[int] = None) -> None:
        """Met à jour la configuration d'un serveur"""
        def _set():
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO server_config (guild_id, mod_role_id, mod_channel_id)
                    VALUES (?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        mod_role_id = COALESCE(?, mod_role_id),
                        mod_channel_id = COALESCE(?, mod_channel_id)
                ''', (guild_id, mod_role_id, mod_channel_id, mod_role_id, mod_channel_id))

        await asyncio.to_thread(_set)

CATEGORY_DESCRIPTIONS = {
    "sexual": "Contenu à caractère sexuel",
    "hate_and_discrimination": "Contenu haineux ou discriminatoire",
    "violence_and_threats": "Contenu violent ou menaçant",
    "dangerous_and_criminal_content": "Contenu dangereux ou criminel",
    "selfharm": "Auto-mutilation",
    "health": "Conseil médical",
    "financial": "Conseil financier",
    "law": "Conseil juridique",
    "pii": "Divulgation d'informations personnelles",
}

class ModBot(commands.Bot):
    """Classe personnalisée pour le bot de modération"""
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        
        self.config = BotConfig.from_env()
        self.mistral_client = Mistral(self.config.mistral_api_key)
        self.db = ConfigDB()
        self.uptime = None
        self._setup_logging()
        self._setup_commands()

    def _setup_logging(self) -> None:
        """Configure le système de logging"""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler("bot.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def _setup_commands(self) -> None:
        """Configure les commandes du bot"""
        @self.command(name="set_mod_role")
        @commands.has_permissions(administrator=True)
        async def set_mod_role(ctx: commands.Context, role: discord.Role):
            """Configure le rôle de modérateur pour le serveur"""
            await self.db.set_config(ctx.guild.id, mod_role_id=role.id)
            await ctx.send(f"✅ Rôle de modérateur configuré: {role.mention}")

        @self.command(name="set_mod_channel")
        @commands.has_permissions(administrator=True)
        async def set_mod_channel(ctx: commands.Context, channel: discord.TextChannel):
            """Configure le salon de modération pour le serveur"""
            await self.db.set_config(ctx.guild.id, mod_channel_id=channel.id)
            await ctx.send(f"✅ Salon de modération configuré: {channel.mention}")

        @self.command(name="show_config")
        @commands.has_permissions(administrator=True)
        async def show_config(ctx: commands.Context):
            """Affiche la configuration actuelle du serveur"""
            mod_role_id, mod_channel_id = await self.db.get_config(ctx.guild.id)
            
            embed = discord.Embed(
                title="Configuration du serveur",
                color=discord.Color.blue()
            )
            
            mod_role = ctx.guild.get_role(mod_role_id) if mod_role_id else None
            mod_channel = ctx.guild.get_channel(mod_channel_id) if mod_channel_id else None
            
            embed.add_field(
                name="Rôle de modérateur",
                value=mod_role.mention if mod_role else "Non configuré",
                inline=False
            )
            embed.add_field(
                name="Salon de modération",
                value=mod_channel.mention if mod_channel else "Non configuré",
                inline=False
            )
            
            await ctx.send(embed=embed)

        @set_mod_role.error
        @set_mod_channel.error
        @show_config.error
        async def config_error(ctx: commands.Context, error: commands.CommandError):
            if isinstance(error, commands.MissingPermissions):
                await ctx.send("❌ Vous devez être administrateur pour utiliser cette commande.")
            elif isinstance(error, commands.MissingRequiredArgument):
                await ctx.send("❌ Argument manquant. Veuillez vérifier la syntaxe de la commande.")
            else:
                await ctx.send("❌ Une erreur est survenue lors de l'exécution de la commande.")
                self.logger.error(f"Command error: {error}")

    async def get_server_config(self, guild_id: int) -> Tuple[Optional[int], Optional[int]]:
        """Récupère la configuration d'un serveur avec fallback sur les valeurs par défaut"""
        mod_role_id, mod_channel_id = await self.db.get_config(guild_id)
        return (
            mod_role_id or self.config.default_mod_role_id,
            mod_channel_id or self.config.default_mod_channel_id
        )

    async def check_message(self, message: discord.Message) -> Optional[ModerationResult]:
        """Vérifie un message pour détecter du contenu inapproprié"""
        try:
            start_time = datetime.now()
            response = await asyncio.to_thread(
                self.mistral_client.classifiers.moderate,
                model="mistral-moderation-latest",
                inputs=[message.content]
            )
            latency = (datetime.now() - start_time).total_seconds()

            violations = []
            for result in response.results:
                for category, is_violation in result.categories.items():
                    if is_violation:
                        violations.append((category, result.category_scores[category]))

            if violations:
                return ModerationResult(
                    violations=violations,
                    response_id=response.id,
                    latency=latency
                )
            return None

        except Exception as e:
            self.logger.error(f"Error during message moderation: {e}")
            return None

    async def handle_violation(self, message: discord.Message, result: ModerationResult) -> None:
        """Gère une violation détectée"""
        try:
            await message.delete()
            
            # Créer l'embed pour l'utilisateur
            embed = self._create_violation_embed(message, result)
            await message.channel.send(embed=embed)
            
            # Récupérer la configuration du serveur
            mod_role_id, mod_channel_id = await self.get_server_config(message.guild.id)
            
            # Notifier les modérateurs
            if mod_channel_id:
                mod_channel = self.get_channel(mod_channel_id)
                if mod_channel:
                    violation_report = self._create_violation_report(message, result)
                    await mod_channel.send(
                        f"<@&{mod_role_id}>\n```json\n{violation_report}\n```"
                    )
                else:
                    self.logger.error(f"Mod channel {mod_channel_id} not found")
            
            self.logger.info(
                f"Message from {message.author} ({message.author.id}) "
                f"deleted and reported for violation: {result.violations}"
            )
        
        except Exception as e:
            self.logger.error(f"Error handling violation: {e}")

    def _create_violation_embed(self, message: discord.Message, result: ModerationResult) -> discord.Embed:
        """Crée l'embed de violation pour l'utilisateur"""
        category_field_value = "\n".join([
            f"{CATEGORY_DESCRIPTIONS.get(category, category)}: {round(score, 3)*100}%" 
            for category, score in result.violations
        ])
        
        return discord.Embed(
            title="🚨 Automodération",
            description=(
                f"{message.author.mention}, votre message a été supprimé et signalé aux "
                "modérateurs car il a été considéré comme offensant par le système "
                "d'auto modération. Si vous pensez qu'il s'agit d'une erreur, veuillez "
                "contacter un modérateur et lui fournir l'ID de la violation ci-dessous."
            ),
            color=discord.Color.red()
        ).add_field(name="Catégories", value=category_field_value
        ).add_field(name="ID", value=result.response_id
        ).set_thumbnail(url="https://cdn3.emoji.gg/emojis/2731-certified-moderator.png")

    def _create_violation_report(self, message: discord.Message, result: ModerationResult) -> str:
        """Crée le rapport de violation pour les modérateurs"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "latency": result.latency,
            "user": message.author.name,
            "user_id": message.author.id,
            "message": message.content,
            "message_id": message.id,
            "violations": [
                {
                    "category": category,
                    "score": score
                } for category, score in result.violations
            ],
            "response_id": result.response_id
        }
        return json.dumps(report, indent=4)

    async def get_uptime(self) -> str:
        """Retourne le temps d'activité du bot"""
        if not self.uptime:
            return "Bot not fully initialized"
            
        delta = datetime.now() - self.uptime
        days, seconds = delta.days, delta.seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{days}d, {hours}h, {minutes}m, {seconds}s"

async def main():
    """Point d'entrée principal"""
    bot = ModBot()
    
    @bot.event
    async def on_ready():
        bot.logger.info(f'Logged in as {bot.user.name}')
        bot.logger.info(f"Connected to {len(bot.guilds)} servers")
        bot.uptime = datetime.now()
        try:
            synced = await bot.tree.sync()
            bot.logger.info(f"Synced {len(synced)} slash commands")
        except Exception as e:
            bot.logger.error(f"Failed to sync slash commands: {e}")

    @bot.event
    async def on_message(message):
        if message.author == bot.user:
            return
            
        bot.logger.info(f"Message from {message.author} ({message.author.id}): {message.content}")
        
        result = await bot.check_message(message)
        if result:
            await bot.handle_violation(message, result)
            
        await bot.process_commands(message)

    try:
        await bot.start(bot.config.discord_token)
    except Exception as e:
        bot.logger.error(f"Failed to start bot: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())