# 生词本 terminal app

## Introduction 简介

按照 familiarity 随机采样生词本中的生词.
Familiarity=1 表示很熟悉, =5 表示不熟悉.
单词发音功能目前仅限 macOS 系统.

## Installation 安装

首先, 阅读 `requirements.txt`, 注释掉你不需要的依赖, 然后 (推荐在虚拟环境中),

```bash
pip install -r requirements.txt
```

最后,

```bash
pip install .
```

## Configuration example 配置文件示例

见 `example_config.toml`.

## Vocabulary book example 单词表示例

见 `example_vocab_notebook.tsv`.

## Help 帮助

执行以下命令以查看帮助:

```bash
python3 -m vocabnb --help
```
