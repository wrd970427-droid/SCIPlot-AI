# Docker R 执行环境（V0.1）

本目录提供隔离的 R 4.4 运行时。宿主机**不**直接 `Rscript` 用户脚本。

## 文件

```
docker/
├── Dockerfile
├── R/
│   └── packages.R
└── README.md
```

## 镜像内容

- 基础：`rocker/r-ver:4.4.2`
- 已装：tidyverse、ggplot2、ggrepel、svglite、Cairo
- 预留未装：ComplexHeatmap、survival、survminer、pROC、maftools

## 构建

在仓库根目录：

```bash
docker build -t sciplot-r:0.1 docker
```

## 安全默认值（由 `services/r_executor.py` 传入）

| 项 | 值 |
|----|----|
| 网络 | `--network none` |
| CPU | 2 |
| 内存 | 4g |
| 超时 | 120 s |
| 根文件系统 | `--read-only`，可写仅 `/out` 与 `/tmp` |
| 权限 | 非 root uid 1000，`--cap-drop ALL`，`no-new-privileges` |
| 挂载 | 仅脚本目录只读 `/in`，输出目录可写 `/out` |

不要把 `/`、`C:\Windows`、`/etc` 或用户主目录挂进容器。

## 手工试跑

```bash
docker run --rm --network none --cpus 2 --memory 4g \
  --read-only --tmpfs /tmp:rw,nosuid,nodev,size=256m \
  --security-opt no-new-privileges --cap-drop ALL --user 1000:1000 \
  -v /abs/path/to/script.dir:/in:ro \
  -v /abs/path/to/output:/out:rw \
  -w /out \
  sciplot-r:0.1 Rscript --vanilla /in/script.R
```

Python 接口见 `services/r_executor.py`。
