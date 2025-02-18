# 生词本 terminal app

## 简介

按照 familiarity 随机采样生词本中的生词。Familiarity=1 表示很熟悉，=5 表示不熟悉。单词发音功能依赖 [`mpg123`](https://www.mpg123.de)；如果没找到但系统为 macOS，则会使用 `osascript` 调用 QuickTime Player。如果既没有安装 `mpg123`，系统也不是 macOS，同时安装时还启用了 `[pronounce]` 功能（见下），安装时会报错。

## 安装

需要 Python>=3.9。

推荐 [`pipx`](https://pipx.pypa.io/stable/) 安装：

```bash
# 启用单词发音功能
pipx install 'vocabnb[pronounce] @ git+https://github.com/kkew3/vocab-notebook.git'
# 否则
pipx install 'vocabnb @ git+https://github.com/kkew3/vocab-notebook.git'
```

亦可新建 python3 虚拟环境然后在其中使用 `pip` 安装，命令同上（只需把 "pipx" 替换为 "pip"）。

## 配置文件示例

见 [`example_config.toml`](./example_config.toml)。

Merriam-Webster API 可以在[这里](https://dictionaryapi.com/products/index)免费获取。

## 使用

通过如下命令开始背单词：

```bash
vocabnb sample
```

### 帮助

执行以下命令以查看帮助:

```bash
vocabnb --help
```

引用如下：

```
Usage: vocabnb [OPTIONS] COMMAND [ARGS]...

  The vocabulary book cli.

Options:
  --help  Show this message and exit.

Commands:
  delete           Delete word definition.
  ls               List all words in arbitrary order.
  query            Query word definition.
  sample           Vocabulary notebook sampler.
  upsert           Upsert word definition by reading word definition...
  upsert-template  Print the yaml template required by `upsert`.
```

## 许可

MIT.
