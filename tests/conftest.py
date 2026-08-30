import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

# NoneBot 官方测试引导：在收集任何测试模块之前初始化驱动并加载插件，
# 使插件顶层 require("nonebot_plugin_localstore") / get_plugin_config /
# localstore.get_plugin_data_file 均有可用的运行环境。
nonebot.init(driver="~aiohttp")
driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

nonebot.load_plugin("nonebot_plugin_localstore")
nonebot.load_plugin("nonebot_plugin_onebot_luckperms")