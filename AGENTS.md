# fin-app

## 工作流程

承袭原 `react/AGENTS.md` 的工作流约定：

1. **不动已有函数**：未经明确同意，不改/重命名/删除已存在的函数或方法。
2. **优先新增**：新功能优先新增函数，不就地改写。
3. **不顺手重构**：禁止以"清理"为由改动与当前任务无关的代码。

## 关键约束

- 不引入新 pip / npm 依赖，除非明确批准
- backend 的 services/clients/repositories 默认只读
- 跨 task 改动必须独立 commit；commit message 用 Conventional Commits