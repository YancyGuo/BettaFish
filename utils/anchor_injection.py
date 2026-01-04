"""
分析对象锚点提取与注入工具（BETTAFISH B+C格式专用）

核心功能：
1. 解析META和KEYWORDS块
2. 构造给LLM1的去噪+锚定prompt
3. 对LLM1输出的paragraph.content进行兜底注入

设计原则：
- 新格式（B+C）为主路径，直接用META字段
- 只在META缺失时才用兜底策略
- 保持逻辑简单、清晰

版本：2025-01-04 优化版
"""

import json
import re
from typing import Dict, List, Tuple, Optional
from loguru import logger

# B+C 块标记
KEYWORDS_BEGIN = "===BETTAFISH_KEYWORDS_BEGIN==="
KEYWORDS_END = "===BETTAFISH_KEYWORDS_END==="
META_BEGIN = "===BETTAFISH_META_BEGIN==="
META_END = "===BETTAFISH_META_END==="


def _extract_block(text: str, begin: str, end: str) -> Optional[str]:
    """提取被标记包围的块内容

    支持两种格式:
    1. 块标记独占行: BEGIN\n内容\nEND
    2. 块标记和内容同行: BEGIN 内容 END
    """
    # 尝试多行格式: BEGIN\n内容\nEND
    pattern_multiline = re.escape(begin) + r"\s*\n(.*?)\n\s*" + re.escape(end)
    match = re.search(pattern_multiline, text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()

    # 尝试单行格式: BEGIN 内容 END
    pattern_oneline = re.escape(begin) + r"\s+(.*?)\s+" + re.escape(end)
    match = re.search(pattern_oneline, text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()

    return None


def _remove_block(text: str, begin: str, end: str) -> str:
    """从文本中移除指定的块

    支持两种格式:
    1. 块标记独占行: BEGIN\n内容\nEND
    2. 块标记和内容同行: BEGIN 内容 END
    """
    # 尝试多行格式
    pattern_multiline = re.escape(begin) + r"\s*\n.*?\n\s*" + re.escape(end)
    result = re.sub(pattern_multiline, "", text, flags=re.DOTALL)

    # 如果没有匹配多行格式，尝试单行格式
    if result == text:
        pattern_oneline = re.escape(begin) + r"\s+.*?\s+" + re.escape(end)
        result = re.sub(pattern_oneline, "", text, flags=re.DOTALL)

    return result.strip()


def parse_meta_block(raw: str) -> Dict[str, str]:
    """
    解析BETTAFISH_META块（只做解析，不做推断）

    支持两种格式:
    1. 多行格式:
       ===BETTAFISH_META_BEGIN===
       TARGET_GAME_CN: 二重螺旋
       GAME_EN_NAME: Duet Night Abyss
       ...
       ===BETTAFISH_META_END===

    2. 单行格式:
       ===BETTAFISH_META_BEGIN=== TARGET_GAME_CN: 二重螺旋 VERSION_CODE: 1.0 ... ===BETTAFISH_META_END===

    核心算法: 按KEY位置切片，兼容单行/多行/中英混排
    - 找到所有 KEY: 的位置
    - 把相邻key之间的内容当作value
    - value可以是任何字符(中文/英文/数字/括号/空格等)

    Returns:
        字典，键值对为META中的字段
    """
    meta: Dict[str, str] = {}
    block_content = _extract_block(raw, META_BEGIN, META_END)

    if not block_content:
        logger.debug("未找到BETTAFISH_META块")
        return meta

    text = block_content.strip()

    # 找到所有 KEY: 的位置 (KEY格式: 大写字母开头，可含数字和下划线)
    key_matches = list(re.finditer(r'([A-Z][A-Z0-9_]*)\s*:\s*', text))

    if not key_matches:
        logger.warning("META块中未找到任何键值对")
        return meta

    # 按KEY位置切片提取value
    for i, m in enumerate(key_matches):
        key = m.group(1).strip()
        val_start = m.end()
        val_end = key_matches[i + 1].start() if i + 1 < len(key_matches) else len(text)
        value = text[val_start:val_end].strip()
        if key:
            meta[key] = value

    logger.debug(f"解析到META: {meta}")
    return meta


def parse_keywords_block(raw: str) -> List[str]:
    """
    解析BETTAFISH_KEYWORDS块（只做解析，不做推断）

    格式示例:
    ===BETTAFISH_KEYWORDS_BEGIN===
    ["二重螺旋1.0", "二重螺旋 于新日启程", "Duet Night Abyss 1.0", ...]
    ===BETTAFISH_KEYWORDS_END===

    Returns:
        关键词列表
    """
    block_content = _extract_block(raw, KEYWORDS_BEGIN, KEYWORDS_END)

    if not block_content:
        logger.debug("未找到BETTAFISH_KEYWORDS块")
        return []

    try:
        keywords = json.loads(block_content)
        if not isinstance(keywords, list) or not all(isinstance(x, str) for x in keywords):
            raise ValueError("BETTAFISH_KEYWORDS块必须是字符串数组")
        logger.debug(f"解析到{len(keywords)}个关键词")
        return keywords
    except json.JSONDecodeError as e:
        logger.error(f"解析KEYWORDS JSON失败: {e}")
        return []


def _normalize_unknown(s: str) -> str:
    """将UNKNOWN或空字符串规范化为空"""
    return "" if not s or s.strip().upper() == "UNKNOWN" else s.strip()


def extract_target_and_aliases(query: str) -> Tuple[str, List[str], str, Dict[str, str]]:
    """
    提取分析对象、别名和版本信息

    新格式（B+C）主路径：
    - 直接从META块读取TARGET_GAME_CN、VERSION_CODE等
    - 只在META缺失时才用兜底策略

    Args:
        query: 完整的用户查询（可能包含B+C块）

    Returns:
        (target_name, aliases, version, meta_dict)
    """
    # 解析META块
    meta = parse_meta_block(query)

    # 主路径：直接用META字段（新格式）
    target = _normalize_unknown(meta.get("TARGET_GAME_CN", ""))
    version = _normalize_unknown(meta.get("VERSION_CODE", ""))

    # 别名列表
    aliases: List[str] = []

    # 英文名
    en_name = _normalize_unknown(meta.get("GAME_EN_NAME", ""))
    if en_name:
        aliases.append(en_name)

    # 昵称（逗号/顿号/空格分隔）
    nicknames = _normalize_unknown(meta.get("GAME_NICKNAMES", ""))
    if nicknames:
        for nickname in re.split(r"[，,、\s]+", nicknames):
            nickname = nickname.strip()
            if nickname and nickname.upper() != "UNKNOWN" and nickname not in aliases:
                aliases.append(nickname)

    # 只有在META缺失target时才用兜底策略
    if not target:
        logger.warning("META块缺少TARGET_GAME_CN，尝试兜底提取")

        # 兜底策略1: 正文显式声明
        patterns = [
            r'本次分析对象为[「《](.+?)[」》]',
            r'分析对象为[「《](.+?)[」》]',
        ]
        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                target = match.group(1).strip()
                logger.info(f"[兜底-显式声明] 提取到target={target}")
                break

        # 兜底策略2: 从KEYWORDS首项反推（如果仍然没有）
        if not target:
            keywords = parse_keywords_block(query)
            if keywords:
                first_keyword = keywords[0]
                # 去掉版本号尾巴："二重螺旋1.0" -> "二重螺旋"
                target = re.sub(r"[\s\-]*\d+(\.\d+)?.*?$", "", first_keyword).strip()
                logger.info(f"[兜底-关键词] 从'{first_keyword}'提取到target={target}")

    # 只有在META缺失version时才用兜底
    if not version:
        version_match = re.search(r"(\d+\.\d+|\d+)\s*版本", query)
        if version_match:
            version = version_match.group(1)
            logger.debug(f"[兜底] 从正文提取version={version}")

    logger.info(f"最终提取结果 - target={target}, aliases={aliases}, version={version}")
    return (target, aliases, version, meta)


def build_llm1_prompt(query: str) -> str:
    """
    构造给LLM1（结构规划节点）的去噪+锚定prompt

    处理步骤：
    1. 从query中提取META和KEYWORDS块
    2. 移除这两个块，得到纯净的用户正文
    3. 构造锚定信息头部
    4. 拼接返回

    Args:
        query: 原始B+C格式查询

    Returns:
        处理后的prompt（锚定头部 + 用户正文）

    Example:
        输入: B+C格式的长query
        输出:
        【分析对象锚定】
        游戏：二重螺旋（别名/昵称：Duet Night Abyss）
        版本：1.0（于新日启程）
        时间：2024-12-01 ~ 2024-12-31

        【用户任务说明正文】
        本次分析...（去掉块后的正文）
    """
    # 提取信息
    target, aliases, version, meta = extract_target_and_aliases(query)

    # 移除块，得到纯净正文
    body = query.strip()
    body = _remove_block(body, KEYWORDS_BEGIN, KEYWORDS_END)
    body = _remove_block(body, META_BEGIN, META_END)

    # 构造锚定头部
    alias_text = f"（别名/昵称：{', '.join(aliases)}）" if aliases else ""

    version_title = _normalize_unknown(meta.get("VERSION_TITLE", ""))
    version_title_text = f"（{version_title}）" if version_title else ""

    launch_date = _normalize_unknown(meta.get("LAUNCH_DATE", ""))
    end_date = _normalize_unknown(meta.get("END_DATE", ""))
    time_range = f"{launch_date} ~ {end_date}" if launch_date or end_date else "UNKNOWN"

    header = (
        "【分析对象锚定】\n"
        f"游戏：{target}{alias_text}\n"
        f"版本：{version}{version_title_text}\n"
        f"时间：{time_range}\n\n"
        "【用户任务说明正文】\n"
    )

    result = header + body
    logger.info(f"构造LLM1 prompt，锚定信息: 游戏={target}, 版本={version}")
    return result


def inject_target_to_content(content: str, target: str, aliases: List[str], version: str) -> str:
    """
    在paragraph.content开头注入锚定句（如果不包含target）

    Args:
        content: 原始paragraph.content
        target: 分析对象名称
        aliases: 别名列表
        version: 版本号

    Returns:
        注入后的content

    Example:
        输入: "分析玩家在1.0版本公测前..."
        输出: "本段聚焦于《二重螺旋》（Duet Night Abyss）1.0版本相关讨论。\n分析玩家在1.0版本公测前..."
    """
    if not target:
        logger.warning("target为空，跳过注入")
        return content

    # 检查前160字符是否已包含target或任一别名
    check_range = content[:160]
    all_names = [target] + [a for a in aliases if a]

    if any(name in check_range for name in all_names):
        logger.debug(f"content开头已包含分析对象，无需注入")
        return content

    # 构造注入句
    version_text = f"{version}版本" if version else ""
    alias_text = f"（{aliases[0]}）" if aliases else ""
    prefix = f"本段聚焦于《{target}》{alias_text}{version_text}相关讨论。\n"

    logger.info(f"兜底注入锚定句: {prefix.strip()}")
    return prefix + content
