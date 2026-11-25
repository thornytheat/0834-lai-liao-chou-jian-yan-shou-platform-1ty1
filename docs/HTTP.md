# 阶段接口

`POST /api/stages/<stage>` 接收 `multipart/form-data`。字段 `sample=dirty`、`sample=clean`、`sample=partial` 或 `file=<CSV>` 三选一。阶段为 `intake`、`prepare`、`calculate`、`policy`、`balance`。预览不入库。

`POST /api/runs` 接收同样的输入，执行全批并返回运行报告。`GET /api/runs` 返回最近 50 批。`GET /api/runs/<id>` 查询一批、当前复核状态和各批组复核决定。

`PATCH /api/runs/<id>` 整批复核，接收 `revision`、`status` 和 `note`。状态使用 `APPROVED` 或 `HELD`，决定扇出到全部未签发批组。冲突返回 409，客户端读取新版本后重试。

`PATCH /api/runs/<id>/cases/<case>` 按批组复核，`revision` 使用该批组自己的版本号。仅当批组判定通过、无牵涉隔离行且整单未待查时可 `APPROVED`。不同批组的复核互不冲突，同一批组并发时只有一个生效。已签发批组不可再改。

`GET /api/runs/<id>/evidence` 下载 `review-evidence/2` JSON：运行清单、行号隔离、业务证据、整批复核信息和各批组复核决定（`decisions`）。对账只认 `APPROVED` 批组；每组的 `lines` 与 `balance.release.holds` 把暂缓依据对回原始行。
