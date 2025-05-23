import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import yt_dlp
from collections import deque
import asyncio

SONG_QUEUES = {}

LOOP_STATUS = {}

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

SONG_QUEUES = {}

async def search_ytdlp_async(query, ydl_opts):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, ydl_opts))

def _extract(query, ydl_opts):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(query, download=False)


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} está online!")


@bot.tree.command(name="skip", description="Pula a música que está tocando atualmente")
async def skip(interaction: discord.Interaction):
    if interaction.guild.voice_client and (interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused()):
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("Música atual pulada.")
    else:
        await interaction.response.send_message("Não há nada tocando para pular.")


@bot.tree.command(name="pause", description="Pausa a música que está tocando atualmente.")
async def pause(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    # Verifica se o bot está em um canal de voz
    if voice_client is None:
        return await interaction.response.send_message("Não estou em um canal de voz.")

    # Verifica se algo está realmente tocando
    if not voice_client.is_playing():
        return await interaction.response.send_message("Nada está tocando no momento.")
    
    # Pausa a faixa
    voice_client.pause()
    await interaction.response.send_message("Reprodução pausada!")


@bot.tree.command(name="resume", description="Retoma a música que está pausada atualmente.")
async def resume(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    # Verifica se o bot está em um canal de voz
    if voice_client is None:
        return await interaction.response.send_message("Não estou em um canal de voz.")

    # Verifica se está realmente pausado
    if not voice_client.is_paused():
        return await interaction.response.send_message("Não estou pausado no momento.")
    
    # Retoma a reprodução
    voice_client.resume()
    await interaction.response.send_message("Reprodução retomada!")


@bot.tree.command(name="stop", description="Para a reprodução e limpa a fila.")
async def stop(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    # Verifica se o bot está em um canal de voz
    if not voice_client or not voice_client.is_connected():
        return await interaction.response.send_message("Não estou conectado a nenhum canal de voz.")

    # Limpa a fila do servidor
    guild_id_str = str(interaction.guild_id)
    if guild_id_str in SONG_QUEUES:
        SONG_QUEUES[guild_id_str].clear()

    # Se algo estiver tocando ou pausado, para
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    # (Opcional) Desconecta do canal
    await voice_client.disconnect()

    await interaction.response.send_message("Reprodução parada e desconectado!")


@bot.tree.command(name="play", description="Toca uma música ou adiciona à fila.")
@app_commands.describe(song_query="Termo de busca")
async def play(interaction: discord.Interaction, song_query: str):
    await interaction.response.defer()

    voice_channel = interaction.user.voice.channel

    if voice_channel is None:
        await interaction.followup.send("Você precisa estar em um canal de voz.")
        return

    voice_client = interaction.guild.voice_client

    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_channel != voice_client.channel:
        await voice_client.move_to(voice_channel)

    ydl_options = {
        "format": "bestaudio[abr<=96]/bestaudio",
        "noplaylist": True,
        "youtube_include_dash_manifest": False,
        "youtube_include_hls_manifest": False,
    }

    query = "ytsearch1: " + song_query
    results = await search_ytdlp_async(query, ydl_options)
    tracks = results.get("entries", [])

    if tracks is None:
        await interaction.followup.send("Nenhum resultado encontrado.")
        return

    first_track = tracks[0]
    audio_url = first_track["url"]
    title = first_track.get("title", "Untitled")

    guild_id = str(interaction.guild_id)
    if SONG_QUEUES.get(guild_id) is None:
        SONG_QUEUES[guild_id] = deque()

    SONG_QUEUES[guild_id].append((audio_url, title))

    if voice_client.is_playing() or voice_client.is_paused():
        await interaction.followup.send(f"Adicionado à fila: **{title}**")
    else:
        await interaction.followup.send(f"Agora tocando: **{title}**")
        await play_next_song(voice_client, guild_id, interaction.channel)


async def play_next_song(voice_client, guild_id, channel):
    if SONG_QUEUES[guild_id]:
        audio_url, title = SONG_QUEUES[guild_id].popleft()

        ffmpeg_options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn -c:a libopus -b:a 96k",
        }

        source = discord.FFmpegOpusAudio(audio_url, **ffmpeg_options, executable="bin\\ffmpeg\\ffmpeg.exe")

        def after_play(error):
            if error:
                print(f"Error playing {title}: {error}")
            asyncio.run_coroutine_threadsafe(play_next_song(voice_client, guild_id, channel), bot.loop)

        voice_client.play(source, after=after_play)
        asyncio.create_task(channel.send(f"Now playing: **{title}**"))
    else:
        await voice_client.disconnect()
        SONG_QUEUES[guild_id] = deque()

@bot.tree.command(name="eduardo", description="eduardo.")
async def dance(interaction: discord.Interaction):
    await interaction.response.send_message("https://tenor.com/tmGKQp8vvew.gif")

@bot.tree.command(name="loop", description="Ativa/desativa o loop da música atual.")
async def loop(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    voice_client = interaction.guild.voice_client

    if voice_client is None or not voice_client.is_playing():
        await interaction.response.send_message("Não há nada tocando para ativar o loop.")
        return

    if guild_id not in LOOP_STATUS:
        LOOP_STATUS[guild_id] = False

    LOOP_STATUS[guild_id] = not LOOP_STATUS[guild_id]
    
    status = "ativado" if LOOP_STATUS[guild_id] else "desativado"
    await interaction.response.send_message(f"Loop {status} para a música atual.")


async def play_next_song(voice_client, guild_id, channel):
    if SONG_QUEUES[guild_id]:
        audio_url, title = SONG_QUEUES[guild_id].popleft()

        ffmpeg_options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn",
        }

        try:
            source = discord.FFmpegOpusAudio(audio_url, **ffmpeg_options, executable="bin\\ffmpeg\\ffmpeg.exe")

            def after_play(error):
                if error:
                    print(f"Erro ao tocar {title}: {error}")
                    asyncio.run_coroutine_threadsafe(channel.send(f"Erro ao tocar {title}. Pulando para próxima música."), bot.loop)
                
                if LOOP_STATUS.get(guild_id, False):
                    SONG_QUEUES[guild_id].appendleft((audio_url, title))
                
                asyncio.run_coroutine_threadsafe(play_next_song(voice_client, guild_id, channel), bot.loop)

            voice_client.play(source, after=after_play)
            await channel.send(f"Agora tocando: **{title}**")
        except Exception as e:
            print(f"Erro ao preparar áudio: {e}")
            await channel.send(f"Erro ao preparar áudio para {title}. Pulando para próxima música.")
            asyncio.create_task(play_next_song(voice_client, guild_id, channel))
    else:
        await voice_client.disconnect()
        SONG_QUEUES[guild_id] = deque()
        if guild_id in LOOP_STATUS:
            LOOP_STATUS[guild_id] = False

# Executar o bot
bot.run(TOKEN)