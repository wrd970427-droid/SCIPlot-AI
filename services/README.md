# R Execution Service（V0.1）

将生成的 R 脚本送进 Docker，而不是在宿主机 `Rscript`。

## 文件

```
services/
├── README.md
├── __init__.py
├── r_executor.py
├── workflow.py
```

端到端编排：

```python
from services.workflow import FigureWorkflow

result = FigureWorkflow().generate_figure(prompt, csv_path, work_dir="output/demo")
```

## 接口

```python
from services import execute_r_script

result = execute_r_script("volcano.R", "output")
# result.status: "success" | "failure"
# result.output_files: ["volcano.pdf", ...]
# result.log: combined stdout/stderr
```

构建镜像后再跑真实脚本：

```bash
docker build -t sciplot-r:0.1 docker
python -m pytest tests/test_r_executor.py -v
```
