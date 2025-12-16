#!/usr/bin/env python3
"""
BettaFish 爬虫关键词覆盖率检查工具
用于验证各平台是否成功爬取了 daily_topics 中指定的所有关键词
"""

import psycopg2
import json
from typing import Dict, List, Set, Tuple
from collections import defaultdict

# 数据库配置
DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 5432,
    'database': 'bettafish',
    'user': 'bettafish',
    'password': 'bettafish'
}

# 平台表映射
PLATFORM_TABLES = {
    'zhihu': 'zhihu_content',
    'weibo': 'weibo_note',
    'kuaishou': 'kuaishou_video',
    'bili': 'bilibili_video',
    'douyin': 'douyin_aweme',
    'xhs': 'xhs_note',
    'tieba': 'tieba_note'
}

# 平台中文名
PLATFORM_NAMES = {
    'zhihu': '知乎',
    'weibo': '微博',
    'kuaishou': '快手',
    'bili': 'B站',
    'douyin': '抖音',
    'xhs': '小红书',
    'tieba': '贴吧'
}


def get_db_connection():
    """创建数据库连接"""
    return psycopg2.connect(**DB_CONFIG)


def get_expected_keywords(topic_id: str) -> Tuple[str, Set[str]]:
    """
    获取话题的期望关键词集合
    返回: (topic_name, expected_keywords_set)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT topic_name, keywords FROM daily_topics WHERE topic_id = %s",
            (topic_id,)
        )
        result = cursor.fetchone()

        if not result:
            raise ValueError(f"Topic ID '{topic_id}' not found in daily_topics")

        topic_name, keywords_json = result
        keywords_list = json.loads(keywords_json)

        # 归一化：去除首尾空格
        expected_set = {kw.strip() for kw in keywords_list}

        return topic_name, expected_set

    finally:
        cursor.close()
        conn.close()


def get_platform_keywords(topic_id: str, platform: str, table_name: str) -> Set[str]:
    """
    获取指定平台实际爬取的关键词集合
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        query = f"""
            SELECT DISTINCT source_keyword
            FROM {table_name}
            WHERE topic_id = %s AND source_keyword IS NOT NULL
        """
        cursor.execute(query, (topic_id,))
        results = cursor.fetchall()

        # 归一化：去除首尾空格
        hit_set = {row[0].strip() for row in results if row[0]}

        return hit_set

    except Exception as e:
        print(f"⚠️ 查询 {platform} 时出错: {e}")
        return set()

    finally:
        cursor.close()
        conn.close()


def check_coverage(topic_id: str, platforms: List[str] = None) -> Dict:
    """
    检查指定话题在各平台的关键词覆盖情况

    Args:
        topic_id: 话题ID (如 'star_rail_3_7')
        platforms: 要检查的平台列表，默认检查所有平台

    Returns:
        包含覆盖率信息的字典
    """
    if platforms is None:
        platforms = list(PLATFORM_TABLES.keys())

    # 获取期望关键词
    topic_name, expected_set = get_expected_keywords(topic_id)
    expected_count = len(expected_set)

    print(f"\n{'='*80}")
    print(f"📊 话题覆盖率检查报告")
    print(f"{'='*80}")
    print(f"话题ID: {topic_id}")
    print(f"话题名称: {topic_name}")
    print(f"期望关键词数: {expected_count}")
    print(f"{'='*80}\n")

    results = {}

    for platform in platforms:
        if platform not in PLATFORM_TABLES:
            print(f"⚠️ 未知平台: {platform}")
            continue

        table_name = PLATFORM_TABLES[platform]
        platform_name = PLATFORM_NAMES[platform]

        # 获取该平台实际爬取的关键词
        hit_set = get_platform_keywords(topic_id, platform, table_name)

        # 计算匹配、缺失、意外关键词
        matched = expected_set & hit_set  # 交集
        missing = expected_set - hit_set  # 期望但未命中
        unexpected = hit_set - expected_set  # 命中但不在期望中

        matched_count = len(matched)
        missing_count = len(missing)
        unexpected_count = len(unexpected)

        # 计算覆盖率
        coverage_rate = (matched_count / expected_count * 100) if expected_count > 0 else 0

        # 状态判断
        if coverage_rate == 100:
            status = '✅ 完美'
        elif coverage_rate >= 80:
            status = '✅ 良好'
        elif coverage_rate >= 50:
            status = '⚠️ 一般'
        elif coverage_rate > 0:
            status = '❌ 较差'
        else:
            status = '❌ 失败'

        results[platform] = {
            'platform_name': platform_name,
            'matched_count': matched_count,
            'missing_count': missing_count,
            'unexpected_count': unexpected_count,
            'coverage_rate': coverage_rate,
            'status': status,
            'matched': matched,
            'missing': missing,
            'unexpected': unexpected
        }

        # 打印平台报告
        print(f"【{platform_name}】 {status}")
        print(f"  覆盖率: {coverage_rate:.1f}% ({matched_count}/{expected_count})")
        print(f"  匹配关键词: {matched_count} 个")
        print(f"  缺失关键词: {missing_count} 个")
        if unexpected_count > 0:
            print(f"  ⚠️ 意外关键词: {unexpected_count} 个 (可能是数据归一化问题)")
        print()

    return results


