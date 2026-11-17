# 归档交付样例数据（仅用于展示目录结构）

本目录模拟一次本地归档交付的内容：

```
archive/
├── README.txt               # 本说明，档案号 sample-001
├── assets/
│   ├── img/
│   │   └── pixel.png
│   └── logo 小图.bin        # 二进制字节
├── docs/
│   ├── README.md            # 与 2023/README.md 同名但内容不同
│   ├── 2023/
│   │   └── README.md        # 第三层同名文件
│   ├── notes.txt            # 空文件
│   └── 老项目/
│       └── 说明.txt
├── empty_dir/
│   └── inner/               # 空目录，不含文件
└── logs/
    ├── app 2024-01.log      # 文件名含空格
    └── raw.bin              # 含非 UTF-8 字节的二进制内容
```

自测时也可以在系统临时目录下自行构造类似的小目录再运行清单命令。
