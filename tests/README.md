# Schema tests

V0.1 覆盖 Schema、Requirement Agent、R Code Agent 与 R Executor。

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

Docker 集成（需已构建 `sciplot-r:0.1`）：

```bash
docker build -t sciplot-r:0.1 docker
python -m pytest tests/test_r_executor.py -v
```
