
# 打包 Tag 流程（Git 操作规范）

## 1. 准备工作（在 main 分支上操作）

确保当前处于 `main` 分支且已拉取最新代码：

```bash
git checkout main
git pull origin main
```

## 2. 更新 CHANGELOG.md

在 `CHANGELOG.md` 中：
- 将 `[Unreleased]` 部分的内容移动到新版本标题下（如 `[v0.3.0]`）
- 更新版本日期
- 清空 `[Unreleased]` 部分（保留标题和分类）

提交 CHANGELOG 更新：

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): 更新 v0.3.0 版本说明"
git push origin main
```

## 3. 创建 Annotated Tag

使用以下命令创建带描述的 Annotated Tag：

```bash
git tag -a v0.3.0 -m "Release v0.3.0

新增：
- MPS 多进程支持（单卡最高 32 进程）
- ParMesh 分区支持（default/metis/cartesian）

修复：
- ParMesh 稳定性问题

变更：
- 输出路径统一迁移至 build/test"
```

## 4. 推送 Tag 到 GitHub

```bash
git push origin v0.3.0
```

或一次性推送所有本地 Tag：

```bash
git push origin --tags
```

## 5. 在 GitHub 上创建 Release（推荐）

1. 打开 GitHub 仓库 → **Releases** → **Draft a new release**
2. **Tag version**：选择 `v0.3.0`
3. **Release title**：填写 `v0.3.0` 或 `v0.3.0 - MPS 多进程支持与 ParMesh 改进`
4. **Describe this release**：粘贴 CHANGELOG.md 中 `v0.3.0` 对应的内容
5. **Set as a pre-release**：根据实际情况选择（正式版本通常不勾选）
6. 点击 **Publish release**

## 推荐完整流程脚本（一次性执行）

```bash
#!/bin/bash
VERSION="v0.3.0"

# 切换到 main 并更新
git checkout main
git pull origin main

# 提交 CHANGELOG（请确保已手动更新）
git add CHANGELOG.md
git commit -m "docs(changelog): 更新 ${VERSION} 版本说明" || echo "CHANGELOG 无需提交"

# 创建 Annotated Tag
git tag -a ${VERSION} -m "Release ${VERSION}

新增：
- MPS 多进程支持
- ParMesh 分区支持

修复：
- ParMesh 稳定性修复

变更：
- 输出路径迁移至 build/test"

# 推送 Tag
git push origin ${VERSION}

echo "Tag ${VERSION} 已创建并推送成功！"
echo "请前往 GitHub Releases 页面创建 Release 说明。"
```

**注意事项**：
- 每次发布正式版本前，必须先更新 `CHANGELOG.md`
- 强烈推荐使用 Annotated Tag（`-a` 参数），便于保留发布信息
- Tag 一旦推送，原则上不要删除或强制移动
