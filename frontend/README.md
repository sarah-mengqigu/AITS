# AITS 前端（frontend/）

AITS 智能测试平台前端：Vue 3 + Vite 5 + Element Plus + Pinia + Vue Router + ECharts。

## 环境与命令

```bash
cd frontend
pnpm install --store-dir ./.pnpm-store   # 镜像由 .npmrc 固定；store 放前端目录内
pnpm dev              # http://127.0.0.1:5173
pnpm build            # 产物 dist/
pnpm test -- --run    # vitest 单次运行（等价 pnpm test:run）
```

后端默认地址 `http://127.0.0.1:8000`，开发时由 Vite 代理（`vite.config.js`）：

- `^/api/` → `http://127.0.0.1:8000`
- `^/media/` → `http://127.0.0.1:8000`
- `^/ws/` → `ws://127.0.0.1:8000`（`ws: true`）

> 代理键使用带边界正则，避免前端路由 `/api-testing/*` 被 `/api` 代理截获。

## 环境变量

| 变量 | 说明 | 默认 |
|---|---|---|
| `VITE_API_BASE` | axios baseURL | `/api` |
| `VITE_WS_BASE` | WebSocket 基础路径 | `/ws` |

见 `.env.development`、`.env.production`。

## 目录结构

```
src/
  api/            # axios 实例（含 401 单飞刷新）与 9 个业务模块接口
  components/     # PageHeader/DataTable/StatusTag/StatCard/EmptyState/JsonViewer/ConfirmButton
  layouts/        # MainLayout（侧边菜单 + 顶栏 + 内容区）
  router/         # 路由表 + 登录守卫
  stores/         # auth / project / app（pinia + persistedstate）
  styles/         # 全局样式与主题变量
  utils/          # format / download / ws
  views/          # 页面（本轮：login、dashboard、projects、not-found；其余占位）
tests/            # vitest 单测（format / auth store / download）
```

## 接口契约

所有接口路径严格遵循 `docs/ARCHITECTURE.md` §2；接口模块已完整实现方法，下一页可直接调用。
后端未启动时页面展示可读错误/空态，不会白屏。

## 约定

- 错误提示统一读取 `error.response.data.message`（client.js 归一化为 `error.message`）。
- 列表分页统一 `{ count, results }`；表格使用 `DataTable` 封装 loading / 空态 / 分页。
- 未登录访问任意页面 → `/login?redirect=...`；已登录访问 `/login` → `/dashboard`。
- 401 并发请求共享同一次 refresh；刷新失败清空登录态并跳转登录。