def print_missing_keywords(results: Dict):
    """打印各平台的缺失关键词详细清单"""
    print(f"\n{'='*80}")
    print(f"📋 缺失关键词详细清单")
    print(f"{'='*80}\n")

    for platform, data in results.items():
        if data['missing_count'] > 0:
            platform_name = data['platform_name']
            print(f"【{platform_name}】缺失 {data['missing_count']} 个关键词:")
            for i, kw in enumerate(sorted(data['missing']), 1):
                print(f"  {i}. {kw}")
            print()
        else:
            print(f"【{data['platform_name']}】✅ 无缺失关键词\n")


def print_unexpected_keywords(results: Dict):
    """打印各平台的意外关键词清单（用于发现脏数据）"""
    has_unexpected = any(data['unexpected_count'] > 0 for data in results.values())

    if not has_unexpected:
        return

    print(f"\n{'='*80}")
    print(f"⚠️ 意外关键词清单 (不在期望列表中)")
    print(f"{'='*80}\n")

    for platform, data in results.items():
        if data['unexpected_count'] > 0:
            platform_name = data['platform_name']
            print(f"【{platform_name}】发现 {data['unexpected_count']} 个意外关键词:")
            for i, kw in enumerate(sorted(data['unexpected']), 1):
                print(f"  {i}. {kw}")
            print()


def list_available_topics():
    """列出所有可用的话题"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT topic_id, topic_name, extract_date,
                   jsonb_array_length(keywords::jsonb) as keyword_count
            FROM daily_topics
            ORDER BY extract_date DESC
        """)
        results = cursor.fetchall()

        print(f"\n{'='*80}")
        print(f"📚 可用话题列表")
        print(f"{'='*80}\n")

        for topic_id, topic_name, extract_date, kw_count in results:
            print(f"  • {topic_id}")
            print(f"    名称: {topic_name}")
            print(f"    日期: {extract_date}")
            print(f"    关键词数: {kw_count}")
            print()

    finally:
        cursor.close()
        conn.close()


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='BettaFish 爬虫关键词覆盖率检查工具')
    parser.add_argument('topic_id', nargs='?', help='话题ID (如 star_rail_3_7)')
    parser.add_argument('-p', '--platforms', nargs='+',
                       choices=list(PLATFORM_TABLES.keys()),
                       help='指定要检查的平台 (默认检查所有平台)')
    parser.add_argument('-l', '--list', action='store_true',
                       help='列出所有可用话题')
    parser.add_argument('-d', '--detail', action='store_true',
                       help='显示缺失关键词详细清单')
    parser.add_argument('-u', '--unexpected', action='store_true',
                       help='显示意外关键词清单')

    args = parser.parse_args()

    # 列出话题
    if args.list:
        list_available_topics()
        return

    # 检查覆盖率
    if not args.topic_id:
        print("错误: 请提供 topic_id 参数，或使用 -l 列出可用话题")
        print("\n使用示例:")
        print("  python check_coverage.py star_rail_3_7")
        print("  python check_coverage.py star_rail_3_7 -p bili zhihu")
        print("  python check_coverage.py star_rail_3_7 -d")
        print("  python check_coverage.py -l")
        return

    try:
        results = check_coverage(args.topic_id, args.platforms)

        if args.detail:
            print_missing_keywords(results)

        if args.unexpected:
            print_unexpected_keywords(results)

        # 总结
        print(f"{'='*80}")
        print(f"✅ 检查完成")
        print(f"{'='*80}\n")

    except ValueError as e:
        print(f"❌ 错误: {e}")
    except Exception as e:
        print(f"❌ 未知错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
