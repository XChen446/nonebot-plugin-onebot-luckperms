import tempfile
from pathlib import Path

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

# NoneBot 官方测试引导：在收集任何测试模块之前初始化驱动并加载插件，
# 使插件顶层 require("nonebot_plugin_localstore") / get_plugin_config /
# localstore.get_plugin_data_file 均有可用的运行环境。
nonebot.init(driver="~aiohttp")
driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

nonebot.load_plugin("nonebot_plugin_localstore")

# 把 localstore 数据基目录重定向到临时目录，
# 避免测试在真实用户数据目录落盘（get_plugin_data_file 只建目录不建文件）。
import nonebot_plugin_localstore as store

store.BASE_DATA_DIR = Path(tempfile.mkdtemp(prefix="oblp-test-data-"))

nonebot.load_plugin("nonebot_plugin_onebot_luckperms")