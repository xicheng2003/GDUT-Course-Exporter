# [GDUT-Course-Exporter] - GDUT教务系统课表导出工具

[![GitHub stars](https://img.shields.io/github/stars/xicheng2003/GDUT-Course-Exporter?style=flat-square)](https://github.com/xicheng2003/GDUT-Course-Exporter)
[![GitHub forks](https://img.shields.io/github/forks/xicheng2003/GDUT-Course-Exporter?style=flat-square)](https://github.com/xicheng2003/GDUT-Course-Exporter/network)
[![LICENSE](https://img.shields.io/github/license/xicheng2003/GDUT-Course-Exporter?style=flat-square)](https://github.com/xicheng2003/GDUT-Course-Exporter/blob/main/LICENSE)

一个通用化、可扩展的Python脚本，可以自动登录高校教务系统，抓取学生个人课表，并生成可供所有日历APP订阅的 `.ics` 格式日历文件。

## ✨ 项目特性

- **两种运行模式**：支持在本地直接运行生成`.ics`文件，也支持通过GitHub Actions实现自动化部署，生成可长期订阅的日历链接。
- **验证码自动识别**：内置[ddddocr](https://github.com/sml2h3/ddddocr)库，可自动识别登录验证码，实现端到端的自动化。
- **高度可扩展**：采用插件化设计，理论上可以轻松扩展以支持任何具有相似流程的教务系统。
- **可靠的解析**：能够智能识别并处理不同环境下（本地 vs. 服务器）返回的多种数据格式。

## 🚀 使用指南

本项目提供两种使用方式，请根据您的需求选择。

### 方案一：本地运行（一次性生成 `.ics` 文件）

适合只想快速获取当前学期课表文件的用户。

**1. 克隆或下载项目**
```bash
git clone https://github.com/xicheng2003/GDUT-Course-Exporter.git
cd GDUT-Course-Exporter
```

**2. 安装依赖**
请确保您已安装 Python 3.8+。
```bash
pip install -r requirements.txt
```

**3. 配置 `config.yml` 文件**
在项目根目录找到 `config.yml` 文件，并根据注释填入您的个人信息。
```yaml
# 学校适配器名称，目前支持: gdut
provider: gdut

# 学期信息
# "202501" 表示2025-2026学年度第一学期
# "20"表示学期总周数，对应抓取20周课表
academic_year_semester: "202501" 
total_semester_weeks: 20

# 用户认证信息 (仅供本地运行)
credentials:
  account: "你的学号"
  password: "你的密码"

# ... 其他配置保持默认即可 ...
```

**4. 运行脚本**
```bash
python run.py
```
运行成功后，您会在项目根目录下找到生成的 `.ics` 文件（默认为 `my_courses.ics`）。您可以将此文件导入到任意日历应用中。

---

### 方案二：自动化部署（生成可订阅的日历链接）

适合希望“一次配置，长期有效”的用户。该方案利用GitHub Actions每日自动更新课表，并生成一个永久有效的订阅链接。

**1. Fork 本项目**
点击本项目页面右上角的 **Fork** 按钮，将项目复制到您自己的GitHub账户下。

**2. 配置仓库机密信息 (Secrets)**
进入您Fork后的仓库，点击 `Settings` -> `Secrets and variables` -> `Actions`。
点击 `New repository secret` 按钮，创建两个机密信息：
- **Name:** `ACCOUNT` -> **Secret:** `（这里填入您的学号）`
- **Name:** `PASSWORD` -> **Secret:** `（这里填入您的教务系统密码）`

**3. 修改 `config.yml`**
在您的仓库中，直接编辑 `config.yml` 文件。对于自动化部署，您**只需确保 `provider`、`academic_year_semester` 和 `total_semester_weeks` 等信息正确即可**。`credentials` 部分无需理会，程序会优先使用您在第二步中设置的Secrets。

**4. 启用 Actions 和 Pages**
- **Actions**: 通常在您Fork并修改文件后，GitHub Actions会自动启用。您可以在仓库的 `Actions` 标签页查看。如果未启用，请根据提示点击启用。
- **Pages**: 进入仓库的 `Settings` -> `Pages` 页面。在 `Build and deployment` -> `Branch` 下，选择 `gh-pages` 分支，然后点击 `Save`。

**5. 获取订阅链接**
等待1-2分钟，刷新Pages设置页面。GitHub会在此页面顶部提供您的日历订阅链接，格式为：
`https://<你的GitHub用户名>.github.io/<你的仓库名>/my_courses.ics`

将此链接添加到您的日历应用中，即可实现课表的自动同步与更新。

## 🤝 如何贡献

欢迎所有形式的贡献！尤其是帮助项目支持更多的学校。

### 添加新学校适配器

1.  在 `providers/` 目录下，参考 `gdut.py` 创建一个新的学校文件，例如 `new_school.py`。
2.  在该文件中，定义一个 `NEW_SCHOOL_PROVIDER` 字典，包含该校的`base_url`、`class_time_map`以及任何特殊的加密函数。
3.  在本地修改 `config.yml` 的 `provider` 为 `new_school` 进行测试。
4.  测试通过后，欢迎您提交 Pull Request！

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 开源。