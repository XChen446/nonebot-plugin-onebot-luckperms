from nonebot import on_command
from nonebot_plugin_onebot_luckperms import register_node, require, get_context

register_node("demo.ban", "Ban a user", default=False)
register_node("demo.kick", "Kick a user", default=False)
register_node("demo.mute", "Mute a user", default=False)

ban = on_command("ban", permission=require("demo.ban"))
kick = on_command("kick", permission=require("demo.kick"))
mute = on_command("mute", permission=require("demo.mute"))


@ban.handle()
async def _():
    ctx = get_context()
    if ctx and ctx.identity.role == "owner":
        await ban.send("Owner executed ban")
    else:
        await ban.send("Ban executed")


@kick.handle()
async def _():
    await kick.send("Kick executed")


@mute.handle()
async def _():
    await mute.send("Mute executed")
