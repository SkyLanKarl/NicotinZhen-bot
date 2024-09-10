import subprocess
import discord
from discord.ext import commands
import yt_dlp
import asyncio
from clean_bili_url import clean_bilibili_url
import requests
import bili_API

# 创建并启用 intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True  # 允许读取消息内容

# 创建 bot 实例，传入 intents 参数
bot = commands.Bot(command_prefix="!", intents=intents)

# 音频队列
queue = []
search_results = {}
volume_level = 0.1  # 默认音量为 0.1

@bot.command(name='bs', help='在Bilibili上搜索视频')
async def search_bili(ctx, *, query):
    global search_results  # 声明全局变量

    # 调用 API 进行搜索
    result = bili_API.bili_s(query)  # 调用API模块中的bili_s
    #print(f"API 返回结果: {result}")  # 打印 result 以确保其有内容
    #print(f"结果类型: {type(result)}")  # 打印 result 的类型

    if isinstance(result, list) and len(result) > 0:  # 确保 result 是列表且有内容
        search_results[ctx.author.id] = result  # 使用用户ID为key保存搜索结果
        response = "搜索结果：\n"
        for index, video in enumerate(result, start=1):  # 添加编号并打印视频标题
            response += f"{index}. 标题：{video['title']}\n"
        response += "请输入 `!c <编号>` 选择要播放的歌曲。"
    else:
        response = "未找到相关视频，请重试。"

    #print(search_results, flush=True)  # 输出调试信息到命令行
    await ctx.send(response)

# 添加选择命令
@bot.command(name='c', help='选择要播放的歌曲')
async def choose_bili(ctx, choice: int):
    global search_results  # 声明全局变量

    # 检查用户是否有之前的搜索结果
    if ctx.author.id not in search_results:
        await ctx.send("请先使用 `!bs <关键词>` 搜索歌曲。")
        return

    # 获取用户的搜索结果
    results = search_results[ctx.author.id]

    # 检查用户输入的选择是否有效
    if isinstance(results, list) and 1 <= choice <= len(results):  # 确保 results 是列表
        selected_video = results[choice - 1]

        # 确保 selected_video 是字典
        if isinstance(selected_video, dict) and 'title' in selected_video and 'url' in selected_video:
            #await ctx.send(f"你选择了: {selected_video['title']}，即将处理该请求。")
            
            # 获取语音客户端
            #voice_client = ctx.voice_client

            # 检查是否有歌曲正在播放
            if len(queue) > 0:
                queue.append(selected_video['url'])  # 将选择的歌曲加入队列
                await ctx.send(f"当前正在播放歌曲，已将 {selected_video['title']} 添加到队列中。")
            else:
                await play(ctx, selected_video['url'])  # 如果没有歌曲播放，则直接播放
        else:
            await ctx.send("无法解析视频信息，请重试。")
    else:
        await ctx.send(f"无效选择，请输入 1 到 {len(results)} 之间的编号。")



# 播放音乐并添加到队列
@bot.command(name='play', help='从Bilibili/YouTube链接播放音频')
async def play(ctx, url):
    # 检查用户是否在语音频道中
    if ctx.author.voice:
        voice_channel = ctx.author.voice.channel
        if ctx.voice_client is None:
            await voice_channel.connect()
        elif ctx.voice_client.channel != voice_channel:
            await ctx.voice_client.disconnect()
            await voice_channel.connect()

        voice_client = ctx.voice_client

        with yt_dlp.YoutubeDL({'format': 'bestaudio/best[height<=720]/worstaudio', 'noplaylist': 'True', 'extractaudio': True, 'retries': 5, 'continuedl': True  }) as ydl:
            print(url)
            info = ydl.extract_info(url, download=False)
            audio_url = info['formats'][0]['url']

        if voice_client.is_playing():
            queue.append(url)  # 将新 URL 加入队列
            await ctx.send(f"已加入队列: {info['title']}")
        else:
            ffmpeg_path = "ffmpeg/bin/ffmpeg.exe"
            ffmpeg_options = {
                                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -analyzeduration 100M -probesize 100M -err_detect ignore_err',
                                'options': '-vn -loglevel debug -report'  # 输出详细日志并生成报告文件
                            }

            try:
                audio_source = discord.FFmpegPCMAudio(
                    executable=ffmpeg_path, 
                    source=audio_url, 
                    **ffmpeg_options
                )
                audio_source_with_volume = discord.PCMVolumeTransformer(audio_source, volume=volume_level)

                voice_client.play(audio_source_with_volume, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx, voice_channel), bot.loop))
                await ctx.send(f"正在播放: {info['title']}，音量为 {volume_level * 100}%")
            except subprocess.CalledProcessError as e:
                await ctx.send(f"播放时发生子进程错误: {str(e)}")
            except Exception as e:
                await ctx.send(f"播放时出错: {str(e)}")

                
    else:
        await ctx.send("你必须先加入语音频道！")


# 跳过当前歌曲
@bot.command(name='skip', help='跳过当前歌曲')
async def skip(ctx):
    voice_channel = ctx.message.guild.voice_client
    if voice_channel.is_playing():
        voice_channel.stop()  # 停止当前播放
        await ctx.send("已跳过当前歌曲")
        await play_next(ctx, voice_channel)  # 手动触发播放下一首

# 播放队列中的下一首歌曲
async def play_next(ctx, voice_channel):
    if queue:
        url = queue.pop(0)  # 取出队列中的下一首歌曲
        
        # 使用 yt-dlp 获取音频源
        with yt_dlp.YoutubeDL({'format': 'bestaudio', 'noplaylist': 'True'}) as ydl:
            info = ydl.extract_info(url, download=False)
            url2 = info['formats'][0]['url']

            # 手动指定 ffmpeg 的路径
            ffmpeg_path = "ffmpeg/bin/ffmpeg.exe"  # 这里替换为你安装的 ffmpeg 的路径
            ffmpeg_options = {
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                'options': '-vn'
            }

            voice_channel.play(
                discord.FFmpegPCMAudio(executable=ffmpeg_path, source=url2, **ffmpeg_options),
                after=lambda e: asyncio.create_task(play_next(ctx, voice_channel))  # 使用 asyncio.create_task 调用异步任务
            )
        
        await ctx.send(f"正在播放: {info['title']}")
    else:
        await ctx.send("队列已为空")

# 随时调节音量
@bot.command(name='v', help='调节音量，使用范围为 0 到 100')
async def volume(ctx, volume: int):
    global volume_level  # 声明全局变量

    # 检查音量范围是否合法
    if 0 <= volume <= 100:
        volume_level = volume / 100  # 将音量范围转换为 0.0 到 1.0

        # 检查 Bot 是否在播放音乐
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.source.volume = volume_level  # 调整当前播放的音量
            await ctx.send(f"音量已设置为: {volume}%")
        else:
            await ctx.send("当前没有正在播放的音乐。")
    else:
        await ctx.send("请输入有效的音量范围 (0 到 100)。")

# 退出语音频道
@bot.command(name='gun', help='让Bot退出语音频道')
async def leave(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_connected():
        await voice_client.disconnect()
        await ctx.send("尼古丁真已经滚出语音频道")

# 启动 Bot
bot.run('')