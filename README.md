# TikTok Drama Center 批量上传工具

## 功能

- 读取 `export_*.xlsx` 中的剧集信息
- 自动下载封面图与视频到本地
- 在 Edge 浏览器中批量创建 draft、填写表单、上传视频、保存

## 环境要求

- Windows 10/11
- Python 3.12（已安装）
- 系统已安装 Microsoft Edge

## 安装

```bash
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

如果 Chromium 内核未安装，可执行：

```bash
.venv/Scripts/python.exe -m playwright install chromium
```

（实际运行使用系统 Edge，Chromium 仅作备用。）

## 首次登录

持久化登录态保存在 `./browser_data`。如果尚未登录，先运行分析脚本完成登录：

```bash
.venv/Scripts/python.exe analyze_page.py
```

按提示在弹出的 Edge 窗口中登录 TikTok，回到终端按回车抓取字段即可。

## 运行上传

处理 Excel 中全部剧集：

```bash
.venv/Scripts/python.exe upload.py
```

仅测试前 1 部剧：

```bash
.venv/Scripts/python.exe upload.py --limit 1
```

指定其他 Excel：

```bash
.venv/Scripts/python.exe upload.py path/to/your.xlsx
```

## 输入文件说明

### export_*.xlsx

| 列名 | 用途 |
|---|---|
| 原剧名 | 保留 |
| 原简介 | 保留 |
| 作者 | 保留 |
| 分类 | 保留（不用于表单） |
| 原海报URL | 保留 |
| 翻译语言 | 保留 |
| 翻译后剧名 | 表单「剧集名」 |
| 翻译后简介 | 表单「剧集描述」 |
| 新海报URL | 表单「封面图」 |
| 剧集数 | 表单「总集数」 |
| 剧集 URL | 该剧全部视频 URL，以换行分隔 |

### attr_require.txt

已固化为代码中的默认值：

- 免费预览集数：8
- 个人页剧集展示集数：3
- 目标人群：男性
- 源语言：中文
- 是否 AI 短剧：是
- 托管模式：开启
- 版权自查承诺：勾选
- 发布方式：过审后自动发布
- 保存（不提交）

## 输出

- `./downloads/`：下载的封面与视频缓存
- `./errors/row_<行号>.png`：失败时的页面截图
- 终端打印成功/失败汇总

## 注意事项

- 每部剧独立占用一个浏览器 Tab，最多 10 个 Tab 并行。
- 脚本从 `series/list` 点击「新建」为每部剧创建独立 draft。
- 表单包含自定义下拉框和文件上传，运行过程中请勿手动操作浏览器窗口，以免干扰自动化。
