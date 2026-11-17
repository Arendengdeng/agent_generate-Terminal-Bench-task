"""Six distinct immutable specifications derived from the existing examples."""
import copy
from pathlib import Path

from synthesis_agent.files import read_json
from synthesis_agent.inputs import validate_inputs


def default_specs(project):
    specs = []
    for family in ('csv', 'jsonl', 'manifest'):
        source = Path(project) / 'examples' / (family + '-repair')
        base = {'id': family + '-original', 'family': family, 'variant': 'original',
                'source': str(source), 'plan': read_json(source / 'plan.json'),
                'contract': read_json(source / 'contract.json')}
        specs.append(base)
        variant = copy.deepcopy(base)
        variant.update(id=family + '-variant', variant='variant')
        c, p = variant['contract'], variant['plan']
        if family == 'csv':
            goal = '修复 CSV 清洗工具，按归一化邮箱保留最后一次姓名，按邮箱首次出现顺序输出。'
            c['output_spec'] = ('UTF-8 CSV，表头为 email,name。邮箱去掉首尾空白后转小写；姓名仅去掉首尾空白。'
                '按归一化邮箱去重，姓名使用该邮箱最后一条记录的姓名；输出顺序为各邮箱首次出现顺序；使用 CSV 转义规则。')
            c['requirements'][1]['description'] = ('归一化邮箱后去重，保留最后一次姓名，但按邮箱首次出现顺序输出；'
                '正确处理空白、大小写以及带引号和逗号的字段。')
        elif family == 'jsonl':
            goal = '修复 JSONL 聚合工具，仅按 service 分组，统计条数、总耗时及最大耗时。'
            c['output_spec'] = ('UTF-8 JSON 数组；每个实际出现的 service 对应一个对象，恰含 service、count、'
                'total_duration_ms、max_duration_ms。统计该服务所有级别的记录数、耗时之和及最大耗时。'
                '按 service 的 Python 字符串升序排列；空输入输出 []。')
            c['requirements'][1]['description'] = '仅按 service 分组，跨 level 统计条数、总耗时与最大耗时，不丢失重复记录。'
        else:
            goal = '修复目录摘要 CLI，递归按文件内容分组并输出各组路径、字节数和 SHA-256。'
            c['output_spec'] = ('UTF-8 JSON 数组，每个不同 SHA-256 摘要对应一个对象，恰含 size、sha256、paths。'
                'size 为该组文件内容字节数，sha256 为 64 位小写十六进制 SHA-256；paths 包含该摘要所有普通文件'
                '相对 input_dir 的 POSIX 路径，按 Python 字符串升序排列。各对象按 sha256 升序排列；'
                '忽略目录，空目录输出 []。本任务按 SHA-256 相等定义同组。')
            c['requirements'][1]['description'] = '递归遍历全部普通文件，按 SHA-256 分组，保留全部相对路径，包括嵌套同名、空格和 Unicode 文件名。'
            c['requirements'][2]['description'] = '按实际二进制内容计算字节数和 SHA-256；空文件和非 UTF-8 内容正确；组内路径与组间摘要分别升序，空目录输出 []。'
        p.update(title=goal, goal=goal)
        c['objective'] = goal
        specs.append(variant)
    return validate_specs(specs)


def validate_specs(specs):
    if not isinstance(specs, list) or not 5 <= len(specs) <= 10:
        raise ValueError('batch requires 5–10 task specifications')
    ids = set()
    contracts = set()
    import json
    import re
    for spec in specs:
        ident = spec['id']
        if not isinstance(ident, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', ident) or ident in ids:
            raise ValueError('task IDs must be unique lowercase path-safe identifiers')
        ids.add(ident)
        if spec['family'] not in {'csv', 'jsonl', 'manifest'} or spec['variant'] not in {'original', 'variant'}:
            raise ValueError('unsupported control recipe')
        validate_inputs(spec['plan'], spec['contract'])
        key = json.dumps(spec['contract'], sort_keys=True, ensure_ascii=False)
        if key in contracts:
            raise ValueError('each candidate must have a distinct Contract')
        contracts.add(key)
    return specs
