import "./style.css";

const app = document.querySelector("#app");

app.innerHTML = `
  <main class="page">
    <h1>SCIPlot AI Demo</h1>
    <p class="sub">本地单用户演示：自然语言需求 → Figure Specification → R → QC。仅支持火山图。</p>
    <section class="panel">
      <label for="prompt">绘图需求</label>
      <textarea id="prompt">帮我生成Nature风格RNA-seq火山图</textarea>
      <label for="file">数据文件（CSV / TSV）</label>
      <input id="file" type="file" accept=".csv,.tsv,text/csv" />
      <button id="generate" type="button">Generate</button>
      <div class="status" id="status"></div>
    </section>
    <section class="panel" id="preview-panel" hidden>
      <h2>Figure 预览</h2>
      <img class="preview" id="preview" alt="volcano preview" />
    </section>
    <section class="panel">
      <h2>Figure Specification</h2>
      <pre id="spec">等待生成…</pre>
    </section>
    <section class="panel">
      <h2>Generated R Code</h2>
      <pre id="rscript">等待生成…</pre>
    </section>
    <section class="panel">
      <h2>QC Report</h2>
      <pre id="qc">等待生成…</pre>
    </section>
    <section class="panel">
      <h2>下载</h2>
      <div class="downloads" id="downloads"></div>
    </section>
  </main>
`;

const statusEl = document.querySelector("#status");
const specEl = document.querySelector("#spec");
const rEl = document.querySelector("#rscript");
const qcEl = document.querySelector("#qc");
const downloadsEl = document.querySelector("#downloads");
const previewPanel = document.querySelector("#preview-panel");
const preview = document.querySelector("#preview");
const button = document.querySelector("#generate");

const DOWNLOADS = [
  ["volcano.pdf", "PDF"],
  ["volcano.svg", "SVG"],
  ["volcano.png", "PNG"],
  ["volcano.R", "R script"],
  ["QC_report.json", "QC JSON"],
];

button.addEventListener("click", onGenerate);

async function onGenerate() {
  const prompt = document.querySelector("#prompt").value.trim();
  const file = document.querySelector("#file").files[0];
  if (!file) {
    statusEl.textContent = "请先上传 CSV/TSV。";
    return;
  }
  button.disabled = true;
  statusEl.textContent = "正在提交任务…";
  const body = new FormData();
  body.append("prompt", prompt);
  body.append("file", file);
  try {
    const created = await fetch("/api/figure/generate", { method: "POST", body }).then((r) => r.json());
    if (!created.task_id) {
      statusEl.textContent = created.message || "提交失败";
      button.disabled = false;
      return;
    }
    await poll(created.task_id);
  } catch (err) {
    statusEl.textContent = String(err);
  } finally {
    button.disabled = false;
  }
}

async function poll(taskId) {
  for (let i = 0; i < 120; i += 1) {
    const data = await fetch(`/api/figure/result/${taskId}`).then((r) => r.json());
    statusEl.textContent = `任务 ${taskId}：${data.status}${data.message ? " — " + data.message : ""}`;
    if (data.status && data.status !== "running") {
      render(taskId, data);
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 700));
  }
  statusEl.textContent = "等待超时。请检查后端与 Docker 是否已启动。";
}

function render(taskId, data) {
  specEl.textContent = data.spec ? JSON.stringify(data.spec, null, 2) : data.message || "无 Spec";
  qcEl.textContent = data.qc_report ? JSON.stringify(data.qc_report, null, 2) : "无 QC 报告";
  if (data.questions && data.questions.length) {
    specEl.textContent =
      "Required information missing\n\n" +
      data.questions.map((q) => "- " + q).join("\n") +
      "\n\n" +
      specEl.textContent;
  }
  if (data.log) {
    qcEl.textContent += "\n\n--- execution log ---\n" + data.log;
  }
  downloadsEl.innerHTML = DOWNLOADS.map(
    ([file, label]) =>
      `<a href="/api/figure/download/${taskId}/${file}" target="_blank" rel="noreferrer">${label}</a>`,
  ).join("");
  loadR(taskId);
  if ((data.figure_files || []).includes("volcano.png")) {
    previewPanel.hidden = false;
    preview.src = `/api/figure/download/${taskId}/volcano.png?t=${Date.now()}`;
  } else {
    previewPanel.hidden = true;
  }
}

async function loadR(taskId) {
  try {
    const text = await fetch(`/api/figure/download/${taskId}/volcano.R`).then((r) => {
      if (!r.ok) throw new Error("no r");
      return r.text();
    });
    rEl.textContent = text;
  } catch {
    rEl.textContent = "尚未生成 R 脚本。";
  }
}
