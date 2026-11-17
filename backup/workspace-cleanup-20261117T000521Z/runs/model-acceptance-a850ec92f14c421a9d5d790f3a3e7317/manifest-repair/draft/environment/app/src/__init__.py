"""目录摘要清单生成工具。

本模块提供一个小型 CLI，用于为交付目录生成 JSON 摘要清单：

    python /app/src/manifest.py <input_dir> <output.json>

职责划分：
* ``fs_walk``   —— 遍历输入目录，产出相对路径与文件元信息；
* ``hashing``   —— 根据文件内容计算大小与 SHA-256；
* ``manifest``  —— 组装记录、排序并写出 JSON。
"""

__version__ = "0.3.1"
