#!/usr/bin/env python3
"""
AI 工具翻译模块 - 可插拔翻译引擎
  当前引擎：百度翻译
  一键切换：修改变量 TRANSLATOR 即可
  支持：Baidu / Youdao / Microsoft / Google / DeepL
"""

import json
import time
import requests
from abc import ABC, abstractmethod


# ============================================================
# 🔧 在这里切换翻译引擎（改一行即可）
# ============================================================
# 可选值: 'baidu' | 'youdao' | 'microsoft' | 'google' | 'deepl'
TRANSLATOR = 'baidu'


# ============================================================
# API 凭据
# ============================================================
CREDENTIALS = {
    'baidu': {
        'appid': '20260616002632944',
        'api_key': 'RMpY_d8ol8t8ojiqubrn60a0g',
    },
    # 如需切换其他引擎，填写对应的凭据即可
}


# ============================================================
# 抽象基类 - 所有翻译引擎必须实现 translate() 方法
# ============================================================
class BaseTranslator(ABC):
    """翻译引擎基类"""

    def __init__(self, source_lang='en', target_lang='zh'):
        self.source = source_lang
        self.target = target_lang
        self.name = self.__class__.__name__

    @abstractmethod
    def translate(self, text: str) -> str:
        """翻译单条文本，返回翻译结果"""
        pass

    def translate_batch(self, texts: list, delay: float = 1.0) -> list:
        """批量翻译（逐条调用，带延迟避免限流）"""
        results = []
        for i, text in enumerate(texts):
            if not text or not text.strip():
                results.append('')
                continue
            try:
                result = self.translate(text)
                results.append(result)
                print(f"  [{i+1}/{len(texts)}] ✓ {text[:40]}... → {result[:40]}...")
            except Exception as e:
                print(f"  [{i+1}/{len(texts)}] ✗ {text[:40]}... → ERROR: {e}")
                results.append('')  # 失败留空，不阻塞整体流程
            time.sleep(delay)
        return results


# ============================================================
# 百度翻译引擎
# ============================================================
class BaiduTranslator(BaseTranslator):
    """百度翻译 API — 大模型翻译 + Bearer Token 鉴权"""

    API_URL = 'https://fanyi-api.baidu.com/ait/api/aiTextTranslate'

    def __init__(self, appid: str, api_key: str, source_lang='en', target_lang='zh'):
        super().__init__(source_lang, target_lang)
        self.appid = appid
        self.api_key = api_key

    def translate(self, text: str) -> str:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }
        payload = {
            'appid': self.appid,
            'from': self.source,
            'to': self.target,
            'q': text,
        }

        resp = requests.post(self.API_URL, headers=headers, json=payload, timeout=15)
        data = resp.json()

        if 'error_code' in data:
            raise Exception(f"Baidu API error {data['error_code']}: {data.get('error_msg', 'unknown')}")

        return data['trans_result'][0]['dst']


# ============================================================
# 网易有道翻译引擎（预留，需要时填写凭据即可切换）
# ============================================================
class YoudaoTranslator(BaseTranslator):
    """网易有道翻译 API - 待实现"""

    API_URL = 'https://openapi.youdao.com/api'

    def __init__(self, app_id: str, secret_key: str, source_lang='en', target_lang='zh-CHS'):
        super().__init__(source_lang, target_lang)
        self.app_id = app_id
        self.secret_key = secret_key

    def translate(self, text: str) -> str:
        # TODO: 实现有道翻译 API 调用
        raise NotImplementedError("有道翻译引擎待实现，请填写 CREDENTIALS['youdao'] 后完成 translate() 方法")


# ============================================================
# 微软 Azure 翻译引擎（预留）
# ============================================================
class MicrosoftTranslator(BaseTranslator):
    """微软 Azure 翻译 API - 待实现"""

    API_URL = 'https://api.cognitive.microsofttranslator.com/translate?api-version=3.0'

    def __init__(self, api_key: str, region: str, source_lang='en', target_lang='zh-Hans'):
        super().__init__(source_lang, target_lang)
        self.api_key = api_key
        self.region = region

    def translate(self, text: str) -> str:
        # TODO: 实现微软翻译 API 调用
        raise NotImplementedError("微软翻译引擎待实现，请填写 CREDENTIALS['microsoft'] 后完成 translate() 方法")


# ============================================================
# 引擎工厂 - 一键创建
# ============================================================
def create_translator(engine_name: str = None) -> BaseTranslator:
    """根据配置创建翻译引擎实例"""
    engine = engine_name or TRANSLATOR
    creds = CREDENTIALS.get(engine, {})

    if engine == 'baidu':
        return BaiduTranslator(creds['appid'], creds['api_key'])
    elif engine == 'youdao':
        return YoudaoTranslator(creds.get('app_key',''), creds.get('app_secret',''))
    elif engine == 'microsoft':
        return MicrosoftTranslator(creds.get('api_key',''), creds.get('region',''))
    else:
        # 任意第三方引擎，只需在 CREDENTIALS 和此处分发
        raise ValueError(f"未知翻译引擎: {engine}，支持: baidu, youdao, microsoft")


# ============================================================
# 批量翻译工具数据
# ============================================================
def translate_tools(tools_json_path: str, output_path: str = None, delay: float = 1.0):
    """
    批量翻译 tools.json 中的 tagline 和 description
    只翻译 _zh 字段为空的工具（增量更新）
    """
    with open(tools_json_path, 'r', encoding='utf-8') as f:
        tools = json.load(f)

    # 收集需要翻译的文本
    to_translate = []  # [(tool_index, field, text)]
    for i, t in enumerate(tools):
        if not t.get('tagline_zh') and t.get('tagline'):
            to_translate.append((i, 'tagline_zh', t['tagline']))
        if not t.get('description_zh') and t.get('description'):
            to_translate.append((i, 'description_zh', t['description']))

    if not to_translate:
        print("✅ 所有工具已有中文翻译，无需翻译")
        return tools

    print(f"📝 需要翻译 {len(to_translate)} 条文本")

    translator = create_translator()
    print(f"🚀 使用翻译引擎: {translator.name}")

    texts = [item[2] for item in to_translate]
    results = translator.translate_batch(texts, delay=delay)

    # 写回翻译结果
    for (i, field, _), result in zip(to_translate, results):
        if result:
            tools[i][field] = result

    # 保存
    output = output_path or tools_json_path
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(tools, f, ensure_ascii=False, indent=2)

    translated_count = sum(1 for r in results if r)
    print(f"✅ 翻译完成: {translated_count}/{len(results)} 条成功")
    print(f"💾 已保存到: {output}")

    return tools


# ============================================================
# 命令行入口
# ============================================================
if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else 'tools.json'
    translate_tools(path)
