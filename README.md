# SakuraMedia 插件市场

SakuraMedia 插件市场的索引仓库。SakuraMedia 客户端在「系统设置 → 插件 → 插件市场」读取本仓库的 [`index.json`](index.json)，展示插件列表、下载安装包并一键安装或更新。

- 默认市场源：`https://raw.githubusercontent.com/tinypinglite/sakuramedia-plugin-market/main/index.json`
- 插件在 SakuraMedia 后端进程内运行。官方插件以编译产物经本仓库 Release 分发，社区插件收录其公开仓库的 Release 安装包。

## 收录政策

- 收录**官方**与**社区**插件；官方插件标记 `official: true`，社区插件标记 `official: false`。
- 官方插件由维护者在私有 monorepo 编译，以 `.zip`（含 linux/amd64 与 linux/arm64 两个 `.so`）发布在本仓库的 Release，源码不公开；元数据 `source` 为 `market`。
- 社区插件仓库必须公开，Release 必须提供根目录含 `manifest.json` 的 `.zip` 安装包，且 `manifest.plugin_id` 与 `version` 和 Release tag 一致；元数据 `source` 缺省或为 `external`。
- 社区插件不收录私有仓库、来源不明或包含恶意行为的插件。
- 插件必须使用与宿主兼容的许可证。由于插件在宿主进程内运行，推荐直接使用 PolyForm Noncommercial License 1.0.0；使用其他许可证需经维护者书面确认兼容。

## 官方插件

官方插件源码维护在私有 monorepo `tinypinglite/sakuramedia-official-plugins`，不在本仓库。

- 每个插件对应一个 GitHub Release，tag 为 `<plugin_id>-v<version>`；Action 只构建该插件，不会因为改一个插件而重发所有插件。
- 构建在 `python:3.10-slim-bookworm` 内用 Nuitka 编译，同时产出 linux/amd64 与 linux/arm64 的 `.so`，打进同一个 zip。
- 产物自动上传到本仓库同名 Release，并更新 `plugins/<plugin_id>.json`、`releases/<plugin_id>.json` 与 `index.json`。
- `releases/<plugin_id>.json` 由 GitHub Pages 以 `application/json` 提供，客户端「检查更新」读取该地址。

官方插件的 zip 只包含 `__init__.py` shim、双架构 `.so`、`manifest.json`、`i18n/` 等运行资源，不含业务 `.py` 源码。

## 上架插件

1. Fork 本仓库，在 `plugins/` 下新增 `<plugin_id>.json`（文件名必须与 `plugin_id` 完全一致）：

   ```json
   {
     "plugin_id": "sakuramedia_example",
     "display_name": "示例插件",
     "description": "一句话说明插件用途，不超过 200 字。",
     "author": "你的名字",
     "repo": "your-name/your-plugin-repo",
     "homepage": "https://github.com/your-name/your-plugin-repo",
     "categories": ["other"],
     "official": false
   }
   ```

2. 社区插件的 `latest` 字段不要手写：索引维护流程会每天自动从仓库的最新 Release 同步版本号、下载地址和 sha256。版本号必须是 `x.y.z` 三段格式，Release 里只放一个 `.zip` 插件包（可附带 `.sha256` 文件）。`source` 可省略，缺省按 `external` 处理。
3. 向本仓库提交 Pull Request，说明插件用途与仓库地址；官方插件由维护者通过私有 monorepo 的发版 Action 自动写入，不接受外部 PR 修改。

分类可选值：`storage`（存储 / 下载）、`metadata`（元数据）、`discovery`（榜单 / 发现）、`automation`（自动化任务）、`subtitle`（字幕）、`other`。

字段完整定义见 [`schema/plugin.schema.json`](schema/plugin.schema.json)。

## 多语言元数据

插件名称与简介的多语言文案以**插件 manifest 为唯一事实源**：插件在 `manifest.json` 里声明
`display_name_i18n` 与 `description` / `description_i18n`，索引维护流程在同步 Release 时把它们搬进
`plugins/<plugin_id>.json` 与 `index.json`。

- `display_name` / `description`：原文（通常是中文）。manifest 声明了就以 manifest 为准，没声明就保留市场里已有的文案。
- `display_name_i18n` / `description_i18n`：可选字典，键为语言标签（`zh-CN` / `en`）。manifest 声明了就整块同步，没声明就删掉该键。
- 这四个字段由脚本自动写入，**投稿时不要手写**；要改文案就改插件 manifest 并发一版，索引会自动跟上。
- 客户端按「当前语言 → `zh-CN` → 原文」的顺序取值；没有多语言文案的插件在英文界面下仍显示原文。

## 索引生成

`index.json` 由 [`scripts/build_index.py`](scripts/build_index.py) 生成：

```bash
GITHUB_TOKEN=xxx python3 scripts/build_index.py
```

脚本对 `plugins/` 下的每个插件按 `source` 分流：

- `source=external`（社区，缺省）：查询 `repo` 的最新 Release，下载 `.zip` 包，校验 `plugin_id`、`version` 与 tag 一致，计算 sha256 并回写 `latest`；
- `source=market`（官方）：不再查询外部仓库，直接下载已提交的 `latest.download_url`，校验 `latest.sha256`、包内 manifest 的 `plugin_id` / `version` / `host_api_version` 与 `latest` 一致；
- 两种来源都会把 manifest 里的展示名与简介（含多语言版本）同步进元数据，manifest 没声明的文案保留市场原值；
- 汇总所有插件重新生成 `index.json`。

`--only <plugin_id>` 只同步指定插件，但仍用全部插件元数据重建 `index.json`；官方发版 Action 用它避免每次发版都查询所有社区仓库。

任一插件失败时不写入任何文件，避免市场出现半截数据。客户端安装前会下载校验 sha256。

## 手动安装

不使用插件市场时，官方插件可从本仓库的 Release 页面下载 `.zip`，社区插件从其公开仓库的 Release 页面下载，然后在「系统设置 → 插件」手动上传安装。安装或更新后需要重启 SakuraMedia 容器。

## 安全提示

插件会在 SakuraMedia 后端进程内运行，拥有宿主开放的全部能力。请只安装可信来源的插件；官方插件是编译产物，无法直接审计源码；社区插件以源码发布且未经官方审计，安装前建议先阅读其源码。
## License

本项目采用 [PolyForm Noncommercial License 1.0.0](./LICENSE)，仅允许非商业用途。

Copyright (C) 2026 tinypinglite
